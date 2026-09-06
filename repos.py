"""Star Rising: pick a genuinely trending GitHub repo and turn it into a video.

The question pipeline answers what people asked. This one reports what people
starred. The source is the GitHub Search API -- keyless at 10 requests/minute,
30/minute with a token, which Actions hands us for free -- rather than scraping
github.com/trending, which carries no API contract and breaks on a markup change.

"Trending" here means stars per day since creation, inside a recent window: a
repo that took four years to reach 3,000 stars is not news, one that did it in
three weeks is. Everything after that is a filter:

  * no usable description -> skipped, there is nothing honest to narrate
  * lists, tutorials, roadmaps, dotfiles -> skipped, nothing a viewer can run
  * already covered -> skipped, tracked per niche in posted.json
  * an LLM gate keeps only repos a founder or small business could actually run

Every failure path raises so the caller can fall back to the question pipeline:
a quiet week on GitHub must cost a topic, never a run.
"""
import os, re, time
from datetime import date, datetime, timedelta, timezone

import requests

from llm import nim_json

API = "https://api.github.com/search/repositories"
UA = {"User-Agent": "mpt-autopilot/1.0", "Accept": "application/vnd.github+json"}

# Defaults for everything a niche's `star_rising` block can override.
WINDOW_DAYS = 90          # how far back a repo may have been created
MIN_STARS = 300           # floor for "people actually adopted this"
MIN_DESCRIPTION = 40      # chars; below this there is no video in it
PER_PAGE = 50
SHORTLIST = 20            # how many reach the LLM gate

# Repos that trend but that a viewer cannot run: reading material, personal
# config, and course work. Matched against name + description + topics.
NOT_RUNNABLE_RE = re.compile(
    r"\b(?:awesome|awesome-\w+|curated (?:list|collection)|collection of|list of|"
    r"cheat ?sheets?|roadmap|interview (?:questions|prep)|tutorials?|course|"
    r"learning path|study (?:notes|guide)|lecture|textbook|ebook|"
    r"papers?(?: list| collection| we love)|research paper|dotfiles|"
    r"wallpapers?|icons? pack|free-programming|for beginners|"
    r"resume template|portfolio template)\b", re.I)


def log(msg): print(f"[repos] {msg}", flush=True)


def _config(niche):
    return (niche or {}).get("star_rising") or {}


def enabled(niche):
    return bool(_config(niche).get("enabled"))


def _api_get(params, attempts=3):
    """Search API call. A token lifts the rate limit from 10/min to 30/min;
    Actions provides one, so CI never trips it. 403 here is the rate limiter,
    not a permission problem, so unlike research.py's _get it IS worth a wait."""
    headers = dict(UA)
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if token and token.lower() != "xxxx":
        headers["Authorization"] = f"Bearer {token}"
    last = None
    for i in range(attempts):
        try:
            r = requests.get(API, headers=headers, params=params, timeout=30)
            if r.status_code in (403, 429) and "rate limit" in r.text.lower():
                wait = min(float(r.headers.get("Retry-After", 0) or 2 ** i * 10), 60)
                log(f"rate limited, waiting {wait:.0f}s")
                time.sleep(wait)
                last = RuntimeError("search rate limited")
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last = e
            if i < attempts - 1:
                time.sleep(2 ** i * 3)
    raise last


def _age_days(created_at):
    """Whole days since creation, floored at 1 so a day-old repo cannot divide by
    zero and pretend to infinite velocity."""
    try:
        born = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return max(1.0, (datetime.now(timezone.utc) - born).total_seconds() / 86400)


def _normalise(item):
    """One search result -> the fields the rest of the pipeline uses."""
    age = _age_days(item.get("created_at"))
    stars = item.get("stargazers_count") or 0
    return {
        "full_name": item.get("full_name") or "",
        "name": item.get("name") or "",
        "owner": ((item.get("owner") or {}).get("login") or ""),
        "description": (item.get("description") or "").strip(),
        "url": item.get("html_url") or "",
        "stars": stars,
        "language": item.get("language") or "",
        "topics": item.get("topics") or [],
        "license": ((item.get("license") or {}).get("spdx_id") or ""),
        "created_at": item.get("created_at") or "",
        "pushed_at": item.get("pushed_at") or "",
        "archived": bool(item.get("archived")),
        "fork": bool(item.get("fork")),
        "age_days": age,
        # The trending signal itself. Sorting on raw stars just returns whatever
        # was already famous inside the window.
        "stars_per_day": (stars / age) if age else 0.0,
    }


def _latin_ratio(text):
    """Share of letters that are plain a-z. A README-quality description written
    in Chinese or Cyrillic is fine software and a bad narration source -- edge-tts
    reads it in an English voice and the script cannot quote it."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if "a" <= c.lower() <= "z") / len(letters)


def usable_description(repo, min_chars=MIN_DESCRIPTION):
    """A description we can honestly build 50 seconds of narration on."""
    desc = (repo.get("description") or "").strip()
    if len(desc) < min_chars:
        return False
    if len(desc.split()) < 5:
        return False
    if _latin_ratio(desc) < 0.8:
        return False
    # "🔥🔥 the best 🔥🔥" and bare URLs say nothing about what the thing does.
    if desc.lower().startswith(("http://", "https://")):
        return False
    return True


def is_runnable_shape(repo):
    """Reject the trending repos that are reading material, not software."""
    hay = " ".join([repo.get("name", ""), repo.get("description", ""),
                    " ".join(repo.get("topics") or [])])
    return not NOT_RUNNABLE_RE.search(hay)


def fetch_candidates(niche):
    """Every configured query, filtered and ranked by star velocity.

    The queries are all scoped to the same creation window, so what comes back is
    "born recently AND already adopted" -- the closest the Search API gets to the
    trending page's velocity signal."""
    cfg = _config(niche)
    window = int(cfg.get("window_days") or WINDOW_DAYS)
    min_stars = int(cfg.get("min_stars") or MIN_STARS)
    min_chars = int(cfg.get("min_description_chars") or MIN_DESCRIPTION)
    since = (date.today() - timedelta(days=window)).isoformat()
    # A niche can add qualifiers ("topic:self-hosted", "language:python"); the
    # empty string is the plain window query and is always run.
    extras = list(cfg.get("queries") or [""])

    seen, per_query = set(), []
    for extra in extras:
        q = f"created:>={since} stars:>={min_stars}"
        if extra:
            q += f" {extra}"
        try:
            data = _api_get({"q": q, "sort": "stars", "order": "desc",
                             "per_page": PER_PAGE})
        except Exception as e:
            log(f"query {extra or '(plain)'!r} failed: {type(e).__name__}: {str(e)[:90]}")
            continue
        kept = []
        for item in data.get("items", []):
            repo = _normalise(item)
            if not repo["full_name"] or repo["full_name"] in seen:
                continue
            seen.add(repo["full_name"])
            if repo["archived"] or repo["fork"]:
                continue
            if not usable_description(repo, min_chars):
                continue
            if not is_runnable_shape(repo):
                continue
            kept.append(repo)
        kept.sort(key=lambda r: r["stars_per_day"], reverse=True)
        per_query.append(kept)
        log(f"  {extra or '(plain window)'}: {len(kept)} kept")
        time.sleep(2)  # the search endpoint's own rate limit is per-minute

    out = _interleave(per_query)
    log(f"{len(out)} candidate repos after description + shape filters "
        f"(window {window}d, min {min_stars} stars)")
    return out


def _interleave(per_query):
    """Round-robin the per-query results instead of sorting everything by velocity.

    A global sort hands the whole shortlist to whatever is going viral this week
    -- lately that is AI agent harnesses, which the gate rejects one after
    another until the run falls back. Taking the fastest-rising repo from each
    query in turn keeps the niche's own queries (self-hosted, automation, saas)
    represented in the twenty rows the model actually sees."""
    out = []
    for rank in range(max((len(q) for q in per_query), default=0)):
        for query_results in per_query:
            if rank < len(query_results):
                out.append(query_results[rank])
    return out


def unused(candidates, posted_full_names):
    """Drop repos this niche already made a video about. Comparison is
    case-insensitive because GitHub treats owner/name that way."""
    already = {str(n).lower() for n in posted_full_names or ()}
    fresh = [r for r in candidates if r["full_name"].lower() not in already]
    if len(fresh) != len(candidates):
        log(f"skipped {len(candidates) - len(fresh)} repos already covered")
    return fresh


SELECT_SYSTEM = """You choose which trending open-source project becomes the next short
video for a software house whose viewers are FOUNDERS, OPS LEADS and SMALL-BUSINESS
OWNERS -- not developers browsing GitHub.

Pick the ONE repo that:
  - a small business could actually RUN or pay someone to run for them: a self-hostable
    app, an automation tool, a service that replaces a paid subscription, a workable
    alternative to a SaaS product they already buy;
  - has a description concrete enough to explain in 50 seconds without guessing;
  - is a tool, not a toy: it does a job someone is currently paying for.

REJECT (return -1 if the shortlist has nothing better):
  - research code, model weights, benchmarks, papers-with-code
  - libraries and frameworks whose only user is another developer (UI kits, parsers,
    build tools, language bindings)
  - anything whose value is "look how clever this is" rather than "this does your job"
  - demos, clones built as exercises, and repos whose description is a slogan

Then phrase the topic as a hook that names the project and the job it takes over. NOT
"Introducing Foo" (a title, promises nothing). Right: "The self-hosted invoicing app
that replaces your $40/month subscription".

Also return `replaces`: the paid product or manual process this repo takes over, in a
few words, or "" if the description does not support naming one. Never invent one."""


def choose(niche, candidates, limit=SHORTLIST):
    """Ask the model which shortlisted repo is worth a video, and how to phrase it.
    Raises when nothing qualifies -- an empty shortlist is a fallback signal, not a
    reason to publish a video about a paper repository."""
    if not candidates:
        raise RuntimeError("no candidate repos available")
    shortlist = candidates[:limit]
    listed = "\n".join(
        f"{i}. {r['full_name']} [{r['stars']} stars, {r['stars_per_day']:.0f}/day, "
        f"{r['language'] or 'n/a'}{', topics: ' + ', '.join(r['topics'][:5]) if r['topics'] else ''}] "
        f":: {r['description'][:200]}"
        for i, r in enumerate(shortlist)
    )
    guidance = _config(niche).get("select_prompt") or SELECT_SYSTEM
    result = nim_json(
        guidance + ' JSON schema: {"index": <number, or -1 if none qualify>, '
        '"topic": "...", "replaces": "...", "why": "..."} '
        "Topic under 14 words, hook-style, names the project, no clickbait cliches.",
        f"Niche: {niche['name']}\n\nTrending repos:\n{listed}",
        max_tokens=700,
    )
    index = result.get("index")
    topic = (result.get("topic") or "").strip()
    if not isinstance(index, int) or index < 0:
        raise RuntimeError(f"no shortlisted repo qualified: {(result.get('why') or '')[:160]}")
    if index >= len(shortlist) or not topic:
        raise RuntimeError(f"model returned an unusable selection: {str(result)[:160]}")
    repo = dict(shortlist[index])
    repo["replaces"] = (result.get("replaces") or "").strip()
    log(f"chose {repo['full_name']} ({repo['stars']} stars, "
        f"{repo['stars_per_day']:.0f}/day)")
    log(f"  -> {topic}")
    return topic, repo


# Every episode burns a repo permanently, so the pool drains at the publishing
# rate. Warn while there is still time to widen window_days or min_stars rather
# than the morning it hits zero and every run falls back to the question pipeline.
LOW_SUPPLY = 15


def pick(niche, posted_full_names=()):
    """(topic, repo) for the next Star Rising video. Raises if today's GitHub has
    nothing this niche can honestly cover."""
    candidates = unused(fetch_candidates(niche), posted_full_names)
    if not candidates:
        raise RuntimeError("no fresh trending repos passed the filters")
    if len(candidates) < LOW_SUPPLY:
        log(f"WARNING: only {len(candidates)} uncovered repos left. Widen "
            f"star_rising.window_days or lower min_stars before the pool empties.")
    return choose(niche, candidates)


def brief(repo):
    """The facts a script may state, formatted for the writer's system prompt.
    Anything not in here is not established, and the prompt says so."""
    lines = [
        f"REPOSITORY: {repo['full_name']}",
        f"URL: {repo['url']}",
        f"WHAT ITS AUTHORS SAY IT IS: {repo['description']}",
        f"STARS: {repo['stars']:,} (about {repo['stars_per_day']:.0f} a day since it "
        f"was created {int(repo['age_days'])} days ago)",
    ]
    if repo.get("language"):
        lines.append(f"PRIMARY LANGUAGE: {repo['language']}")
    if repo.get("topics"):
        lines.append(f"TOPICS: {', '.join(repo['topics'][:8])}")
    if repo.get("license"):
        lines.append(f"LICENSE: {repo['license']}")
    if repo.get("replaces"):
        lines.append(f"IT PLAUSIBLY REPLACES: {repo['replaces']}")
    return "\n".join(lines)


def stars_label(stars):
    """'4.2k' / '860' -- the badge slot is 12 characters wide."""
    if stars >= 10_000:
        return f"{stars / 1000:.0f}k"
    if stars >= 1_000:
        return f"{stars / 1000:.1f}k"
    return str(stars)

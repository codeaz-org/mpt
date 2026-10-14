"""App Rescue: a recurring segment that sells codeaz's AI-app rescue service.

Each episode takes one real, well-documented way AI-built apps (Lovable, Bolt, v0,
Replit) break in production and ends on rescue.codeaz.org. Topics come from a curated
bank, rescue_topics.json, not from a model: the bank entry is the only set of facts a
script may state, which is what keeps a sales segment honest.

The segment runs one video in `every` (default 3). Within it, five formats take turns,
each a complete system of its own -- where its topic comes from, what the script must
do, how the critic judges it, how it looks on screen, and how repeats are prevented:

  explainer   symptoms -> why -> the proper fix          bank, any topic
  check       "check it yourself": steps a founder runs  bank topics with `check`
              on THEIR OWN app (dashboard, own accounts)
  prompt_fix  what founders prompt, why prompting        bank topics with `prompts`
              cannot fix it, and what does
  checklist   numbered launch checklist, item #N         bank `checklist_order`, in order
  question    a real founder question from Reddit or     harvested, then matched to a
              Google, answered from one bank topic       bank topic; never answered freehand

Formats rotate in that order. A format with nothing left to say this run (no fresh
topic, no matching question) is skipped for the next one, so a run is never lost to
one dry format. Every format burns what it used: per-format topic ids under
posted.json `rescue`, and harvested questions by id like the question pipeline.

Config, per niche in niches.json:

  "app_rescue": {
    "enabled": true,
    "every": 3,                     # one rescue video per N runs
    "url": "rescue.codeaz.org",
    "formats": ["explainer", "check", "prompt_fix", "checklist", "question"],
    "script_prompt": "...",         # voice and rules shared by every format
    "format_prompts": {"check": "...", ...},   # each format's shape
    "critic_rubric": "...", "critic_axes": [...],
    "critic_notes": {"check": "...", ...},     # each format's extra review rules
    "question_sources": {"subreddits": [...], "google_seeds": [...]}
  }
"""
import json, random, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BANK = ROOT / "rescue_topics.json"
LOW_WATER = 3
FORMATS = ("explainer", "check", "prompt_fix", "checklist", "question")

# What each format puts on screen, and the badge it carries.
LABELS = {
    "explainer":  {"tag": "RESCUE",    "now": "Your app now",       "after": "After a proper fix"},
    "check":      {"tag": "CHECK",     "now": "Is this your app?",  "after": "Check it yourself"},
    "prompt_fix": {"tag": "PROMPT",    "now": "What you prompted",  "after": "What actually fixes it"},
    "checklist":  {"tag": "CHECKLIST", "now": "Before you launch",  "after": "How to get it right"},
    "question":   {"tag": "ASKED",     "now": "A founder asked",    "after": "The answer"},
}


def log(msg): print(f"[rescue] {msg}", flush=True)


# ---------------------------------------------------------------- config --
def config(niche):
    return niche.get("app_rescue") or {}


def enabled(niche):
    return bool(config(niche).get("enabled"))


def url(niche):
    return config(niche).get("url") or "rescue.codeaz.org"


def formats(niche):
    wanted = config(niche).get("formats") or FORMATS
    return [f for f in wanted if f in FORMATS]


def is_turn(niche, history):
    """Is this run's video an App Rescue episode? `history` is the niche's recorded
    modes, newest last. One rescue every `every` videos: it is rescue's turn once the
    last every-1 videos were all something else. A freshly enabled niche starts on
    rescue, so the first run after turning it on proves the path end to end."""
    if not enabled(niche):
        return False
    every = max(2, int(config(niche).get("every", 3)))
    recent = list(history or [])[-(every - 1):]
    return "rescue" not in recent


def rotation(niche, last_format=None):
    """Formats in the order to try this run: the one after the last used first, then
    the rest, so a dry format hands over to the next instead of costing the run."""
    order = formats(niche)
    if not order:
        return []
    start = (order.index(last_format) + 1) % len(order) if last_format in order else 0
    return order[start:] + order[:start]


# ------------------------------------------------------------------ bank --
def load_bank(path=BANK):
    data = json.loads(Path(path).read_text())
    topics = data.get("topics") or []
    ids = [t.get("id") for t in topics]
    if len(ids) != len(set(ids)):
        raise RuntimeError("rescue_topics.json has duplicate ids")
    return topics


def load_checklist(path=BANK):
    return list(json.loads(Path(path).read_text()).get("checklist_order") or [])


def _used(used, fmt):
    """`used` is posted.json's per-niche rescue record: {format: [topic ids]}. An old
    flat list predates formats and counts as explainer episodes."""
    if isinstance(used, list):
        used = {"explainer": used}
    return set((used or {}).get(fmt) or [])


def eligible(topic, fmt):
    """Can this bank entry carry an episode in this format?"""
    if fmt == "check":
        return bool(topic.get("check"))
    if fmt == "prompt_fix":
        return bool(topic.get("prompts") and topic.get("prompt_fails"))
    if fmt == "checklist":
        return bool(topic.get("checklist"))
    return True


# ---------------------------------------------------------------- picking --
def _episode(fmt, topic, title, **extra):
    ep = {"format": fmt, "topic": topic, "title": title}
    ep.update(extra)
    return ep


def _pick_from_bank(fmt, bank, used, rng):
    fresh = [t for t in bank if eligible(t, fmt) and t["id"] not in _used(used, fmt)]
    if not fresh:
        raise LookupError(f"no unused topics left for {fmt}")
    if len(fresh) <= LOW_WATER:
        log(f"WARNING: only {len(fresh)} unused topics left for {fmt}")
    topic = rng.choice(fresh)
    return _episode(fmt, topic, topic["topic"])


def _pick_checklist(bank, used, order):
    by_id = {t["id"]: t for t in bank}
    for n, tid in enumerate(order, start=1):
        if tid in by_id and tid not in _used(used, "checklist") and by_id[tid].get("checklist"):
            topic = by_id[tid]
            if len(order) - n < LOW_WATER:
                log(f"WARNING: launch checklist is at item {n} of {len(order)}")
            return _episode("checklist", topic,
                            f"Launch checklist #{n}: {topic['checklist']}",
                            number=n, of=len(order))
    raise LookupError("the launch checklist is complete")


MATCH_SYSTEM = """You match real questions from founders to the one problem in a fixed list that
answers them. The founders built apps with AI app builders (Lovable, Bolt, v0, Replit).

Go through EVERY question. For each one, find the listed problem (if any) whose
explanation and fix would genuinely answer what that founder asked, and score the
pairing from 1 to 10:

  9-10  the problem is exactly what they are asking about
  7-8   the problem is the real answer to their question, even if they did not use
        the technical words ("how do I prove one tenant can't see another's data" is
        the Row Level Security problem)
  1-6   only loosely related, or the question is about pricing, credits, marketing,
        jobs, tool recommendations or which builder is best

A forced match produces a video that answers a question nobody asked, so score
honestly. List every pairing that scores 5 or more. For each, write a video title:
under 14 words, restating their question plainly, no emoji, no exclamation marks.

JSON schema: {"matches": [{"index": <question number>, "problem_id": "<id from the list>", "score": <1-10>, "title": "..."}]}"""
MIN_MATCH = 7

VERIFY_SYSTEM = """A founder asked a question about their app. You are given the question and
ONE problem with its explanation. Would a video explaining this problem and its fix
genuinely answer what they asked? Not 'is it related' -- would they feel answered?

Score 1-10. 9-10: it is the answer. 7-8: it is the real answer even in different
words. 1-6: related topic, but it answers a different question.

JSON schema: {"score": <1-10>, "why": "..."}"""


def _pick_question(niche, bank, used, used_question_ids, harvest, matcher):
    if harvest is None or matcher is None:
        raise LookupError("question format needs a harvester and a matcher")
    sources = config(niche).get("question_sources") or {}
    seeker = {"id": niche["id"], "name": "App Rescue", "ask_hn": False,
              "subreddits": sources.get("subreddits") or [],
              "google_seeds": sources.get("google_seeds") or [],
              "offtopic_terms": niche.get("offtopic_terms") or []}
    asked = [q for q in harvest(seeker) if q.get("id") not in set(used_question_ids or ())]
    topics = [t for t in bank if t["id"] not in _used(used, "question")]
    if not asked or not topics:
        raise LookupError("no fresh founder questions or topics to answer them with")
    shortlist = asked[:20]
    listed_q = "\n".join(
        f"{i}. [{q.get('source', '')}] {q['title']}"
        + (f" :: {q['text'][:160]}" if q.get("text") else "")
        for i, q in enumerate(shortlist))
    listed_p = "\n".join(f"{t['id']}: {t['topic']} -- {t['cause'].split('. ')[0]}"
                         for t in topics)
    result = matcher(MATCH_SYSTEM, f"Questions:\n{listed_q}\n\nProblems:\n{listed_p}") or {}
    by_id = {t["id"]: t for t in topics}

    def score(m):
        try:
            return float(m.get("score") or 0)
        except (TypeError, ValueError):
            return 0.0
    # Older single-match answers are accepted too.
    matches = result.get("matches") if isinstance(result.get("matches"), list) else [result]
    valid = [m for m in matches if isinstance(m, dict) and isinstance(m.get("index"), int)
             and 0 <= m["index"] < len(shortlist) and m.get("problem_id") in by_id
             and score(m) >= MIN_MATCH]
    if not valid:
        best = max(matches, key=lambda m: score(m) if isinstance(m, dict) else 0, default={})
        raise LookupError(f"no founder question matched a bank topic (best: {str(best)[:120]})")
    result = max(valid, key=score)
    index, pid = result["index"], result["problem_id"]
    q = shortlist[index]
    # A second, independent look at the one pairing chosen. In testing the matcher
    # paired "Is RLS enough to secure my SaaS?" with the empty-list problem -- related
    # words, wrong answer -- and mixed titles between candidates.
    topic = by_id[pid]
    verdict = matcher(VERIFY_SYSTEM, f"Question: {q['title']}\n"
                      + (f"Details: {q['text'][:400]}\n" if q.get("text") else "")
                      + f"\nProblem: {topic['topic']}\nWhy it happens: {topic['cause']}") or {}
    if score(verdict) < MIN_MATCH:
        raise LookupError(f"verifier rejected '{q['title'][:60]}' -> {pid} "
                          f"({str(verdict)[:100]})")
    log(f"matched [{q.get('source')}] {q['title'][:80]} -> {pid}")
    return _episode("question", topic, clean_question(q["title"]), asked=q)


def clean_question(title):
    """The founder's own words, tidied for a title: no '????', no trailing space."""
    t = re.sub(r"([?!])[?!]+", r"\1", title.strip())
    return t[0].upper() + t[1:] if t else t


def pick(niche, used, last_format=None, used_question_ids=(), bank=None,
         checklist=None, harvest=None, matcher=None, rng=random):
    """The next episode: the first format in rotation that has something to say."""
    bank = bank if bank is not None else load_bank()
    checklist = checklist if checklist is not None else load_checklist()
    misses = []
    for fmt in rotation(niche, last_format):
        try:
            if fmt == "checklist":
                ep = _pick_checklist(bank, used, checklist)
            elif fmt == "question":
                ep = _pick_question(niche, bank, used, used_question_ids, harvest, matcher)
            else:
                ep = _pick_from_bank(fmt, bank, used, rng)
            log(f"{fmt}: {ep['title']}")
            return ep
        except LookupError as e:
            misses.append(f"{fmt}: {e}")
            log(f"{fmt} has nothing this run ({e}); trying the next format")
    raise RuntimeError("no App Rescue format could produce an episode: " + "; ".join(misses))


def record(used, ep):
    """Burn the episode's topic for its format. Returns the updated record."""
    if isinstance(used, list):
        used = {"explainer": used}
    used = dict(used or {})
    used.setdefault(ep["format"], []).append(ep["topic"]["id"])
    return used


# ------------------------------------------------------------- the writer --
def brief(ep, niche):
    """The facts block handed to the writer. Everything the narration claims has to
    trace back to these lines."""
    t, fmt = ep["topic"], ep["format"]
    builders = ", ".join(t.get("builders") or ["AI app builders"])
    lines = [
        f"FORMAT: {fmt}",
        f"PROBLEM: {t['topic']}",
        f"WHERE IT SHOWS UP: apps built with {builders}",
        "WHAT THE FOUNDER SEES:", *[f"  - {s}" for s in t.get("symptoms") or []],
        f"WHY IT HAPPENS: {t['cause']}",
        "THE PROPER FIX:", *[f"  - {f}" for f in t.get("fixes") or []],
    ]
    if fmt == "check":
        lines += ["HOW TO CHECK, ON YOUR OWN APP:", *[f"  - {c}" for c in t["check"]]]
    if fmt == "prompt_fix":
        lines += ["WHAT FOUNDERS USUALLY PROMPT:", *[f'  - "{p}"' for p in t["prompts"]],
                  f"WHY PROMPTING CANNOT FIX IT: {t['prompt_fails']}"]
    if fmt == "checklist":
        lines += [f"LAUNCH CHECKLIST ITEM #{ep['number']} of {ep['of']}: {t['checklist']}"]
    if fmt == "question":
        q = ep["asked"]
        lines += [f"THE REAL QUESTION (asked on {q.get('source') or 'a founder forum'}): "
                  f"\"{q['title']}\""]
    lines.append(f"THE OFFER: a written audit of the founder's app, delivered in 72 hours, "
                 f"then fixed-price fixes. Booked at {url(niche)}.")
    return "\n".join(lines)


def script_prompt(niche, fmt):
    cfg = config(niche)
    shape = (cfg.get("format_prompts") or {}).get(fmt, "")
    return (cfg.get("script_prompt") or "") + ("\n\n" + shape if shape else "")


SPOKEN_URL = "rescue dot codeaz dot org"


def spoken(script, niche=None):
    """Narration is read by a TTS voice, so write it the way it should sound: a
    checklist '#3' is 'number three' not 'hash three', the link is said the same way
    every time, and an all-caps label is not shouted."""
    out = re.sub(r"#\s?(\d+)", r"number \1", script)
    site = re.escape(url(niche or {}))
    out = re.sub(r"(?:https?://)?" + site, SPOKEN_URL, out, flags=re.I)
    # Plain words over jargon, and no read-aloud signposts like "Why:".
    out = plain(out)
    out = re.sub(r"(?:(?<=[.!?])|^)\s*(?:Why|How to get it right|What actually fixes it|The fix)\s*:\s*(\w)",
                 lambda m: " " + m.group(1).upper(), out).strip()
    out = re.sub(r"\b[A-Z]{2,}(?:\s+[A-Z]{2,})+\b",
                 lambda m: m.group(0).capitalize() if m.group(0) not in ("RLS",) else m.group(0), out)
    return out


# "1)" or "2." starting a list item -- but not "number 4." ending a sentence.
_WORDS = dict(enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()))
_LIST_MARKER = re.compile(r"(?:^|[:;]|(?<!number)\s)(?:\d[.)]|\(\d\))\s")


def script_problems(ep, script):
    """Format rules a reviewing model is too lenient on, checked in code. Each is
    (problem, instruction to the writer). An empty list means the script may go to
    review."""
    problems = []
    low = script.lower()
    if _LIST_MARKER.search(script):
        problems.append(("reads a numbered list aloud ('1)', '2.')",
                         "Say the steps as speech: 'first', 'then', 'finally'. No list numbers."))
    mentions = low.count(SPOKEN_URL)
    if mentions != 1:
        problems.append((f"mentions the audit link {mentions} times",
                         f"Mention '{SPOKEN_URL}' exactly once, in the close."))
    if ep["format"] == "prompt_fix":
        prompts = [p.lower().strip(" .?!") for p in ep["topic"].get("prompts") or []]
        if not any(p in low for p in prompts):
            problems.append(("never names the prompt the founder typed",
                             "Quote one of these prompts word for word in the first two "
                             "sentences: " + "; ".join(f'"{p}"' for p in prompts)))
    code = re.search(r"\b\w+\.\w+\(\)|\b[a-z]+_[a-z_]+\b|\b[A-Z]+_[A-Z_]*\b(?<!VITE_)(?<!NEXT_PUBLIC_)",
                     script)
    if code and ep["topic"]["id"] != "vite-env-exposed":
        problems.append((f"reads code aloud ('{code.group(0)}')",
                         "Describe it in words instead of naming code: 'the column that "
                         "holds the user's id', 'the logged-in user'."))
    words = len(script.split())
    if words > 140:
        problems.append((f"{words} words; the video runs long",
                         "Cut to 110-130 words. Keep the fix steps, cut repetition."))
    if ep["format"] == "question":
        opener = re.split(r"(?<=[.!?])\s+", script.strip(), maxsplit=1)[0].lower()
        if "asked" not in opener:
            problems.append(("does not open by framing the founder's question",
                             "Open with 'A founder asked' and their question in your own "
                             "words. Describe only what they wrote, nothing about their app."))
        stop = {"how", "do", "you", "i", "my", "the", "a", "an", "to", "is", "it", "in", "of",
                "and", "or", "can", "what", "why", "does", "for", "on", "with", "am", "are",
                "founder", "asked", "someone", "be", "if", "that", "this", "your", "me"}
        def keywords(text):
            return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in stop}
        if ep.get("asked") and not keywords(opener) & keywords(ep["asked"]["title"]):
            problems.append(("the opening does not restate the real question",
                             f"Open with 'A founder asked' and THIS question in your own "
                             f"words: \"{ep['asked']['title']}\""))
        invented = re.search(r"\b(?:the|this|that) founder(?:'s)? (?:built|has|app|users)|"
                             r"\btheir app (?:is|has|works|shows)", low)
        if invented:
            problems.append((f"claims things about the asker's app ('{invented.group(0)}')",
                             "Say nothing about the asker's app beyond their question. "
                             "Explain the general problem and its fix instead."))
    said = (f"number {ep.get('number')}", f"number {_WORDS.get(ep.get('number'), '-')}")
    if ep["format"] == "checklist" and not any(x in low for x in said):
        problems.append((f"does not say checklist number {ep['number']}",
                         f"Open with 'Launch checklist, number {ep['number']}:'."))
    return problems


def _first(text):
    return (text or "").split(". ")[0].rstrip(".") + "."


def description(ep):
    """The two description sentences, built from the bank rather than written by a
    model: in previews the model added causes the bank never stated ('or site
    verification settings') and words the brand bans ('guarantees')."""
    t, fmt = ep["topic"], ep["format"]
    if fmt == "question":
        lead = f"A founder asked: \"{ep['asked']['title'].strip()}\""
    elif fmt == "checklist":
        lead = f"Launch checklist, number {ep['number']}: {t['checklist']}."
    elif fmt == "check":
        lead = f"How to check your own app for this: {t['topic'][0].lower()}{t['topic'][1:]}."
    else:
        lead = t["topic"].rstrip(".") + "."
    why = (t.get("prompt_fails") if fmt == "prompt_fix" else t.get("cause")) or ""
    return plain(f"{lead} {why}".strip())


def plain(text):
    """Everyday words for the viewer-facing text: the bank is written for accuracy."""
    text = re.sub(r"\b(?:Supabase\s+)?anon(?:ymous)?\s+key\b", "public key", text, flags=re.I)
    return re.sub(r"\bpublic (?:API )?key,? called the public key\b,?", "public key", text, flags=re.I)


def critic_overrides(niche, fmt):
    """The shared rescue rubric plus this format's own review rules."""
    cfg = config(niche)
    out = {k: cfg[k] for k in ("critic_rubric", "critic_axes") if cfg.get(k)}
    note = (cfg.get("critic_notes") or {}).get(fmt)
    if note and out.get("critic_rubric"):
        out["critic_rubric"] = out["critic_rubric"] + "\n\nFORMAT RULES (" + fmt + "):\n" + note
    return out


def question(ep):
    """What the critic scores `answers_question` against."""
    if ep["format"] == "question":
        return ep["asked"]["title"]
    t = ep["topic"]
    return {
        "check": f"How do I check whether my app has this problem: {t['topic']}?",
        "prompt_fix": f"Why hasn't prompting the AI fixed this: {t['topic']}?",
        "checklist": f"Before launch, how do I make sure that: {t.get('checklist', t['topic'])}?",
    }.get(ep["format"], f"My app has this problem: {t['topic']}. What is going on and how do I fix it?")


# ------------------------------------------------------------- the screen --
def base_props(ep, niche):
    """RescueSplit props that come from the bank, not the narration. The lists on
    screen are the facts of the episode, already written to fit their slots, so the
    extractor does not get a vote on them."""
    t, fmt = ep["topic"], ep["format"]
    labels = LABELS[fmt]
    first = (t.get("prompt_fails") if fmt == "prompt_fix" else t.get("cause")) or ""
    props = {
        "format": fmt, "url": url(niche),
        # The "why" line is the bank's first sentence: an extractor squeezing it to fit
        # produced "Public bucket, no expiry", which explains nothing.
        "cause": first.split(". ")[0].rstrip(".") + ".",
        "labelNow": labels["now"], "labelAfter": labels["after"],
        "builders": " · ".join(t.get("builders") or []),
        "symptoms": list(t.get("symptoms") or [])[:3],
        "fixes": list(t.get("fixes") or [])[:3],
    }
    if fmt == "check":
        props["fixes"] = list(t["check"])[:3]
    if fmt == "prompt_fix":
        props["symptoms"] = list(t["prompts"])[:2]
    if fmt == "checklist":
        props["number"] = ep["number"]
        props["of"] = ep["of"]
        props["symptoms"] = [t["checklist"]]
    if fmt == "question":
        q = ep["asked"]
        props["asked"] = q["title"]
        props["askedOn"] = q.get("source") or ""
    return props


def fallback_props(ep):
    """Used only where the extractor came back empty for a field."""
    t = ep["topic"]
    first = (t.get("prompt_fails") if ep["format"] == "prompt_fix" else t.get("cause")) or ""
    return {"cause": first.split(". ")[0].rstrip(".") + "."}


def tag(ep):
    return LABELS[ep["format"]]["tag"]

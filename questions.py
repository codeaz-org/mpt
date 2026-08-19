"""Harvest real questions that real people asked, and pick one to answer.

The model no longer invents video ideas. Every video starts from a question a human
actually posted -- on Reddit, Ask HN or Stack Overflow -- and the model's only job is to
answer it. That is the difference between a channel that mass-produces topics and one
that responds to its audience, and it is also what YouTube's inauthentic-content policy
looks for.

Selection rules, in order:
  1. it must read as a question, not a link or an announcement
  2. it must have engagement, since an unanswered post is not a shared problem
  3. it must not repeat a question already used, or a video already published
"""
import re
from collections import Counter

import research
from llm import nim_json

# "how do i", "why does", "what is", "can someone explain" ... or simply ends with "?"
QUESTION_RE = re.compile(
    r"^\s*(?:how|why|what|when|where|which|who|can|could|should|does|do|did|is|are|was|"
    r"were|will|would|am|if|anyone|does anyone|has anyone|eli5|explain)\b|[?]\s*$", re.I)
# Posts that are questions but not about the subject: careers, hiring, hardware, drama.
OFFTOPIC_RE = re.compile(
    r"\b(?:salary|salaries|hiring|interview|resume|cv|job offer|laid off|layoff|"
    r"which laptop|what laptop|should i quit|bootcamp worth|am i too old|career change|"
    r"visa|relocat\w+|remote job|freelanc\w+ rate)\b", re.I)
MIN_ENGAGEMENT = 3
MAX_TITLE_WORDS = 30


def log(msg): print(f"[questions] {msg}", flush=True)


def _offtopic_pattern(niche):
    """A niche can override the default block list. Software-house-facing niches, for
    example, treat 'hiring' and 'freelance rates' as on-topic buyer language."""
    terms = (niche or {}).get("offtopic_terms")
    if terms is None:
        return OFFTOPIC_RE
    if not terms:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")\b", re.I)


def looks_like_a_question(post, niche=None):
    title = (post.get("title") or "").strip()
    if not title or len(title.split()) > MAX_TITLE_WORDS:
        return False
    pattern = _offtopic_pattern(niche)
    if pattern and pattern.search(title):
        return False
    return bool(QUESTION_RE.search(title))


def harvest(niche):
    """Every configured source, filtered down to real questions with engagement."""
    posts = []
    for sub in niche.get("subreddits", []):
        try:
            posts += research.fetch_subreddit(sub)
        except Exception as e:
            log(f"r/{sub}: {type(e).__name__}: {str(e)[:70]}")
    if niche.get("ask_hn", True):
        try:
            posts += research.fetch_ask_hn()
        except Exception as e:
            log(f"ask hn: {type(e).__name__}: {str(e)[:70]}")
    for query in niche.get("hn_queries", []):
        try:
            posts += research.fetch_hn(query or None)
        except Exception as e:
            log(f"hn '{query}': {type(e).__name__}: {str(e)[:70]}")
    for tag in niche.get("stackexchange_tags", []):
        try:
            posts += research.fetch_stackexchange(tag)
        except Exception as e:
            log(f"stackexchange '{tag}': {type(e).__name__}: {str(e)[:70]}")
    for seed in niche.get("google_seeds", []):
        try:
            posts += research.fetch_google_suggest(seed)
        except Exception as e:
            log(f"google '{seed}': {type(e).__name__}: {str(e)[:70]}")

    questions, seen = [], set()
    for p in posts:
        if not looks_like_a_question(p, niche):
            continue
        if (p.get("score", 0) + p.get("num_comments", 0)) < MIN_ENGAGEMENT:
            continue
        key = (p.get("title") or "").strip().lower()
        if key in seen:
            continue
        seen.add(key)
        questions.append(p)

    questions.sort(key=lambda p: p.get("score", 0) + 2 * p.get("num_comments", 0), reverse=True)
    log(f"{len(questions)} real questions from {len(posts)} posts")
    return questions


_SUBJECT_STOP = frozenset("""a an and are as at be but by for from how i in is it my
of on or should the to was were what when where which who why with your you can does
do so if not just about that this these those there here have has had will would could
using use used make makes made get gets got new best free my me our we they them their
why-does why-is how-do how-to what-is""".split())
_SUBJECT_TOKEN_RE = re.compile(r"[a-z][a-z0-9\-\.]{3,}")


def _subject_tokens(text):
    return [t for t in _SUBJECT_TOKEN_RE.findall(text.lower()) if t not in _SUBJECT_STOP]


def _hot_subjects(used_topics, keep_last=8, min_repeats=2):
    """Subject nouns that appear in >=min_repeats of the last N posted topics --
    the ones the channel is leaning on. Later we push questions that hit these to
    the tail of the shortlist so fresher subjects surface first."""
    counts = Counter()
    for topic in used_topics[-keep_last:]:
        counts.update(set(_subject_tokens(topic)))
    return {tok for tok, n in counts.items() if n >= min_repeats}


def unused(questions, used_ids, used_topics, too_similar):
    """Drop anything already turned into a video, by source id or by subject.
    Then re-rank so questions on subjects the channel has leaned on recently
    fall to the tail. Stable sort preserves engagement order within a bucket."""
    out = []
    for q in questions:
        if q.get("id") and q["id"] in used_ids:
            continue
        clash, _ = too_similar(q["title"], used_topics)
        if clash:
            continue
        out.append(q)
    hot = _hot_subjects(used_topics)
    if hot:
        out.sort(key=lambda q: len(hot.intersection(_subject_tokens(q.get("title") or ""))))
        log(f"downranked recent subjects: {sorted(hot)}")
    return out


SELECT_SYSTEM = """You choose which audience question to answer in the next short video, and
phrase it as a video topic.

You are given real questions people posted today. Pick the ONE that is:
  - a genuine misunderstanding of how something works, not a request for opinions,
    recommendations, tools, career advice or someone's personal situation;
  - explainable in 60 seconds through an everyday analogy;
  - useful to many people, not only the person who asked.

Then write the topic as a hook that restates THEIR question and hints at an everyday
system with moving parts. The topic is a promise to answer that question.

"RGB Normalization Gearbox" is wrong: it is a title, it names no question and promises
nothing. "Divide RGB by 255 or 256? The off-by-one that shifts every colour" is right.

Keep the asker's actual problem: do not drift to a neighbouring subject you find more
interesting.

Return the index of the question you chose and the topic."""


def choose(niche, questions, limit=25):
    """Ask the model to pick the most explainable question and phrase it as a topic.
    It selects from real questions; it does not invent one."""
    if not questions:
        raise RuntimeError("no unused questions available")
    shortlist = questions[:limit]
    listed = "\n".join(
        f"{i}. [{q.get('score', 0)}pts/{q.get('num_comments', 0)}c {q.get('source', '')}] "
        f"{q['title']}" + (f" :: {q['text'][:120]}" if q.get("text") else "")
        for i, q in enumerate(shortlist)
    )
    guidance = niche.get("select_prompt") or SELECT_SYSTEM
    result = nim_json(
        guidance + ' JSON schema: {"index": <number>, "topic": "...", "why": "..."} '
        "Topic under 14 words, hook-style, no clickbait cliches.",
        f"Niche: {niche['name']}\n\nQuestions:\n{listed}",
        max_tokens=700,
    )
    index = result.get("index")
    topic = (result.get("topic") or "").strip()
    if not isinstance(index, int) or not 0 <= index < len(shortlist) or not topic:
        raise RuntimeError(f"model returned an unusable selection: {str(result)[:160]}")
    question = shortlist[index]
    log(f"chose [{question.get('source')}] {question['title'][:80]}")
    log(f"  -> {topic}")
    return topic, question

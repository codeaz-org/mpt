#!/usr/bin/env python3
"""
MPT Autopilot: NVIDIA NIM topic gen -> MoneyPrinterTurbo video -> YouTube (+ optional TikTok via Upload-Post).

Env vars required:
  PEXELS_API_KEY         Pexels API key
  YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN_<NICHEID>   (per-niche YouTube OAuth)
Optional:
  OLLAMA_URL             default: http://localhost:11434 (CI installs & warms Ollama)
  OLLAMA_MODEL           default: gpt-oss:20b
  UPLOAD_POST_API_KEY    enables TikTok via upload-post.com
  MPT_DIR                path to MoneyPrinterTurbo checkout (default: ./MoneyPrinterTurbo)
  NICHES                 comma-separated niche ids to run (default: all)
"""
import difflib, json, os, random, re, shutil, subprocess, sys, time, glob
from pathlib import Path

import requests

import buffer
import critic
import questions
from llm import NIM_MODEL, nim_chat

ROOT = Path(__file__).resolve().parent

# ponytail: load .env if present; skipped for real deploys (CI sets env directly)
_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
MPT_DIR = Path(os.environ.get("MPT_DIR", ROOT / "MoneyPrinterTurbo"))
STATE_FILE = ROOT / "posted.json"
# DRY_RUN renders everything but uploads nothing, leaving the mp4 in ./out for review.
DRY_RUN = os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes")
OUT_DIR = ROOT / "out"
# Edge TTS name in MPT's format: <edge-tts ShortName>-<Gender>. The "Neural" suffix is
# part of the real voice id; dropping it makes MPT fall back to its Chinese default.
DEFAULT_VOICE = "en-GB-RyanNeural-Male"
# TikTok-style captions. MPT defaults to STHeitiMedium.ttc (a Chinese system font) at
# size 60 pinned to the bottom, which collides with the TikTok caption bar and the
# YouTube Shorts title strip. BeVietnamPro-Bold is the one bold Latin face MPT ships.
SUBTITLE_STYLE = {
    "font_name": "BeVietnamPro-Bold.ttf",
    "font_size": 80,
    "subtitle_position": "custom",
    # Percent from top. 58 left too little room below: a caption that wrapped to three
    # lines ran off the bottom of the frame, cutting the last line in half.
    "custom_position": 52,
    "text_fore_color": "#FFFFFF",
    "stroke_color": "#000000",
    "stroke_width": 4.0,
    "rounded_subtitle_background": False,
}


def log(msg): print(f"[autopilot] {msg}", flush=True)


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"topics": {}, "uploads": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# Words that carry no topic identity, so two topics sharing only these are unrelated.
_STOP = {"the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "by", "with",
         "your", "you", "like", "explained", "why", "how", "what", "when", "is", "are",
         "does", "do", "it", "its", "that", "this", "as", "at", "from", "into", "using"}
# Two independent signals, each with its own bar. Every topic shares the same skeleton
# ("<concept>, explained by <everyday thing>"), which pushes raw character similarity to
# ~50% even for unrelated pairs, so that alone cannot be the test.
TOPIC_JACCARD_LIMIT = 0.40    # shared subject vocabulary
TOPIC_RATIO_LIMIT = 0.72      # near-identical phrasing


def _topic_tokens(topic):
    words = re.findall(r"[a-z]+", topic.lower())
    # crude singularisation so "function" and "functions" count as the same word
    return {w[:-1] if len(w) > 4 and w.endswith("s") else w
            for w in words if w not in _STOP and len(w) > 2}


def topic_similarity(a, b):
    """(vocabulary overlap, phrasing ratio) for two topics, each 0..1."""
    ta, tb = _topic_tokens(a), _topic_tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    ratio = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return jaccard, ratio


CONCEPT_SPLIT_RE = re.compile(r"\s*(?:,|--|:)?\s*\b(?:explained|described|shown)\b|\s+\blike\b\s+",
                              re.I)
CONCEPT_JACCARD_LIMIT = 0.6


def topic_concept(topic):
    """The part before the analogy: 'Recursion, explained by Russian dolls' -> 'Recursion'.
    Swapping the analogy does not make it a different video."""
    return _topic_tokens(CONCEPT_SPLIT_RE.split(topic, maxsplit=1)[0])


def too_similar(topic, used_topics):
    """The already-used topic this one repeats, if any, with the reason."""
    concept = topic_concept(topic)
    for old in used_topics:
        jaccard, ratio = topic_similarity(topic, old)
        if jaccard >= TOPIC_JACCARD_LIMIT:
            return old, f"{jaccard:.0%} shared vocabulary"
        if ratio >= TOPIC_RATIO_LIMIT:
            return old, f"{ratio:.0%} identical phrasing"
        old_concept = topic_concept(old)
        if concept and old_concept:
            overlap = len(concept & old_concept) / len(concept | old_concept)
            if overlap >= CONCEPT_JACCARD_LIMIT:
                return old, f"same concept ({overlap:.0%}), only the analogy differs"
    return None, ""


def pick_topic(niche, used_topics, used_question_ids=(), attempts=2):
    """Answer a question a human actually asked.

    The model no longer invents subjects: it picks from questions harvested today and
    phrases the chosen one as a topic. Anything already answered -- by source id or by
    subject -- is filtered out first. If no source yields a usable question the run
    stops, because inventing one is exactly the behaviour we removed."""
    forced = os.environ.get("TOPIC", "").strip()
    if forced:
        log(f"[{niche['id']}] Topic (forced via TOPIC): {forced}")
        return forced, None

    harvested = questions.harvest(niche)
    available = questions.unused(harvested, set(used_question_ids), used_topics, too_similar)
    log(f"[{niche['id']}] {len(available)} unanswered questions after dedupe")
    if not available:
        raise RuntimeError("no unanswered questions today: widen the niche's sources")

    rejected = []
    last_err = None
    for attempt in range(attempts):
        pool = [q for q in available if q not in rejected]
        if not pool:
            break
        # Shuffle on retries so the model sees a different top of the list --
        # gpt-oss will return {} when its first look at the shortlist doesn't
        # match its taste, and offering the same shortlist gets the same {}.
        if attempt:
            random.shuffle(pool)
        try:
            topic, question = questions.choose(niche, pool)
        except RuntimeError as e:
            last_err = e
            log(f"[{niche['id']}] select attempt {attempt + 1}/{attempts}: {str(e)[:180]}")
            continue
        clash, why = too_similar(topic, used_topics)
        if clash:
            log(f"[{niche['id']}] rejected '{topic}' -- {why} with '{clash}'")
            rejected.append(question)
            continue
        log(f"[{niche['id']}] Topic: {topic}")
        log(f"[{niche['id']}] answering: {question['url']}")
        return topic, question
    if last_err:
        raise last_err
    raise RuntimeError("every candidate question repeated an existing video")


SCRIPT_SYSTEM = """You write narration for a 50-60 second vertical short. Plain spoken English, no
markdown, no headings, no stage directions, no emoji, no hashtags, no "in this video".
Write only the words the narrator says.

Structure, in this exact order:
1. HOOK (1 sentence): open inside the problem with something concrete and visible, as
   if mid-argument. State what actually happens, with a real number, object or effect.
   Never a question, never "have you ever", never a definition, and never a hedge like
   "can lead to" or "is important".
     hook:     "Divide by 256 and every colour in your app comes out one shade dark."
     hook:     "Two waiters just sold the same table twice."
     not hook: "Have you wondered how race conditions work?"
     not hook: "Using the wrong divisor can lead to inaccurate colour representation."
2. ANALOGY (1-2 sentences): introduce the everyday situation in vivid, specific detail.
3. MAPPING (3-4 sentences): the heart of the video. Name each piece of the analogy and
   say exactly which piece of the real subject it stands for. Every analogy element must
   be mapped by name. This is not optional and it is what the video is for.
4. WHY IT MATTERS (1-2 sentences): a concrete consequence a beginner would actually hit
   -- a bug, a crash, a slow page, a security hole. Be specific about the failure.
5. PAYOFF (1 sentence): the one-line takeaway a viewer could repeat to a friend.

Rules: 130-165 words. Short sentences. Use the real technical vocabulary (the actual
keyword, method, or concept name) at least three times. No filler like "let's dive in".
Never explain the analogy without mapping it. Never end on a question."""


# A mapping sentence names an analogy part and the thing it stands for: "the waiter is
# the thread", "each table acts as a shared resource". Llama 3.3 70B will happily return
# a fluent description with none of these, so the output is checked instead of trusted.
MAPPING_RE = re.compile(
    r"\b(?:is|are|being|becomes|represents?|stands? for|acts? as|acts? like|"
    r"plays the role of|maps? to|equals?)\s+"
    r"(?:just\s+)?(?:like\s+)?(?:the|your|a|an|its)\s+\w+",
    re.I,
)
MIN_MAPPINGS = 3

# Concurrency vocabulary is the drift the model falls into: given any analogy it starts
# talking about threads and locks even when the topic is loops or functions. Unless the
# topic is genuinely about concurrency, more than one of these means the script is wrong,
# however fluent it reads.
DRIFT_RE = re.compile(
    r"\b(?:threads?|locks?|locking|mutexe?s?|semaphores?|deadlocks?|race conditions?|"
    r"race windows?|shared resources?|synchroni[sz]ation|mutator|atomic|concurren\w+)\b", re.I)
MAX_DRIFT = 1

# The topic is a question, so the model kept opening by restating it -- which is the one
# opener that cannot hook anyone, since it promises an answer instead of showing a
# problem. The critic scored it 6 every time but nothing forced a rewrite, so the check
# is objective and mechanical: judge the first sentence, not the model's taste.
WEAK_HOOK_RE = re.compile(
    r"^\s*(?:have you ever|ever wondered|did you know|let'?s talk|let'?s dive|in this video|"
    r"today (?:we|i)\b|welcome back|what if (?:you|we)\b|imagine if|so,? you|"
    r"if you'?re (?:a |an )?(?:developer|programmer|beginner)\b)", re.I)
# Hedged abstractions read as statements but promise nothing: "using the wrong divisor
# can lead to inaccurate colour representation" is not a hook, it is a disclaimer.
HEDGE_RE = re.compile(
    r"\b(?:can lead to|may (?:lead|cause|result)|could (?:lead|cause|result)|can cause|"
    r"can result in|is important|are important|plays? a (?:crucial|key|vital) role|"
    r"can be (?:tricky|confusing|challenging|difficult)|it'?s essential|"
    r"one of the most (?:common|important))\b", re.I)


def _first_sentence(script):
    return re.split(r"(?<=[.!?])\s+", script.strip(), maxsplit=1)[0].strip()


def weak_hook(script):
    """Why the opening line fails, or None. A hook must assert something concrete;
    a question hands the tension back to the viewer instead of creating it."""
    opener = _first_sentence(script)
    if not opener:
        return "the script is empty"
    if opener.endswith("?"):
        return f"opens with a question: {opener!r}"
    if WEAK_HOOK_RE.match(opener):
        return f"opens with a stock phrase: {opener!r}"
    if len(opener.split()) > 28:
        return f"opening sentence is {len(opener.split())} words; it should land in one breath"
    hedge = HEDGE_RE.search(opener)
    if hedge:
        return (f"hedged abstraction {hedge.group(0)!r} instead of a concrete consequence: "
                f"{opener!r}")
    return None


def _drift_pattern(niche):
    """Each niche drifts toward its own cliches, so the guard is per niche. Programming
    scripts wander into threads and locks; a finance script would wander into crypto
    hype. A niche can set "drift_terms" to override the default list."""
    terms = (niche or {}).get("drift_terms")
    if not terms:
        return DRIFT_RE
    return re.compile(r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")\b", re.I)


def _drift_terms(script, topic, niche=None):
    """Off-topic jargon, ignoring anything the topic itself names."""
    pattern = _drift_pattern(niche)
    if pattern.search(topic):
        return []
    return sorted({m.group(0).lower() for m in pattern.finditer(script)})


def _clean_script(raw):
    # Reasoning-capable models (deepseek-v3.1, gpt-oss) can emit a thinking block; it
    # would otherwise be narrated aloud. Drop it, including an unclosed trailing one.
    s = re.sub(r"(?is)<(think|thinking|reasoning)>.*?</\1>", " ", raw)
    s = re.sub(r"(?is)<(?:think|thinking|reasoning)>.*$", " ", s)
    s = re.sub(r"```[a-z]*|```", "", s)
    s = re.sub(r"^\s*(?:#+|\*+|\d+[\.\)])\s*", "", s, flags=re.M)
    s = re.sub(r"(?im)^\s*(?:hook|analogy|mapping|why it matters|payoff)\s*[:\-]\s*", "", s)
    s = re.sub(r"\*\*|__|\[[^\]]*\]", "", s)
    s = re.sub(r"\n{2,}", " ", s).replace("\n", " ")
    return re.sub(r"\s{2,}", " ", s).strip().strip('"')


HOOK_SYSTEM = """You write the opening line of a short video, and nothing else.

You are given a question a viewer asked and the script that answers it. Write ONE
sentence, under 20 words, that makes someone stop scrolling.

Rules:
  - State a concrete, visible consequence, or the counter-intuitive part of the answer.
  - Use a real number, object or effect taken from the script.
  - Never a question. Never "have you ever", "did you know", "in this video".
  - Never a hedge: no "can lead to", "may cause", "is important", "can be tricky".
  - Present tense, active, no preamble.

Examples:
  "Divide by 256 and every colour in your app comes out one shade dark."
  "Two waiters just sold the same table twice."
  "Your loop never exits because the counter resets on every pass."

Return only the sentence."""


def _rewrite_hook(script, topic, question=None, attempts=3):
    """Replace a weak opening line using a call that does nothing else.

    Asking one model call to answer a question, map an analogy, stay accurate AND land a
    hook means the hook is what gets dropped -- it scored 6 for every draft. Isolated,
    the same model writes a usable one."""
    body = _first_sentence(script)
    rest = script[len(body):].strip()
    asked = f'Viewer asked: "{question}"\n' if question else ""
    for _ in range(attempts):
        try:
            candidate = _clean_script(nim_chat(
                HOOK_SYSTEM,
                f"{asked}Topic: {topic}\n\nScript:\n{script}",
                temperature=0.9, max_tokens=200,
            ))
        except Exception as e:
            log(f"hook rewrite failed ({type(e).__name__}); keeping the original opener")
            return script
        candidate = _first_sentence(candidate).strip('"')
        if candidate and not weak_hook(candidate):
            log(f"hook rewritten: {candidate}")
            return f"{candidate} {rest}".strip()
    return script


FACTS_FILE = ROOT / "facts.md"

# Product / service names the anti-repetition guard tracks. Anything else the model
# names is fine to repeat -- we only care about the recurring examples that make
# consecutive videos sound the same. Case-insensitive substring match on titles is
# enough; a smarter script tokeniser would be more accurate but this is a nudge,
# not a filter.
_TRACKED_TOOLS = (
    "MPT", "MoneyPrinterTurbo", "this account", "this repo", "our automation",
    "GitHub Actions", "Zapier", "Make", "Integromat", "n8n", "Pipedream",
    "IFTTT", "Bubble", "Retool", "Softr", "Glide", "Webflow", "Supabase",
    "Firebase", "Airtable", "Notion", "Neon", "PlanetScale", "Vercel",
    "Netlify", "Cloudflare", "Railway", "Fly.io", "Render", "OpenAI",
    "Anthropic", "Groq", "OpenRouter", "NVIDIA NIM", "Slack", "Discord",
    "Twilio", "SendGrid", "Resend", "Buffer", "Stripe", "Paddle",
    "Lemon Squeezy",
    # Open-source alternatives the OSS-archetype scripts name. Tracking these
    # keeps the OSS videos from all pointing at the same 2-3 projects.
    # ponytail: flat list, promote to per-archetype pools if scripts start
    # bunching on one project again.
    "NocoDB", "Baserow", "Directus", "Appwrite", "PocketBase", "PostHog",
    "Plausible", "Umami", "Ghost", "Nextcloud", "Meilisearch", "Typesense",
    "MinIO", "Cal.com", "Listmonk", "Metabase", "Grafana", "Matomo",
    "Rocket.Chat", "Mattermost", "Jitsi", "Chatwoot", "Formbricks",
)


def _facts():
    """The truth ledger scripts must stick to. Missing file = no facts injected, which
    just means the model falls back to its own priors -- the script prompt still forbids
    invented specifics."""
    if FACTS_FILE.exists():
        return FACTS_FILE.read_text().strip()
    return ""


def _recent_tools(state, niche_id, keep=4):
    """Names of products/services cited in the last N videos for this niche. Fed to
    the writer as an anti-repetition nudge so consecutive videos don't all lean on
    'MPT autopilot on GitHub Actions'."""
    used = []
    scanned = 0
    for entry in reversed(state.get("uploads", [])):
        if entry.get("niche") != niche_id:
            continue
        hay = " ".join(str(entry.get(k) or "") for k in ("title", "topic", "question")).lower()
        for tool in _TRACKED_TOOLS:
            if tool.lower() in hay and tool not in used:
                used.append(tool)
        scanned += 1
        if scanned >= keep:
            break
    return used[:8]


def _write_script(topic, niche, feedback=None, drift=(), question=None, recent_tools=()):
    """One draft. `feedback` carries the critic's instructions from the previous round.
    `recent_tools` lists product names cited in recent videos so we can nudge the writer
    to pick a different example this time."""
    system = niche.get("script_prompt", SCRIPT_SYSTEM)
    notes = []
    facts = _facts()
    if facts:
        notes.append(
            "TRUTH LEDGER -- rules of what you can claim:\n"
            "  * OWN-WORK claims (things this channel/codeaz built, prices we charged, "
            "clients we had): ONLY from the ledger below. If it is not in the ledger, do "
            "not say we did it.\n"
            "  * PUBLIC FACTS (tool pricing that any user can see on the vendor's website, "
            "free-tier limits, publicly documented founder revenue, well-known open-source "
            "projects): allowed, but only if you would bet a paycheck they are correct. "
            "Prefer naming the specific number ('Zapier free tier = 100 tasks/month') over "
            "hedging ('some tools charge per task').\n"
            "  * INVENTED SPECIFICS: never. No made-up client names, no invented dollar "
            "amounts, no fabricated case studies. If you do not know a number, either use "
            "a real range you are confident in, or drop the number entirely.\n\n" + facts)
    if question:
        # The writer must see the question, not only the topic. Without it the script
        # answers the topic's phrasing and drifts off what the viewer actually asked.
        notes.append(
            f'A real viewer asked: "{question}"\n'
            "Answer THAT question directly. The analogy is how you explain the answer, "
            "not a substitute for it. By the end the asker should know the answer.\n"
            "Do NOT open by repeating the question back. Open with the consequence of "
            "getting it wrong, or with the surprising part of the answer, then explain.")
    notes.append("")
    if feedback:
        notes.append("An editor reviewed your previous attempt and rejected it. Their "
                     f"instructions:\n{feedback}")
    if drift:
        notes.append(f"You also used {', '.join(drift)}, which do not belong to this "
                     "topic. Remove them.")
    if recent_tools:
        notes.append(
            "DO NOT reuse these examples/tools -- they were used in the last few videos and "
            "the channel is starting to sound repetitive: "
            + ", ".join(recent_tools) + ". "
            "Pick a genuinely different concrete example from the ledger (a different "
            "automation platform, a different backend, a different hosting story). Same "
            "point, fresh casting.")
    notes = [n for n in notes if n]
    if notes:
        system += "\n\n" + "\n\n".join(notes)
    return _clean_script(nim_chat(
        system,
        f"Topic: {topic}\n\nWrite the narration now.",
        temperature=0.8 if not feedback else 0.6,
        max_tokens=2000,
    ))


def generate_script(topic, niche, question=None, recent_tools=()):
    """Draft, critique, revise, until an editor agent passes it.

    A model asked to write and approve its own work approves nearly everything, so the
    critic is a separate call with its own rubric. Drift and length are checked here
    because they are cheap and objective; everything subjective is the critic's call."""
    state = {"drift": ()}

    asked = question.get("title") if isinstance(question, dict) else question
    if recent_tools:
        log(f"[{niche['id']}] avoiding recent examples: {', '.join(recent_tools)}")

    def write(feedback):
        script = _write_script(topic, niche, feedback, state["drift"], asked,
                                recent_tools=recent_tools)
        if weak_hook(script):
            script = _rewrite_hook(script, topic, asked)
        state["drift"] = tuple(_drift_terms(script, topic, niche))
        words = len(script.split())
        log(f"[{niche['id']}] draft: {words} words, "
            f"{len(MAPPING_RE.findall(script))} mapping statements"
            + (f", OFF-TOPIC: {', '.join(state['drift'])}" if state["drift"] else ""))
        return script

    def review(t, script, asked, min_score):
        """The critic judges taste; drift is objective, so it overrides an approval.
        A model that has just written about threads will happily approve threads."""
        verdict, scores, problems, fix = critic.review(t, script, asked, min_score, niche=niche)
        bad_hook = weak_hook(script)
        if bad_hook:
            problems = [f"weak hook: {bad_hook}"] + problems
            fix = ("Replace the first sentence. It must be a concrete statement -- never a "
                   "question, a stock opener, or a hedge like 'can lead to'. Name what "
                   "visibly breaks, with a number or object: 'divide by 256 and every "
                   "colour comes out one shade dark'. " + fix)
            verdict = "revise"
        drift = _drift_terms(script, t, niche)
        if len(drift) > MAX_DRIFT:
            problems = [f"uses {', '.join(drift)}, which belong to another subject"] + problems
            fix = (f"Remove {', '.join(drift)} and every idea that depends on them; they do "
                   f"not belong to '{t}'. " + fix)
            verdict = "revise"
        return verdict, scores, problems, fix

    script, verdict, scores = critic.refine(topic, write, question=asked, review_fn=review)

    if len(script.split()) < 60:
        raise RuntimeError(f"script too short: {script[:120]}")
    if verdict != "publish":
        raise RuntimeError(
            f"script never passed review ({critic.summarise(scores)}); nothing published. "
            "Publishing filler is what the inauthentic-content policy penalises.")
    log(f"[{niche['id']}] script approved: {critic.summarise(scores)}")
    return script


def generate_terms(topic, script, niche):
    """Footage search terms. MPT derives its own from the subject; ours follow the
    analogy, so the b-roll matches the story instead of the abstract concept."""
    try:
        raw = nim_chat(
            "You pick stock-footage search terms. Respond with 6 comma-separated terms, "
            "1-2 words each, all concrete filmable scenes or objects -- no abstract nouns "
            "like 'concept' or 'technology'. Favour the everyday situation in the script "
            "over the technical subject.\n"
            "Avoid anything that puts branded or commercial products on screen: no brand "
            "names, no logos, no packaged goods, no shop signage, no phone or laptop "
            "screens showing recognisable apps. Footage full of products reads as product "
            "placement to YouTube's advertiser-suitability check and gets the video "
            "demonetised. Prefer people, hands, places, tools and materials.\n"
            "No numbering, no quotes.",
            f"Topic: {topic}\n\nScript: {script}",
            temperature=0.6,
            max_tokens=512,
        )
        terms = [t.strip(" .\"'") for t in raw.replace("\n", ",").split(",")]
        terms = [t for t in terms if t and len(t.split()) <= 3][:6]
        if len(terms) >= 3:
            return ",".join(terms)
    except Exception as e:
        log(f"term generation failed ({type(e).__name__}), letting MPT derive them")
    return None


def _clean_key(v):
    v = (v or "").strip()
    # ponytail: reject the .env.example placeholder so bad secrets don't leak into config
    return v if v and v.lower() != "xxxx" else ""


MATERIAL_FAILURE = ("download video materials", "stage=materials", "found total videos: 0")


def pick_sources(niche):
    """Every configured stock source, in random order. Both time out often enough that
    one of them being down should cost a retry, not the whole run."""
    usable = [n for n, env in (("pexels", "PEXELS_API_KEY"), ("pixabay", "PIXABAY_API_KEY"))
              if _clean_key(os.environ.get(env))]
    if not usable:
        raise RuntimeError("Set PEXELS_API_KEY and/or PIXABAY_API_KEY (non-empty)")
    random.shuffle(usable)
    return usable


def write_mpt_config(niche, source):
    voice = niche.get("voice", DEFAULT_VOICE)
    pexels = _clean_key(os.environ.get("PEXELS_API_KEY"))
    pixabay = _clean_key(os.environ.get("PIXABAY_API_KEY"))
    log(f"[{niche['id']}] video source: {source}, voice: {voice}")
    cfg = f'''[app]
video_source = "{source}"
pexels_api_keys = ["{pexels}"]
pixabay_api_keys = ["{pixabay}"]
video_language = "en-US"
voice_name = "{voice}"
voice_language = "en-US"
llm_provider = "openai"
openai_api_key = "ollama"
openai_base_url = "{os.environ.get('OLLAMA_URL', 'http://localhost:11434').rstrip('/')}/v1"
openai_model_name = "{NIM_MODEL}"
subtitle_provider = "edge"

[ui]
hide_config = true
language = "en"
'''
    (MPT_DIR / "config.toml").write_text(cfg)


def generate_video(topic, niche, source, script=None, terms=None):
    """Run MPT CLI. Everything that matters is passed as a flag: MPT's argparse defaults
    silently override config.toml (the voice default is zh-CN-XiaoxiaoNeural-Female)."""
    start = time.time()
    style = {**SUBTITLE_STYLE, **niche.get("subtitle", {})}
    cmd = [sys.executable, "cli.py", "--video-subject", topic,
           "--video-source", source,
           "--voice-name", niche.get("voice", DEFAULT_VOICE),
           "--font-name", style["font_name"],
           "--font-size", str(style["font_size"]),
           "--subtitle-position", style["subtitle_position"],
           "--text-fore-color", style["text_fore_color"],
           "--stroke-color", style["stroke_color"],
           "--stroke-width", str(style["stroke_width"]),
           "--rounded-subtitle-background" if style["rounded_subtitle_background"]
           else "--no-rounded-subtitle-background",
           # MPT defaults --bgm-type to "random", which mixes in a track from its
           # bundled library. Those tracks draw copyright claims on YouTube, so the
           # videos ship with narration only.
           "--bgm-type", "none", "--bgm-volume", "0"]
    if style["subtitle_position"] == "custom":
        cmd += ["--custom-position", str(style["custom_position"])]
    if script:
        cmd += ["--video-script", script]
    if terms:
        cmd += ["--video-terms", terms]
    result = subprocess.run(cmd, cwd=MPT_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"MPT failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}")

    candidates = [
        p for p in glob.glob(str(MPT_DIR / "storage" / "tasks" / "**" / "final*.mp4"), recursive=True)
        if os.path.getmtime(p) >= start
    ]
    if not candidates:
        raise RuntimeError("MPT finished but no final video found in storage/tasks")
    return max(candidates, key=os.path.getmtime)


HASHTAG_CAP = 5


def _clean_hashtags(tags):
    """Normalize any list-of-strings input into '#word' form: strip leading '#',
    drop non-alphanumerics, lowercase, dedupe, drop empties. Accepts already-
    hashtag'd strings, space-separated bundles, or plain keywords -- so a
    Pexels tag, an LLM output, and a YouTube snippet.tags list can all feed in."""
    out, seen = [], set()
    for t in tags or []:
        if not isinstance(t, str):
            continue
        # Allow bundles like "#one #two #three" that some sources return as one string.
        for part in t.split():
            slug = re.sub(r"[^a-z0-9]", "", part.lstrip("#").lower())
            if not slug or slug in seen:
                continue
            seen.add(slug)
            out.append(f"#{slug}")
    return out


def make_metadata(topic, niche, question=None):
    """Title, description, hashtags. Never let a metadata hiccup discard a rendered
    video -- fall back to the topic.

    Hashtag policy: prefer the source video's tags when the question came from a
    trending video (those tags are already earning views). Top up with LLM-picked
    ones so we always have HASHTAG_CAP total. Niche's evergreen `hashtags` string
    is the last-resort fallback if both live sources fail."""
    source_tags = _clean_hashtags((question or {}).get("hashtags") or [])[:HASHTAG_CAP]
    need_llm_tags = len(source_tags) < HASHTAG_CAP
    schema = ('{"title": "...", "description": "..."'
              + (', "hashtags": ["#tag1", "#tag2", "#tag3"]' if need_llm_tags else "")
              + '}')
    hashtag_rule = (
        " Hashtags: pick 5 short, topic-relevant hashtags a real viewer might "
        "search for. #kebab as one word (no spaces, no punctuation). Prefer "
        "verticals over generic tags -- '#nocodefounder' beats '#tech'."
        if need_llm_tags else ""
    )
    try:
        raw = nim_chat(
            "You write YouTube Shorts metadata. Respond ONLY with JSON: "
            f"{schema}. Title under 90 chars, punchy hook. Description: 2 "
            "sentences + a call to action to follow." + hashtag_rule,
            f"Video topic: {topic}",
            temperature=0.7,
        )
        meta = json.loads(re.sub(r"```json|```", "", raw).strip())
    except Exception as e:
        log(f"metadata generation failed ({type(e).__name__}), using the topic as-is")
        meta = {"title": topic, "description": topic}
    hashtags = list(source_tags)
    for tag in _clean_hashtags(meta.get("hashtags") or []):
        if tag not in hashtags:
            hashtags.append(tag)
        if len(hashtags) >= HASHTAG_CAP:
            break
    if not hashtags:
        # Last resort: the niche's evergreen tags.
        hashtags = _clean_hashtags([niche.get("hashtags", "")])[:HASHTAG_CAP]
    meta["hashtags"] = hashtags
    tags_str = " ".join(hashtags)
    meta["description"] = f'{meta.get("description", topic)}\n\n{tags_str}'.rstrip()
    meta["title"] = meta.get("title", topic)[:95]
    return meta


def youtube_credentials(niche_id):
    """(client_id, client_secret, refresh_token) for one niche.

    YouTube's upload quota is per Google Cloud project, not per channel: one project
    allows roughly six uploads a day whatever the channel. Giving each channel its own
    project (usually its own Google account) multiplies the ceiling, but then each has
    its own OAuth client, and a refresh token only works with the client that minted it.
    So the client id and secret are per niche too, falling back to the shared pair."""
    suffix = niche_id.upper()

    def pick(name):
        value = (os.environ.get(f"{name}_{suffix}") or "").strip()
        return value or (os.environ.get(name) or "").strip()

    refresh = (os.environ.get(f"YT_REFRESH_TOKEN_{suffix}") or "").strip()
    return pick("YT_CLIENT_ID"), pick("YT_CLIENT_SECRET"), ("" if refresh == "xxxx" else refresh)


def upload_youtube(video_path, meta, niche):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    client_id, client_secret, refresh_token = youtube_credentials(niche["id"])
    if not refresh_token:
        log(f"No YT_REFRESH_TOKEN_{niche['id'].upper()} set; skipping YouTube for {niche['id']}")
        return None
    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    yt = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": niche["youtube_tags"],
            "categoryId": "27",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    log(f"YouTube uploaded: https://youtu.be/{resp['id']}")
    return resp["id"]


def tiktok_caption(meta, niche, limit=2200):
    """TikTok has no separate description: caption and hashtags are one 'title' string.
    Uses the dynamic per-video hashtags produced by make_metadata; falls back to the
    niche's static ones if that field is missing (e.g. metadata regen path)."""
    tags = " ".join(meta.get("hashtags") or []).strip()
    if not tags:
        tags = niche.get("tiktok_hashtags", niche.get("hashtags", "")).strip()
    body = re.sub(r"\s*#\S+", "", meta.get("description", "")).strip()
    parts = [p for p in (meta.get("title", "").strip(), body, tags) if p]
    caption = "\n\n".join(parts)
    if len(caption) <= limit:
        return caption
    room = limit - len(tags) - 2
    return f"{caption[:max(room, 0)].rstrip()}\n\n{tags}"[:limit]


def _tiktok_access_token(ck, cs, refresh):
    r = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"client_key": ck, "client_secret": cs, "grant_type": "refresh_token", "refresh_token": refresh},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _tiktok_put(upload_url, video_path, size):
    with open(video_path, "rb") as f:
        r = requests.put(
            upload_url,
            headers={"Content-Range": f"bytes 0-{size-1}/{size}", "Content-Type": "video/mp4"},
            data=f, timeout=600,
        )
    r.raise_for_status()


def _tiktok_direct_post(access, video_path, caption):
    """Direct Post: the only way to attach a caption and hashtags from the API.
    Needs the video.publish scope. Until the app passes TikTok's audit the only
    privacy level an unaudited client may use is SELF_ONLY, so posts land private."""
    r = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
        headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json; charset=UTF-8"},
        timeout=30,
    )
    r.raise_for_status()
    info = r.json()["data"]
    options = info.get("privacy_level_options") or ["SELF_ONLY"]
    wanted = os.environ.get("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY")
    privacy = wanted if wanted in options else options[0]
    if privacy != wanted:
        log(f"TikTok: privacy {wanted} not offered for this account, using {privacy} (offered: {options})")

    size = os.path.getsize(video_path)
    r = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json; charset=UTF-8"},
        json={
            "post_info": {
                "title": caption,
                "privacy_level": privacy,
                "disable_comment": bool(info.get("comment_disabled")),
                "disable_duet": bool(info.get("duet_disabled")),
                "disable_stitch": bool(info.get("stitch_disabled")),
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                            "chunk_size": size, "total_chunk_count": 1},
        },
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"TikTok direct post init failed: {r.status_code} {r.text[:300]}")
    d = r.json()["data"]
    _tiktok_put(d["upload_url"], video_path, size)
    log(f"TikTok: direct posted ({privacy}) with caption, publish_id={d['publish_id']}")
    return d["publish_id"]


def _tiktok_inbox(access, video_path):
    """Inbox draft. No caption field exists on this endpoint -- TikTok expects the
    account owner to write it in the app before publishing."""
    size = os.path.getsize(video_path)
    r = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
        headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json; charset=UTF-8"},
        json={"source_info": {"source": "FILE_UPLOAD", "video_size": size,
                              "chunk_size": size, "total_chunk_count": 1}},
        timeout=60,
    )
    r.raise_for_status()
    d = r.json()["data"]
    _tiktok_put(d["upload_url"], video_path, size)
    log(f"TikTok: queued to inbox as draft, publish_id={d['publish_id']}")
    return d["publish_id"]


def upload_tiktok(video_path, meta, niche):
    """Send the video to TikTok. Two modes:

    inbox (default)  -- draft in the user's inbox, no caption possible, needs only
                        video.upload and works on an unaudited app.
    direct post      -- caption and hashtags included, needs the video.publish scope;
                        set TIKTOK_DIRECT_POST=1. Private until the app is audited.

    Requires TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN_<NICHEID>."""
    ck = os.environ.get("TIKTOK_CLIENT_KEY")
    cs = os.environ.get("TIKTOK_CLIENT_SECRET")
    refresh = os.environ.get(f"TIKTOK_REFRESH_TOKEN_{niche['id'].upper()}")
    if not (ck and cs and refresh):
        return None

    access = _tiktok_access_token(ck, cs, refresh)
    if os.environ.get("TIKTOK_DIRECT_POST", "").strip().lower() in ("1", "true", "yes"):
        try:
            return _tiktok_direct_post(access, video_path, tiktok_caption(meta, niche))
        except Exception as e:
            log(f"TikTok direct post failed ({e}); falling back to an inbox draft")
    return _tiktok_inbox(access, video_path)


def render_with_fallback(topic, niche, script, terms):
    """Try each stock source before giving up. A Pixabay read timeout used to fail the
    whole run with Pexels sitting configured and idle. The script is already written at
    this point, so a retry costs a render, not another round of model calls."""
    sources = pick_sources(niche)
    last = None
    for i, source in enumerate(sources):
        write_mpt_config(niche, source)
        try:
            return generate_video(topic, niche, source, script=script, terms=terms)
        except RuntimeError as e:
            if not any(m in str(e) for m in MATERIAL_FAILURE):
                raise  # a real MPT failure, not the footage provider being down
            last = e
            remaining = sources[i + 1:]
            log(f"[{niche['id']}] {source} returned no footage"
                + (f", retrying with {remaining[0]}" if remaining else ""))
    raise RuntimeError(f"No stock source returned footage (tried {', '.join(sources)}): {last}")


def write_pending_captions(state, keep=10):
    """A phone-readable list of captions for anything still waiting as an inbox draft.
    Posts published through Buffer already carry their caption, so they are skipped."""
    lines = ["# TikTok captions to paste when publishing drafts", ""]
    for u in reversed(state["uploads"][-keep:]):
        if not u.get("tiktok") or not u.get("tiktok_caption"):
            continue
        if u.get("tiktok_via") == "buffer":
            continue
        lines += [f"## {u['ts']} — {u['niche']}", "", "```", u["tiktok_caption"], "```", ""]
    (ROOT / "CAPTIONS.md").write_text("\n".join(lines))


def publish_tiktok(video, meta, niche, caption):
    """Buffer first: it posts through its own TikTok-approved app, so the caption and
    hashtags go out with the video and the post is public. Our own app can do neither --
    inbox drafts carry no caption, and unaudited direct posts are SELF_ONLY. The draft
    path stays as the fallback so a Buffer outage still gets the video onto the phone.

    Returns (ok, via, post_id)."""
    if buffer.enabled():
        try:
            post_id = buffer.publish(video, caption, title=meta.get("title"),
                                     niche_id=niche["id"])
            return True, "buffer", post_id
        except Exception as e:
            log(f"[{niche['id']}] Buffer failed ({type(e).__name__}: {str(e)[:160]}); "
                "falling back to a TikTok inbox draft")
    publish_id = upload_tiktok(video, meta, niche)
    return bool(publish_id), "inbox", publish_id


# edge-tts at +8% lands around 2.6 words per second. A finished video much shorter than
# the script implies the narration was truncated -- a three second clip carrying only the
# opening line reached a channel once, and nothing downstream noticed.
WORDS_PER_SECOND = 2.6
MIN_VIDEO_SECONDS = 20
MIN_DURATION_RATIO = 0.6


def video_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def check_rendered_video(path, script):
    """Refuse a video whose narration does not match the script it was made from."""
    duration = video_duration(path)
    expected = len(script.split()) / WORDS_PER_SECOND
    if duration < MIN_VIDEO_SECONDS or duration < expected * MIN_DURATION_RATIO:
        raise RuntimeError(
            f"rendered video is {duration:.0f}s but the script needs about "
            f"{expected:.0f}s: the narration was cut short, not uploading")
    streams = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0",
         str(path)], capture_output=True, text=True).stdout.split()
    if "audio" not in streams:
        raise RuntimeError("rendered video has no audio track, not uploading")
    log(f"video checks out: {duration:.0f}s for a {len(script.split())}-word script")
    return duration


def _recent_archetypes(state, niche_id, keep=3):
    """The last few Remotion archetypes used by this niche, freshest first. Fed
    into the classifier so the same visual language does not repeat when the
    script honestly fits more than one template."""
    out = []
    for u in reversed(state.get("uploads", [])):
        if u.get("niche") != niche_id:
            continue
        arch = u.get("archetype")
        if arch and arch != "mpt":
            out.append(arch)
            if len(out) >= keep:
                break
    return out


def _episode_counts(state, niche_id):
    """{archetype: past_count} across every upload this niche has shipped. The
    render badge picks past_count+1 for whichever archetype gets classified,
    turning the counter into a real per-format series marker."""
    counts = {}
    for u in state.get("uploads", []):
        if u.get("niche") != niche_id:
            continue
        arch = u.get("archetype")
        if arch and arch != "mpt":
            counts[arch] = counts.get(arch, 0) + 1
    return counts


def render_video(topic, niche, script, question=None, recent_archetypes=(),
                 episode_counts=None):
    """Dispatch to the configured renderer.

      stock     MPT: stock footage under captions, ffmpeg-composited (default)
      remotion  React composition with topic-matched Pexels bg + edge-tts audio;
                falls back to stock if the archetype doesn't match or Remotion errors

    Returns (mp4 path, archetype id or 'mpt'). Both paths run the same duration
    and audio sanity check -- a short narration shouldn't reach upload."""
    mode = niche.get("video_mode", "stock")
    nid = niche["id"]
    if mode == "remotion":
        log(f"[{nid}] ==== RENDER stage (renderer=REMOTION) ====")
        try:
            import remotion_render
            video, archetype = remotion_render.render(
                topic, niche, script, question=question,
                recent_archetypes=recent_archetypes,
                episode_counts=episode_counts)
            check_rendered_video(video, script)
            log(f"[{nid}] ==== RENDER done via REMOTION -> {Path(video).name} ====")
            return video, archetype
        except Exception as e:
            log(f"[{nid}] REMOTION failed ({type(e).__name__}: {str(e)[:160]})")
            log(f"[{nid}] ==== FALLBACK to MPT stock render ====")
    elif mode != "stock":
        raise RuntimeError(f"unknown video_mode {mode!r} (only 'stock'/'remotion' supported)")
    else:
        log(f"[{nid}] ==== RENDER stage (renderer=MPT stock) ====")
    terms = generate_terms(topic, script, niche)
    video = render_with_fallback(topic, niche, script, terms)
    check_rendered_video(video, script)
    log(f"[{nid}] ==== RENDER done via MPT -> {Path(video).name} ====")
    return video, "mpt"


def niche_is_ready(niche):
    """A niche stays dormant until its YouTube channel exists. This lets a niche be
    configured and reviewed before its channel is created, without failing every run."""
    return bool((os.environ.get(f"YT_REFRESH_TOKEN_{niche['id'].upper()}") or "").strip()
                not in ("", "xxxx"))


def used_question_ids(state, niche_id):
    return {u.get("question_id") for u in state.get("uploads", [])
            if u.get("niche") == niche_id and u.get("question_id")}


def run_niche(niche, state):
    if not niche_is_ready(niche):
        log(f"[{niche['id']}] skipped: set YT_REFRESH_TOKEN_{niche['id'].upper()} "
            "once the channel exists")
        return
    used = state["topics"].setdefault(niche["id"], [])
    for _ in range(niche.get("videos_per_run", 1)):
        topic, question = pick_topic(niche, used, used_question_ids(state, niche["id"]))
        script = generate_script(topic, niche, question,
                                 recent_tools=_recent_tools(state, niche["id"]))
        # Per-archetype episode counts. Whichever archetype the script gets
        # classified into, the badge shows 'Q · 07' or 'COST · 03' etc.
        # -- proof each format is a series, not a one-off.
        video, archetype = render_video(
            topic, niche, script, question=question,
            recent_archetypes=_recent_archetypes(state, niche["id"]),
            episode_counts=_episode_counts(state, niche["id"]))
        log(f"[{niche['id']}] Video: {video}")
        meta = make_metadata(topic, niche, question=question)
        caption = tiktok_caption(meta, niche)

        if DRY_RUN:
            # MPT writes into its own storage dir, so copy the result into ./out.
            dest = Path(video)
            if dest.parent.resolve() != OUT_DIR.resolve():
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                dest = OUT_DIR / f"{niche['id']}-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
                shutil.copy(video, dest)
            log(f"[{niche['id']}] DRY_RUN: uploads skipped, video at {dest}")
            log(f"[{niche['id']}] Title: {meta['title']}")
            log(f"[{niche['id']}] TikTok caption:\n{caption}")
            (dest.with_suffix(".txt")).write_text(
                f"topic: {topic}\n\ntitle: {meta['title']}\n\n"
                f"youtube description:\n{meta['description']}\n\ntiktok caption:\n{caption}\n\n"
                f"script:\n{script}\n"
            )
            used.append(topic)
            continue

        yt_id = upload_youtube(video, meta, niche)
        # Record the topic the moment the video is public. Waiting until after TikTok
        # meant a failure there left a published video whose topic was never marked
        # used, so a later run could produce the same idea again.
        entry = {
            "niche": niche["id"], "topic": topic, "title": meta["title"],
            # provenance: which human question this video answers, so it is never
            # answered twice and the channel can show its work
            "question": (question or {}).get("title"),
            "question_id": (question or {}).get("id"),
            "question_url": (question or {}).get("url"),
            "youtube": yt_id, "tiktok": False, "tiktok_via": None,
            "tiktok_post_id": None, "tiktok_caption": caption,
            "archetype": archetype,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        used.append(topic)
        state["uploads"].append(entry)
        save_state(state)

        try:
            tt_ok, tt_via, tt_id = publish_tiktok(video, meta, niche, caption)
            entry.update(tiktok=tt_ok, tiktok_via=tt_via, tiktok_post_id=tt_id)
            if tt_via == "inbox":
                # A draft carries no caption, so keep it for pasting from the phone.
                log(f"[{niche['id']}] TikTok caption to paste:\n{caption}")
        except Exception as e:
            # YouTube already has the video; losing TikTok must not lose the run.
            log(f"[{niche['id']}] TikTok publishing failed: {type(e).__name__}: {str(e)[:160]}")
        save_state(state)
        write_pending_captions(state)
        try:
            os.remove(video)  # keep disk clean
        except OSError:
            pass


RUN_ATTEMPTS = int(os.environ.get("RUN_ATTEMPTS", "3"))


def _is_revoked_token(exc):
    """Google's OAuth library raises RefreshError with 'invalid_grant' when the
    refresh token has been revoked or expired. That state is terminal -- retrying
    burns another full render (~30 min) hitting the same dead credential."""
    return (type(exc).__name__ == "RefreshError"
            and "invalid_grant" in str(exc).lower())


def _open_revoked_token_issue(niche_id, exc):
    """Best-effort: file a GitHub issue so a dead OAuth token is visible without
    scrolling logs. Silent when the workflow lacks GITHUB_TOKEN or issues:write,
    silent when an issue with the same title is already open -- otherwise every
    scheduled run would file another one."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        return
    title = f"[{niche_id}] YouTube OAuth refresh token expired or revoked"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        r = requests.get(
            "https://api.github.com/search/issues",
            headers=headers,
            params={"q": f'repo:{repo} is:issue is:open in:title "{niche_id}" OAuth'},
            timeout=30,
        )
        if r.ok and r.json().get("total_count", 0) > 0:
            log(f"[{niche_id}] auth issue already open: {r.json()['items'][0]['html_url']}")
            return
    except Exception:
        pass  # fall through and try to create anyway
    body = (
        f"`YT_REFRESH_TOKEN_{niche_id.upper()}` is no longer accepted by Google. "
        f"Regenerate locally:\n\n"
        f"```\n"
        f"python3 -m venv /tmp/yt && /tmp/yt/bin/pip install google-auth-oauthlib\n"
        f"NICHE={niche_id} /tmp/yt/bin/python get_youtube_token.py\n"
        f"```\n\n"
        f"Sign in with the Google account that owns the `{niche_id}` YouTube channel, "
        f"then update the `YT_REFRESH_TOKEN_{niche_id.upper()}` repository secret "
        f"with the printed value.\n\n"
        f"Runs will keep failing until this is done. The autopilot skips the render "
        f"stage now when it hits a revoked token, so wasted CI time is minimal.\n\n"
        f"Original error:\n\n```\n{type(exc).__name__}: {str(exc)[:400]}\n```"
    )
    try:
        r = requests.post(
            f"https://api.github.com/repos/{repo}/issues",
            headers=headers,
            json={"title": title, "body": body},
            timeout=30,
        )
        if r.ok:
            log(f"[{niche_id}] opened issue: {r.json().get('html_url')}")
        else:
            log(f"[{niche_id}] could not open issue ({r.status_code}): {r.text[:200]}")
    except Exception as e:
        log(f"[{niche_id}] could not open issue: {type(e).__name__}: {e}")


def run_niche_with_retries(niche, state, attempts=None):
    """Most failures here are other people's outages -- NIM refusing requests, a stock
    provider timing out, Reddit rate limiting. Waiting six hours for the next cron to
    retry wastes a slot, so retry inside the run with a widening gap.

    Revoked OAuth tokens are the exception: they will not un-revoke by themselves, so
    the loop aborts on the first hit and files a GitHub issue instead of burning two
    more full render cycles hitting the same dead credential."""
    attempts = attempts or RUN_ATTEMPTS
    last = None
    for i in range(attempts):
        try:
            run_niche(niche, state)
            return
        except Exception as e:
            last = e
            log(f"[{niche['id']}] attempt {i + 1}/{attempts} failed: {type(e).__name__}: {str(e)[:200]}")
            if _is_revoked_token(e):
                log(f"[{niche['id']}] OAuth token is revoked -- aborting, not retrying")
                _open_revoked_token_issue(niche["id"], e)
                break
            if i < attempts - 1:
                wait = 30 * (i + 1)
                log(f"[{niche['id']}] retrying in {wait}s")
                time.sleep(wait)
    raise last


def main():
    niches = json.loads((ROOT / "niches.json").read_text())["niches"]
    only = [s.strip() for s in os.environ.get("NICHES", "").split(",") if s.strip()]
    if only:
        niches = [n for n in niches if n["id"] in only]
    state = load_state()
    failures = []
    for niche in niches:
        try:
            run_niche_with_retries(niche, state)
        except Exception as e:
            log(f"[{niche['id']}] FAILED: {e}")
            failures.append(niche["id"])
    if failures:
        sys.exit(f"Failed niches: {failures}")
    log("All niches done.")


if __name__ == "__main__":
    main()

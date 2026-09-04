"""Remotion rendering path. Layers on-screen typography and animation over
topic-matched stock footage with edge-tts narration -- same asset mix as MPT,
delivered through React compositions instead of ffmpeg overlays.

Called from autopilot when a niche declares video_mode="remotion". Falls back
to MPT if any step here fails so a niche that opts in never regresses to no
video.

Archetypes: CostTeardown, WorkflowDemo, RedFlagList, StatCard, QuestionAnswer,
BeforeAfter, BuyOrBuild. Each has a distinct visual language and a distinct
required props shape. The pipeline is:

  1. classify_archetype   pick which template best fits the script
  2. extract_props        pull that archetype's props from the narration
  3. generate_narration   edge-tts to public/narration.mp3
  4. fetch_pexels         topic-matched vertical clip to public/bg.mp4
  5. render               shell out to `npx remotion render`
"""
import asyncio, json, os, re, subprocess, time
from pathlib import Path

import requests

from llm import nim_json

ROOT = Path(__file__).resolve().parent
REMOTION_DIR = ROOT / "remotion"
PUBLIC_DIR = REMOTION_DIR / "public"
OUT_DIR = REMOTION_DIR / "out"


def log(msg): print(f"[remotion] {msg}", flush=True)


# ---- archetype registry -----------------------------------------------------

# Composition id in Root.tsx -> required prop keys (from each template's Props
# interface). Missing any required key means the script didn't fit; caller
# falls back to MPT.
ARCHETYPES = {
    # Only the fields the templates actually render on-screen count as required.
    # whatItDoes / catch / reasoning / caveat used to be here; they were dropped
    # when the templates stopped rendering them (narration covers those).
    "CostTeardown": ("hook", "paidTool", "paidPrice", "freeStack", "payoff"),
    "WorkflowDemo": ("scenario", "steps", "cost", "payoff"),
    "RedFlagList": ("intro", "flags", "takeaway"),
    "StatCard": ("setup", "bigNumber", "context", "payoff"),
    "QuestionAnswer": ("question", "tldr", "payoff"),
    "BeforeAfter": ("process", "before", "after", "saving", "payoff"),
    "BuyOrBuild": ("situation", "buy", "build", "recommendation", "payoff"),
    # Star Rising is never chosen by the classifier -- it is forced by autopilot
    # when the run sources its topic from GitHub, because repo/stars/starsNote
    # come from the API rather than from the narration. It is absent from
    # _ARCH_DESCRIPTIONS for that reason.
    "StarRising": ("repo", "tagline", "stars", "payoff"),
}

# Compact archetype label for the ChannelBadge. Paired with a running per-
# archetype counter so a viewer sees "Q · 07" or "COST · 03" -- proof that
# each format is a series, not a one-off.
ARCHETYPE_TAGS = {
    "QuestionAnswer": "Q",
    "CostTeardown": "COST",
    "WorkflowDemo": "FLOW",
    "RedFlagList": "FLAGS",
    "StatCard": "STAT",
    "BeforeAfter": "B/A",
    "BuyOrBuild": "DECIDE",
    "StarRising": "RISING",
}


# ---- narration (edge-tts) --------------------------------------------------

def generate_narration(text, voice, out_path):
    """Edge TTS -> mp3. Voice matches MPT's '<Name>-<Gender>' convention;
    edge-tts wants just the short name."""
    import edge_tts

    short_name = re.sub(r"-(Male|Female)$", "", voice)
    async def go():
        await edge_tts.Communicate(text, short_name, rate="+8%").save(str(out_path))
    asyncio.run(go())
    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise RuntimeError(f"edge-tts produced no audio for voice {short_name}")
    log(f"2/4 TTS       -> {out_path.name} ({out_path.stat().st_size // 1024} KB, "
        f"voice={short_name})")


def audio_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(path)], capture_output=True, text=True)
    return float(r.stdout.strip())


# ---- background footage (Pexels vertical) -----------------------------------

PEXELS_SEARCH = "https://api.pexels.com/videos/search"
FPS = 30
SLOT_SECONDS = 5.0        # target duration each clip appears on screen
SLOT_FRAMES = int(SLOT_SECONDS * FPS)


def _pexels_search(term, key, per_page=15):
    r = requests.get(
        PEXELS_SEARCH, headers={"Authorization": key},
        params={"query": term, "orientation": "portrait",
                "per_page": per_page, "size": "medium"}, timeout=30)
    if r.status_code != 200:
        log(f"pexels {term!r}: {r.status_code}")
        return []
    return r.json().get("videos", [])


def _best_vertical_file(video):
    """Pick the smallest vertical file >= 720p from a Pexels video record."""
    files = [f for f in video.get("video_files", [])
             if f.get("width") and 720 <= f["width"] <= 1440
             and (f.get("height") or 0) >= f.get("width", 0)]
    files.sort(key=lambda f: f.get("width", 9999))
    return files[0] if files else None


def fetch_pexels_clips(terms, target_seconds, out_dir):
    """Download enough vertical clips from Pexels to cover `target_seconds` of
    narration, one clip per SLOT_SECONDS chunk. Returns a list of
    {'file': relative_name, 'durationInFrames': int} that Remotion stitches
    with crossfades. Iterates term-by-term so early terms dominate the
    montage (they matched the topic best)."""
    key = (os.environ.get("PEXELS_API_KEY") or "").strip()
    if not key or key.lower() == "xxxx":
        raise RuntimeError("PEXELS_API_KEY not set")
    # Add SLOT_SECONDS of headroom so the last transition doesn't clip audio.
    slots_needed = max(2, int((target_seconds + SLOT_SECONDS) / SLOT_SECONDS))
    term_list = [t.strip() for t in (terms or "").split(",") if t.strip()]
    if not term_list:
        raise RuntimeError("no search terms to fetch clips for")

    downloaded = []           # [{'file': 'bg-1.mp4', 'durationInFrames': 150}, ...]
    seen_urls = set()
    tried = []
    for term in term_list:
        if len(downloaded) >= slots_needed:
            break
        tried.append(term)
        for video in _pexels_search(term, key):
            if len(downloaded) >= slots_needed:
                break
            picked = _best_vertical_file(video)
            if not picked or picked["link"] in seen_urls:
                continue
            seen_urls.add(picked["link"])
            filename = f"bg-{len(downloaded) + 1}.mp4"
            path = out_dir / filename
            dl = requests.get(picked["link"], timeout=180, stream=True)
            if dl.status_code != 200:
                continue
            with open(path, "wb") as f:
                for chunk in dl.iter_content(1 << 15):
                    f.write(chunk)
            if path.stat().st_size < 100_000:
                path.unlink(missing_ok=True)
                continue
            downloaded.append({"file": filename, "durationInFrames": SLOT_FRAMES})
    if not downloaded:
        raise RuntimeError(f"no Pexels footage matched any of: {tried}")
    total_kb = sum((out_dir / c["file"]).stat().st_size for c in downloaded) // 1024
    log(f"3/4 bg clips  -> {len(downloaded)} clips, {total_kb} KB total, "
        f"~{SLOT_SECONDS:.0f}s each, terms tried={tried}")
    return downloaded


# ---- classify + extract (two LLM calls) -------------------------------------

_ARCH_DESCRIPTIONS = """
  CostTeardown    Script names a paid tool + its bill and proposes a free-tier
                  replacement. Signals: dollar amount, tool name, "replace with".
  WorkflowDemo    Script walks through a concrete automation flow step by step.
                  Signals: "step 1... step 2...", named services chained together.
  RedFlagList     Script enumerates 2-4 warning signs / things to watch for.
                  Signals: "if they say X", "watch out when", numbered warnings.
  StatCard        Script's core is one surprising number with brief context.
                  Signals: single dominant metric, "$X", "N%", "N hours".
  QuestionAnswer  Script directly answers a viewer's question with reasoning.
                  Signals: opens by restating the question, then TL;DR.
  BeforeAfter     Script compares a manual process to an automated one.
                  Signals: "used to take X, now takes Y", side-by-side timings.
  BuyOrBuild      Script weighs paying for a tool vs building it, with a call.
                  Signals: "buy X or build Y", pros/cons, recommendation.
"""


def classify_archetype(topic, script, question, niche, recent_archetypes=()):
    """Pick the best-fitting archetype. Returns a composition id from ARCHETYPES
    or 'unknown' if nothing fits. Recent archetypes are shown to the classifier
    so it prefers a fresh visual language when a script honestly fits more than
    one -- 'we keep saying the same thing in other words' is often the same
    template picked over and over."""
    asked = f'\nViewer asked: "{question}"\n' if question else ""
    avoid = ""
    if recent_archetypes:
        avoid = ("\n\nRecent videos used these archetypes (in order, most recent "
                 f"first): {', '.join(recent_archetypes)}. If the script honestly "
                 "fits a DIFFERENT archetype comparably well, prefer that. Only "
                 "reuse a recent one when nothing else fits.")
    result = nim_json(
        "You classify short-video scripts into ONE archetype. Return the id of the "
        "template that fits best; if none fits well, return 'unknown'. Do not "
        "invent archetype names. Archetypes:\n" + _ARCH_DESCRIPTIONS + avoid +
        '\n\nJSON schema: {"archetype": "<one of the ids above, or unknown>", '
        '"confidence": 0.0-1.0, "why": "..."}',
        f"Topic: {topic}{asked}\n\nScript:\n{script}",
        temperature=0.15, max_tokens=300,
    )
    archetype = (result.get("archetype") or "unknown").strip()
    conf = float(result.get("confidence") or 0)
    if archetype not in ARCHETYPES or conf < 0.5:
        log(f"1/4 classify  -> UNKNOWN ({archetype}, conf {conf:.2f}): "
            f"{(result.get('why') or '')[:80]}")
        return "unknown"
    log(f"1/4 classify  -> {archetype} (conf {conf:.2f})")
    return archetype


# Per-field character caps. Templates render at fixed font sizes -- a 40-char slot
# rendered with a 200-char string wraps off the frame or clips. Caps are enforced
# post-extraction (word-boundary truncate + ellipsis) so a chatty model can't
# overflow; the extract prompt also carries a short reminder so short output is
# the first-choice behavior. Unknown fields are left alone. Keys correspond to
# either the top-level prop or the array/dict item key that carries the text.
_FIELD_CAPS = {
    "hook": 90, "paidTool": 25, "paidPrice": 18, "whatItDoes": 90,
    "freeStack": 40, "catch": 100, "payoff": 100, "setup": 90,
    "bigNumber": 12, "unit": 15, "context": 90, "source": 40,
    "question": 120, "tldr": 100, "reasoning": 90, "caveat": 100,
    "scenario": 100, "cost": 30, "intro": 100, "takeaway": 100,
    "process": 100, "saving": 60, "situation": 100, "recommendation": 20,
    # inside step/flag/pros-cons objects:
    "label": 30, "detail": 90, "quote": 80, "why": 90,
    "step": 40, "time": 15, "name": 25, "pros": 60, "cons": 60,
    # StarRising. repo/stars/starsNote are overwritten with API values after
    # extraction, so their caps only guard a studio-side prop.
    "repo": 40, "tagline": 110, "stars": 12, "starsNote": 60,
    "replaces": 70, "tradeoff": 100,
}


def _cap(text, limit):
    """Word-boundary truncate. Returns text if it fits; otherwise cuts at the last
    space before limit-1, strips trailing punctuation, and appends an ellipsis."""
    if not isinstance(text, str) or len(text) <= limit:
        return text
    cut = text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:—- ")
    return f"{cut or text[:limit - 1]}…"


def _cap_walk(node, key=None):
    """Recurse through the props tree, applying _FIELD_CAPS by field name. Strings
    inside arrays reuse the array's key; strings inside dicts use their own key."""
    if isinstance(node, str):
        limit = _FIELD_CAPS.get(key)
        return _cap(node, limit) if limit else node
    if isinstance(node, dict):
        return {k: _cap_walk(v, k) for k, v in node.items()}
    if isinstance(node, list):
        return [_cap_walk(item, key) for item in node]
    return node


_EXTRACT_SCHEMAS = {
    "CostTeardown":
        '{"hook":"...","paidTool":"...","paidPrice":"...","whatItDoes":"...",'
        '"freeStack":["..."],"catch":"...","payoff":"..."}',
    "WorkflowDemo":
        '{"scenario":"...","steps":[{"label":"...","detail":"..."}],'
        '"cost":"...","payoff":"..."}',
    "RedFlagList":
        '{"intro":"...","flags":[{"quote":"...","why":"..."}],"takeaway":"..."}',
    "StatCard":
        '{"setup":"...","bigNumber":"...","unit":"...","context":"...",'
        '"source":"...","payoff":"..."}',
    "QuestionAnswer":
        '{"question":"...","tldr":"...","reasoning":["..."],"caveat":"...","payoff":"..."}',
    "BeforeAfter":
        '{"process":"...","before":[{"step":"...","time":"..."}],'
        '"after":[{"step":"...","time":"..."}],"saving":"...","payoff":"..."}',
    "BuyOrBuild":
        '{"situation":"...","buy":{"name":"...","cost":"...","pros":["..."],"cons":["..."]},'
        '"build":{"name":"...","cost":"...","pros":["..."],"cons":["..."]},'
        '"recommendation":"buy"|"build","payoff":"..."}',
    # repo/stars/starsNote are deliberately absent: autopilot supplies them from
    # the GitHub API so no model can round a star count on screen.
    "StarRising":
        '{"tagline":"...","replaces":"...","tradeoff":"...","payoff":"..."}',
}


def extract_props(archetype, topic, script, question):
    """Given an archetype, pull that template's exact props from the narration.
    Every string must come from words the script actually contains. Every field
    is capped post-extraction: templates render at fixed font sizes and long
    strings clip off the frame."""
    asked = f'\nViewer asked: "{question}"\n' if question else ""
    result = nim_json(
        f"You extract fields for the {archetype} short-video template from a "
        "finished narration script. Every string must be either verbatim from "
        "the script or a tight paraphrase in the script's voice. Never invent "
        "numbers, tool names, or client stories. If a required field is not "
        "supported by the script, return an empty string for it.\n\n"
        "KEEP EVERY STRING SHORT so it fits its on-screen slot. Headline slots "
        "(paidPrice, bigNumber, unit, cost, time) must be under 20 characters -- "
        "just the number and unit, no prose. Body strings (hook, payoff, tldr, "
        "context, catch, caveat, takeaway) should read as ONE clean sentence and "
        "stay under about 100 characters. Long extraction wrecks the render.\n\n"
        f"JSON schema: {_EXTRACT_SCHEMAS[archetype]}",
        f"Topic: {topic}{asked}\n\nScript:\n{script}",
        temperature=0.15, max_tokens=1000,
    )
    return _cap_walk(result or {})


def merge_props(props, base_props=None, fallback_props=None):
    """Combine extracted props with caller-supplied ones.

    `fallback_props` fill only what the extractor left empty -- a line written
    from the finished script reads better than raw source text. `base_props`
    overwrite unconditionally: they are facts from an API (a star count, a repo
    name) and a model does not get a vote on those. Everything is re-capped
    afterwards because a merged-in value faces the same on-screen slot."""
    merged = dict(props or {})
    for key, value in (fallback_props or {}).items():
        if value and not merged.get(key):
            merged[key] = value
    merged.update({k: v for k, v in (base_props or {}).items() if v not in (None, "")})
    return _cap_walk(merged)


def _is_complete(archetype, props):
    """All required keys present and non-empty (arrays non-empty too)."""
    for k in ARCHETYPES[archetype]:
        v = props.get(k)
        if v is None or v == "" or v == []:
            return False, k
    return True, None


# ---- Remotion invocation ----------------------------------------------------

def render(topic, niche, script, question=None, recent_archetypes=(),
           episode_counts=None, force_archetype=None, base_props=None,
           fallback_props=None):
    """Full Remotion render loop. Returns (mp4 path, archetype id) so the caller
    can record which template was used and avoid reaching for it back-to-back.
    `episode_counts` is a dict {archetype: past_count}; the badge shows
    'past_count + 1' for whichever archetype gets picked -- a per-format
    series counter.

    `force_archetype` skips the classifier: some formats are decided by where the
    topic came from, not by how the script reads (Star Rising is picked because
    the run sourced a GitHub repo). `base_props` OVERWRITE the extracted props --
    a star count from the API must not be re-derived from narration --  while
    `fallback_props` only fill fields the extractor left empty, so a good
    on-screen line written from the script still wins over the raw source text."""
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if force_archetype:
        if force_archetype not in ARCHETYPES:
            raise RuntimeError(f"unknown forced archetype {force_archetype!r}")
        archetype = force_archetype
        log(f"1/4 classify  -> {archetype} (forced by the topic source)")
    else:
        archetype = classify_archetype(topic, script, question, niche, recent_archetypes)
    if archetype == "unknown":
        raise RuntimeError("no Remotion archetype fits this script")
    past = (episode_counts or {}).get(archetype, 0)
    episode = past + 1
    archetype_tag = ARCHETYPE_TAGS.get(archetype, archetype[:4].upper())
    props = merge_props(extract_props(archetype, topic, script, question),
                        base_props, fallback_props)
    ok, missing = _is_complete(archetype, props)
    if not ok:
        raise RuntimeError(f"{archetype} extraction missing required field: {missing}")

    voice = niche.get("voice", "en-US-AndrewMultilingualNeural-Male")
    narration_path = PUBLIC_DIR / "narration.mp3"
    generate_narration(script, voice, narration_path)

    from autopilot import generate_terms
    terms = generate_terms(topic, script, niche) or topic
    # Wipe any bg-*.mp4 from a previous run so the next fetch starts clean.
    for old in PUBLIC_DIR.glob("bg-*.mp4"):
        old.unlink(missing_ok=True)
    audio_secs = audio_duration(narration_path)
    try:
        clips = fetch_pexels_clips(terms, audio_secs, PUBLIC_DIR)
        props["bgClips"] = clips
    except Exception as e:
        log(f"3/4 bg clips  -> SKIPPED ({type(e).__name__}: {str(e)[:100]})")
    props["narration"] = "narration.mp3"
    props["audioDuration"] = audio_secs
    if niche.get("theme"):
        # A niche-supplied theme overrides the codeaz default baked into the template.
        props["theme"] = niche["theme"]
    props["episode"] = episode
    props["archetypeTag"] = archetype_tag
    props["channelName"] = niche.get("channel_label") or niche.get("id")

    ts = time.strftime("%Y%m%d-%H%M%S")
    out_path = OUT_DIR / f"{niche['id']}-{archetype}-{ts}.mp4"
    cmd = [
        "npx", "remotion", "render", "src/index.ts", archetype,
        str(out_path),
        "--props", json.dumps(props),
    ]
    r = subprocess.run(cmd, cwd=REMOTION_DIR, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"remotion render failed:\n{r.stderr[-1500:]}")
    if not out_path.exists():
        raise RuntimeError("remotion finished but produced no mp4")
    log(f"4/4 render    -> {out_path.name} "
        f"({out_path.stat().st_size // (1024*1024)} MB, {props['audioDuration']:.1f}s)")
    return str(out_path), archetype

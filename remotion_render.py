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
    "CostTeardown": ("hook", "paidTool", "paidPrice", "whatItDoes", "freeStack", "catch", "payoff"),
    "WorkflowDemo": ("scenario", "steps", "cost", "payoff"),
    "RedFlagList": ("intro", "flags", "takeaway"),
    "StatCard": ("setup", "bigNumber", "context", "payoff"),
    "QuestionAnswer": ("question", "tldr", "reasoning", "caveat", "payoff"),
    "BeforeAfter": ("process", "before", "after", "saving", "payoff"),
    "BuyOrBuild": ("situation", "buy", "build", "recommendation", "payoff"),
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

def fetch_pexels_vertical(terms, out_path):
    """Download the best vertical clip matching the topic."""
    key = (os.environ.get("PEXELS_API_KEY") or "").strip()
    if not key or key.lower() == "xxxx":
        raise RuntimeError("PEXELS_API_KEY not set")
    tried = []
    for term in [t.strip() for t in (terms or "").split(",") if t.strip()]:
        tried.append(term)
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": key},
            params={"query": term, "orientation": "portrait", "per_page": 15,
                    "size": "medium"}, timeout=30)
        if r.status_code != 200:
            log(f"pexels {term!r}: {r.status_code}")
            continue
        for video in r.json().get("videos", []):
            candidates = [f for f in video.get("video_files", [])
                          if f.get("width") and 720 <= f["width"] <= 1440
                          and (f.get("height") or 0) >= f.get("width", 0)]
            if not candidates:
                continue
            dl = requests.get(candidates[0]["link"], timeout=180, stream=True)
            if dl.status_code != 200:
                continue
            with open(out_path, "wb") as f:
                for chunk in dl.iter_content(1 << 15):
                    f.write(chunk)
            if out_path.stat().st_size > 100_000:
                log(f"3/4 bg video  -> {out_path.name} "
                    f"({out_path.stat().st_size // 1024} KB, term={term!r})")
                return
    raise RuntimeError(f"no Pexels footage matched any of: {tried}")


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


def classify_archetype(topic, script, question, niche):
    """Pick the best-fitting archetype. Returns a composition id from ARCHETYPES
    or 'unknown' if nothing fits."""
    asked = f'\nViewer asked: "{question}"\n' if question else ""
    result = nim_json(
        "You classify short-video scripts into ONE archetype. Return the id of the "
        "template that fits best; if none fits well, return 'unknown'. Do not "
        "invent archetype names. Archetypes:\n" + _ARCH_DESCRIPTIONS +
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
}


def extract_props(archetype, topic, script, question):
    """Given an archetype, pull that template's exact props from the narration.
    Every string must come from words the script actually contains."""
    asked = f'\nViewer asked: "{question}"\n' if question else ""
    result = nim_json(
        f"You extract fields for the {archetype} short-video template from a "
        "finished narration script. Every string must be either verbatim from "
        "the script or a tight paraphrase in the script's voice. Never invent "
        "numbers, tool names, or client stories. If a required field is not "
        "supported by the script, return an empty string for it.\n\n"
        f"JSON schema: {_EXTRACT_SCHEMAS[archetype]}",
        f"Topic: {topic}{asked}\n\nScript:\n{script}",
        temperature=0.15, max_tokens=1000,
    )
    return result or {}


def _is_complete(archetype, props):
    """All required keys present and non-empty (arrays non-empty too)."""
    for k in ARCHETYPES[archetype]:
        v = props.get(k)
        if v is None or v == "" or v == []:
            return False, k
    return True, None


# ---- Remotion invocation ----------------------------------------------------

def render(topic, niche, script, question=None):
    """Full Remotion render loop. Returns the path to the final mp4."""
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    archetype = classify_archetype(topic, script, question, niche)
    if archetype == "unknown":
        raise RuntimeError("no Remotion archetype fits this script")
    props = extract_props(archetype, topic, script, question)
    ok, missing = _is_complete(archetype, props)
    if not ok:
        raise RuntimeError(f"{archetype} extraction missing required field: {missing}")

    voice = niche.get("voice", "en-US-AndrewMultilingualNeural-Male")
    narration_path = PUBLIC_DIR / "narration.mp3"
    generate_narration(script, voice, narration_path)

    from autopilot import generate_terms
    terms = generate_terms(topic, script, niche) or topic
    bg_path = PUBLIC_DIR / "bg.mp4"
    try:
        fetch_pexels_vertical(terms, bg_path)
        props["bgVideo"] = "bg.mp4"
    except Exception as e:
        log(f"3/4 bg video  -> SKIPPED ({type(e).__name__}: {str(e)[:100]})")
        if bg_path.exists():
            bg_path.unlink()
    props["narration"] = "narration.mp3"
    props["audioDuration"] = audio_duration(narration_path)
    if niche.get("theme"):
        # A niche-supplied theme overrides the codeaz default baked into the template.
        props["theme"] = niche["theme"]

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
    return str(out_path)

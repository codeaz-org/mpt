"""Preview one App Rescue episode per format with the production pipeline, publishing
nothing. Run from the mpt checkout: python preview_rescue.py OUT_DIR [format ...]

Each episode lands in OUT_DIR/<format>/ as video.mp4, post.json and preview.txt. To
approve one, move its folder into queue/approved/ (name order = posting order) and
push: the autopilot posts it on the next App Rescue slot, exactly as previewed."""
import json, shutil, sys, time, traceback
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import autopilot, buffer, questions, rescue  # noqa: E402

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
only = sys.argv[2:] or list(rescue.FORMATS)
base = next(n for n in json.loads(Path("niches.json").read_text())["niches"] if n["id"] == "codeaz")

for fmt in only:
    t0 = time.time()
    niche = json.loads(json.dumps(base))
    niche["app_rescue"]["formats"] = [fmt]            # force this format
    print(f"\n===== {fmt} =====", flush=True)
    try:
        ep = rescue.pick(niche, {}, used_question_ids=(),
                         harvest=questions.harvest,
                         matcher=lambda s, u: autopilot.nim_json(s, u, temperature=0.2, max_tokens=700))
        question = rescue.question(ep)
        script = autopilot.generate_script(ep["title"], niche, question, rescue_ep=ep)
        video, arch = autopilot.render_video(
            ep["title"], niche, script, question=question,
            force_archetype="RescueSplit",
            base_props={**rescue.base_props(ep, niche),
                        "seriesTag": autopilot._rescue_series_tag({}, "codeaz", ep)},
            fallback_props=rescue.fallback_props(ep))
        meta = autopilot.make_metadata(ep["title"], niche, rescue_topic=ep)
        caption = autopilot.tiktok_caption(meta, niche)
        li_text, li_link = buffer.linkedin_text(caption)
        dest = out / fmt
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(video, dest / "video.mp4")
        (dest / "post.json").write_text(json.dumps({
            "niche": "codeaz", "format": fmt, "topic_id": ep["topic"]["id"],
            "asked": ep.get("asked"), "title": meta["title"],
            "description": meta["description"], "hashtags": meta.get("hashtags") or [],
        }, indent=2, ensure_ascii=False) + "\n")
        (dest / "preview.txt").write_text(
            f"FORMAT: {fmt}\nTOPIC: {ep['topic']['id']} -- {ep['title']}\n"
            + (f"REAL QUESTION: {ep['asked']['title']} ({ep['asked'].get('source')}, "
               f"{ep['asked'].get('url')})\n" if ep.get("asked") else "")
            + f"\n--- SCRIPT ({len(script.split())} words) ---\n{script}\n"
            f"\n--- YOUTUBE TITLE ---\n{meta['title']}\n"
            f"\n--- YOUTUBE DESCRIPTION ---\n{meta['description']}\n"
            f"\n--- TIKTOK / INSTAGRAM CAPTION ---\n{caption}\n"
            f"\n--- LINKEDIN POST ---\n{li_text}\n\nFIRST COMMENT: {li_link}\n")
        print(f"OK {fmt} in {time.time() - t0:.0f}s", flush=True)
    except Exception as e:
        traceback.print_exc()
        print(f"FAILED {fmt}: {type(e).__name__}: {str(e)[:300]}", flush=True)

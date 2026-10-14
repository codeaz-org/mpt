# MPT Autopilot

Fully automated faceless-channel pipeline: NVIDIA NIM generates a topic per niche, MoneyPrinterTurbo builds the video (free Pexels footage + free Edge TTS), then it auto-publishes to YouTube (free API) and optionally TikTok (Upload-Post). Four niches included in `niches.json`. Topic history is stored in `posted.json` so it never repeats itself.

## One-time setup (~45 min)

1. **API keys (all free):**
   - NVIDIA NIM key at build.nvidia.com (free credits, OpenAI-compatible endpoint).
   - Pexels API key at pexels.com/api.
2. **Create 4 YouTube channels** (they can live under one Google account as brand channels, or separate accounts — separate is safer).
3. **Google Cloud:** create a project, enable *YouTube Data API v3*, create an OAuth client (Desktop type) → gives you `YT_CLIENT_ID` and `YT_CLIENT_SECRET`. Add yourself as a test user on the consent screen.
4. **Per channel**, run `python get_youtube_token.py` locally, sign in as that channel, and save the printed refresh token as `YT_REFRESH_TOKEN_<NICHEID>`.
5. *(Optional, TikTok)* create an upload-post.com account, connect the TikTok accounts using the niche ids as profile names, and set `UPLOAD_POST_API_KEY`. Free tier = 10 uploads/month, so treat TikTok as a teaser channel or upgrade later.

## Choose ONE runtime

### A. GitHub Actions — recommended, free, true autopilot
1. Push this folder to a GitHub repo.
2. Add every key from `.env.example` as a repo **Secret** (Settings → Secrets → Actions).
3. Done. It runs at 06/12/18/23 UTC daily. Each run commits posted.json back to the repo, which persists your topic history and keeps the schedule alive forever (GitHub disables cron on repos inactive 60+ days — this sidesteps that). Make the repo public for unlimited free minutes; secrets stay encrypted regardless. Trigger manually anytime from the Actions tab.

### B. Docker — for a home PC / VPS that stays on
```bash
cp .env.example .env   # fill it in
touch posted.json && echo '{"topics":{},"uploads":[]}' > posted.json
docker compose up -d --build
```

### C. Colab — testing only
Open `colab_autopilot.ipynb`. Free Colab cannot schedule itself; sessions die. Fine for verifying the pipeline, not for autopilot.

## Content sources

Two paths feed the same render-and-publish pipeline, alternating run by run for any niche that enables the second one:

- **Questions** (`questions.py`) — harvests real questions from Reddit, Ask HN, Stack Exchange and Google Autocomplete, and the video answers one of them. Provenance is recorded per upload (`question_id`, `question_url`) so a question is never answered twice.
- **Star Rising** (`repos.py`) — a recurring open-source segment. Pulls repos from the GitHub Search API in two pools: *rising* (created inside `window_days`, ranked by stars per day — raw star counts just resurface whatever was already famous) and *established* (any age, `established_min_stars`+, pushed within `established_maintained_days`, ranked by total stars). Age was never what made a project worth recommending: a five-year-old self-hosted CRM with 20k stars and commits this month is a safer bet than anything three weeks old, and there are far more of them. The two pools are interleaved so a shortlist carries both. Then it drops anything with no usable description or that is reading material rather than software, then an LLM gate keeps only projects a founder or small business could actually run. The chosen repo lands in `posted.json` under `repos` and on the upload entry, so no repo is covered twice, and the last few subjects (with the tool each replaced) are shown to the gate so three different projects are not all sold as "the free Zapier". `star_rising.exclude` blocks projects outright by substring — useful for one the channel has covered to death elsewhere, since repo dedupe only kicks in after something publishes. Star count, language and licence on screen come from the API, never from the narration.

Enable the segment per niche in `niches.json`:

```json
"star_rising": {
  "enabled": true,
  "every_other_run": true,
  "window_days": 90,
  "min_stars": 300,
  "min_description_chars": 40,
  "queries": ["", "topic:self-hosted", "topic:automation", "topic:saas"]
}
```

`every_other_run` alternates with the question pipeline; it is false for codeaz, so every video is a Star Rising episode and the question pipeline is only the fallback for when no repo passes the filters. Each episode burns a repo permanently, so the window settings have to keep pace with the publishing rate -- 3 videos/day is ~90 repos a month, against ~125 candidates at 180 days / 200 stars plus whatever newly trends. `repos.py` logs a warning once fewer than 15 uncovered repos remain. `fallback_to_questions` is false for codeaz, so a run that finds no coverable repo publishes nothing and says so, rather than quietly shipping a video in the paused format; set it true for a niche that would rather always ship something. Its narration prompt is the niche's `repo_script_prompt`, and it always renders through the `StarRising` Remotion template (badge `RISING`). When GitHub has nothing that passes the filters, the run falls back to the question pipeline instead of failing.

## App Rescue segment (codeaz)

Markets [rescue.codeaz.org](https://rescue.codeaz.org): one in every three codeaz videos (`app_rescue.every`) is an App Rescue episode about one real way AI-built apps (Lovable, Bolt, v0, Replit) break, ending on the audit offer. Five formats take turns, each a complete system in `rescue.py`:

| Format | Topic source | On screen | Repeats prevented by |
|---|---|---|---|
| `explainer` | any bank topic | crooked "Broken" symptoms → why → "Fixed" | topic id, per format |
| `check` | bank topics with `check` steps | "Is this your app?" → numbered self-checks | topic id, per format |
| `prompt_fix` | bank topics with `prompts` + `prompt_fails` | the prompts as chat bubbles → why prompting fails → the fix | topic id, per format |
| `checklist` | `checklist_order` in the bank, in order | big item number → how to get it right | item, numbered 1..N |
| `question` | real posts from `question_sources` (r/lovable, r/boltnewbuilders, ...) matched by the model to ONE bank topic, or skipped | the question, quoted, with where it was asked → the answer | question id + topic id |

- **Facts.** `rescue_topics.json` is curated, and an episode's bank entry is the only set of facts its script may state: no client stories, no statistics. A founder question is never answered freehand; if no bank topic answers it, the format is skipped. Self-checks are always on the viewer's own app (dashboard, own code, own test accounts).
- **Rotation.** Formats go in order after the last one used. A format with nothing left this run hands over to the next, so one dry format never costs an upload; if the whole segment is spent, the run uses the niche's normal format. `rescue.py` warns as each pool runs low -- add topics to keep it going.
- **Writing and review.** `app_rescue.script_prompt` holds the shared voice and rules, `format_prompts` each format's shape, and the critic uses the rescue rubric plus that format's `critic_notes`.
- **Video.** Always the `RescueSplit` template, matching the landing page: dark "now" side, an orange line sweeping up to the light "after" side, then the URL. Each format draws its dark side differently and carries its own series badge ("CHECK · 03", "CHECKLIST · 07/20"). No stock footage; text stays inside the Shorts/TikTok/Reels safe area.
- **Captions** carry the link above the hashtags on every platform.
- **Later:** real rescue stories (before/after from client work) become a sixth format once there is real, permitted material. Never invented.

## Instagram Reels (via Buffer)

Every niche can also post to Instagram as a Reel (shared to the feed, marked as AI-generated) through the same Buffer account that posts TikTok. It is off until the niche names its channel; Instagram is never guessed, so one brand's videos cannot land on another's account.

1. Connect the Instagram business/creator account in Buffer.
2. Find its channel id: `BUFFER_ACCESS_TOKEN=... python3 buffer.py channels`
3. Add it as the repo secret `BUFFER_CHANNEL_ID_IG_<NICHE>` (for example `BUFFER_CHANNEL_ID_IG_CODEAZ`) and add the matching line to the workflow env.

The video is hosted once per run and shared by TikTok, Instagram and LinkedIn. A failed Reel is logged and never loses the run.

## LinkedIn page (via Buffer)

Same pattern: connect the company **page** in Buffer, find its id with `python3 buffer.py channels`, and set `BUFFER_CHANNEL_ID_LI_<NICHE>`. Posts go up as native video. The caption keeps three hashtags rather than TikTok's set, and any link (the rescue.codeaz.org line on App Rescue episodes) sits on its own line at the end of the post. Buffer only allows LinkedIn first comments on paid plans; once the plan allows it, set `BUFFER_LINKEDIN_FIRST_COMMENT=1` to move the link into the first comment, where it is widely reported to cost less reach.

## Tuning
- `RUN_HOURS` (Docker) or the cron lines (Actions) control frequency. Default: 4 runs/day × 4 niches = 16 videos/day. **Start with 1–2 runs/day** — brand-new channels that suddenly post 4x/day get flagged as spam.
- Edit `niches.json` to change prompts, voices, hashtags, or add niches; add a matching `YT_REFRESH_TOKEN_<ID>` secret.
- YouTube API default quota allows ~6 uploads/day per Google Cloud project. With 4 niches × 1 video/run you'll hit that at 2 runs/day; use one Cloud project per channel to scale past it.

## Known limits (honesty section)
- TikTok "free at scale" doesn't exist: TikTok's own API posts privately until your app passes an audit, and Upload-Post's free tier is 10/month.
- YouTube may limit monetization of mass-produced content; channels with a consistent editing hook and occasional human-made videos survive far better. Check `posted.json` weekly and prune topic styles that flop.

# CodeAZ facts ledger

Only claim things on this list. If a fact isn't here, say "roughly" / "in most cases"
or don't say it. No invented client names. No invented numbers. If you don't know
the number, don't cite one.

## What codeaz has actually built (public, verifiable)

Rule of use: cite AT MOST ONE of these projects per video, and only when naming it
is the shortest way to prove the claim. Most videos should stand on the answer
alone. Do not open every script with "we built X". If a video is a generic
workflow demo or cost teardown, keep it clean and don't shoehorn a case study in.

- **MPT Autopilot** — an open-source content automation pipeline running in this repo.
  Harvests real developer/founder questions from Reddit, Hacker News, StackOverflow
  and Google Suggest; drafts a short-video script with a swappable free LLM provider
  (NVIDIA NIM, Groq, OpenRouter with fallback); renders a vertical video over free
  Pexels/Pixabay footage using MoneyPrinterTurbo; publishes to YouTube via Google's
  official API and to TikTok via Buffer. Scheduled on GitHub Actions free tier.
  Zero paid infrastructure. Cite when: showing what a single free-tier cron can do
  end-to-end.

- **Ochi pe Șantier** (ochipesantier.vercel.app) — an in-house web platform we built
  that delivers independent, third-party reports from construction sites in Romania,
  giving investors and site owners objective oversight instead of taking the
  contractor's word. Deployed on Vercel. Cite when: talking about verticalised tools
  for non-tech industries (construction, logistics, field ops), or when a viewer's
  question is about building a small SaaS for an offline industry. Do NOT cite in
  generic automation or programming videos.

## Free tiers we've used in production (as of 2025 — verify before quoting a hard number)

- **GitHub Actions**: unlimited minutes for public repos; 2,000 min/month private on
  the free plan. Enough to run a nightly cron for most small businesses.
- **NVIDIA NIM**: free API key at build.nvidia.com; usable for topic drafts and short
  scripts.
- **Groq**: no credit card, generous daily quota — fast enough for near-real-time.
- **Pexels API**: free, ~200 req/hour, no card.
- **Buffer**: free plan handles small posting cadences per social channel.
- **Google Suggest**: no key, no quota shown publicly. Powers AnswerThePublic.

## What we DO NOT claim

- No named clients unless the client has publicly agreed. Don't invent case studies.
- No revenue/ROI numbers unless the number is on this file with a source line.
- No hourly rates ("we charge $X/hr") — pricing varies per engagement.
- No "we've saved companies $X" — unquantified aggregates are marketing lies.

## Approved patterns (things we can honestly say)

- "A small automation like the one running this account cost $0 in infra."
- "Teams pay agencies to teach themselves your stack. That's the invoice we cut."
- "If your dev shop says 'two more weeks' three times, that's a red flag."
- "Free-tier GitHub Actions + a script is enough for most automation needs a small
  business will ever run."

## Fill this in as you go

Each real project we ship, add:
- What was built (one line)
- What was replaced (tool + rough monthly cost)
- What broke and how we fixed it (concrete)

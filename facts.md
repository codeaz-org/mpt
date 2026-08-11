# CodeAZ facts ledger

Rules of use, in order:

1. **Vary the example.** Every video should reach for a DIFFERENT concrete
   reference. The two codeaz projects at the bottom are last-resort — cite one
   AT MOST every fifth video, and only when naming it is the shortest way to
   prove the claim. Most videos should stand on the answer alone, drawing on
   the public facts section for numbers and tool names.
2. **Prefer publicly verifiable facts** (tool pricing on the vendor's own
   site, free-tier limits, well-documented product mechanics) over own-work
   claims. A viewer can double-check Zapier's $29 tier; they can't check us.
3. **Never invent** client names, dollar amounts, revenue, case studies,
   or client stories. If you don't have a real number, say "roughly" or drop
   the number.
4. **Don't repeat yourself across videos.** If the last video used GitHub
   Actions as the example, this one uses something else. Rotate: Cloudflare
   Workers cron, a Vercel cron function, Supabase Edge Functions, a plain
   Python script on a $5 VPS, an n8n instance, a simple crontab on a Hetzner
   box. Same story, different casting.

## Publicly verifiable — safe to cite by name and number

These change over time; skip the specific number if you're not sure it's
still current, but tool names and free-tier limits are stable enough.

### Automation / integration platforms
- **Zapier**: free = 100 tasks/month; paid tiers start ~$19.99–$29.99/mo.
- **Make (Integromat)**: free = 1,000 ops/month; paid from ~$9/mo.
- **n8n**: open source, self-hostable free; Cloud from ~$20/mo.
- **Pipedream**: free = 10,000 invocations/month.
- **IFTTT**: free = 2 applets; paid from ~$3.49/mo.

### No-code / low-code app builders
- **Bubble**: starts ~$32/mo (personal), $134/mo (growth).
- **Retool**: free = 5 users; paid from $10/user/mo.
- **Softr**: free tier available; paid from ~$29/mo.
- **Glide**: free = limited rows; paid from ~$25/mo.
- **Webflow**: free 2 pages; sites from $14/mo, e-commerce from $29/mo.

### Databases / backend-as-a-service
- **Supabase**: free tier = 500 MB DB + 1 GB storage; Pro from $25/mo.
- **Firebase**: free "Spark" plan; pay-as-you-go beyond.
- **Airtable**: free = 1,000 records/base; paid from $10/user/mo.
- **Notion**: free personal; team from $8/user/mo.
- **Neon**: Postgres, free tier available; paid from ~$19/mo.
- **PlanetScale**: MySQL, paid-only since 2024; from $39/mo.

### Hosting / serverless / cron
- **Vercel**: free hobby tier; Pro from $20/user/mo.
- **Netlify**: free tier; paid from $19/user/mo.
- **Cloudflare Workers**: free = 100k requests/day; paid from $5/mo.
- **Cloudflare Pages**: free tier generous; unlimited requests.
- **Railway**: $5 free credit/mo, then pay-as-you-go.
- **Fly.io**: free trial then pay-as-you-go; small VMs ~$2–$5/mo.
- **Render**: free web services (sleep) or from $7/mo.
- **GitHub Actions**: unlimited minutes on public repos; 2,000 min/mo free on private.

### AI / LLM APIs
- **OpenAI GPT-4o mini**: ~$0.15 / 1M input tokens.
- **Anthropic Claude Haiku**: ~$0.25 / 1M input tokens.
- **Groq**: free tier, generous daily rate, no card.
- **OpenRouter**: some `:free` models with ~50 req/day.
- **NVIDIA NIM**: free API key at build.nvidia.com.

### Communication / notifications
- **Slack**: free tier with 90-day message history; paid from $7.25/user/mo.
- **Discord**: free; Nitro from $9.99/mo (not needed for automation).
- **Twilio**: pay-per-use; SMS ~$0.0083 per US message.
- **SendGrid**: free = 100 emails/day; paid from $19.95/mo.
- **Resend**: free = 3,000 emails/mo, 100/day.
- **Buffer**: free = 3 channels, 10 posts each; paid from $6/channel/mo.

### Payments
- **Stripe**: 2.9% + $0.30 per US card charge; no monthly fee.
- **Paddle**: 5% + $0.50 (merchant of record).
- **Lemon Squeezy**: 5% + $0.50 (merchant of record).

### Well-documented public founder stories (fair game to cite)
- **Nomad List (Pieter Levels)**: publicly reported ~$140k+ MRR, run solo.
- **DHH / Basecamp**: publicly write about small-team economics.
- **Indie Hackers milestones page**: catalog of founder-reported revenues.
- **Levels.fyi**: publicly available salary data.

If you cite a number from this list, phrase it as "publicly listed at" or
"publicly reported around" — leaves room for it to have changed.

## What NOT to claim

- No named clients (unless the client has publicly agreed).
- No invented dollar amounts or revenue figures for anyone.
- No hourly rates for codeaz ("we charge $X/hr") — pricing varies per engagement.
- No "we've saved companies $X" or other unquantified aggregates.
- No fabricated success stories, even generic ones.

## Own-work reference (last resort — cite at most 1 in 5 videos)

Only reach for these when a publicly verifiable example doesn't exist or
doesn't fit. Never open a video with them.

- **MPT Autopilot** — open-source content pipeline in this repo. Harvests
  questions, drafts scripts with free LLMs, renders vertical video via
  Remotion, uploads to YouTube + Buffer. Runs on GitHub Actions free tier.
  Cite when: showing what a truly zero-infra content workflow can do.

- **Ochi pe Șantier** (ochipesantier.vercel.app) — in-house Vercel-hosted
  web platform delivering independent third-party construction site reports
  in Romania. Cite when: talking about verticalised tools for non-tech
  industries (construction, logistics, field ops), or a small SaaS for an
  offline industry. Never in generic automation/programming videos.

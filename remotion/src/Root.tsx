import React from "react";
import { Composition } from "remotion";
import { codeazTheme } from "./theme";
import { CostTeardown, CostTeardownProps } from "./CostTeardown";
import { WorkflowDemo, WorkflowDemoProps } from "./WorkflowDemo";
import { RedFlagList, RedFlagListProps } from "./RedFlagList";
import { StatCard, StatCardProps } from "./StatCard";
import { QuestionAnswer, QuestionAnswerProps } from "./QuestionAnswer";
import { BeforeAfter, BeforeAfterProps } from "./BeforeAfter";
import { BuyOrBuild, BuyOrBuildProps } from "./BuyOrBuild";
import { StarRising, StarRisingProps } from "./StarRising";

const FPS = 30;
const DEFAULT_SECONDS = 30;

/** Every composition sizes itself from `props.audioDuration` (set by autopilot
 *  from the actual TTS mp3). Falls back to DEFAULT_SECONDS in the studio. */
const calcMeta = <P extends { audioDuration?: number }>({ props }: { props: P }) => {
  const seconds = (props.audioDuration ?? DEFAULT_SECONDS) + 1;
  return { durationInFrames: Math.round(seconds * FPS), props };
};

const shared = {
  fps: FPS, width: 1080, height: 1920,
  durationInFrames: Math.round(DEFAULT_SECONDS * FPS),
};

const costTeardownDefaults: CostTeardownProps = {
  hook: "Zapier just charged you $29 to run 100 tasks.",
  paidTool: "Zapier", paidPrice: "$29/mo",
  whatItDoes: "It runs a script when something happens. That's the whole product.",
  freeStack: ["GitHub Actions cron", "One Python script", "Slack webhook"],
  catch: "Setup takes an afternoon. No UI. You own the ops.",
  payoff: "Want the UI? Keep Zapier. Want to own it? This is a weekend.",
  // No bgClips in defaults -- production sets these from Pexels at render time.
  // For a studio preview WITH bg, drop a vertical mp4 in public/ and add:
  //   bgClips: [{ file: "your.mp4" }],
  theme: codeazTheme,
};

const workflowDemoDefaults: WorkflowDemoProps = {
  scenario: "A boutique agency wanted Slack pings when a Stripe invoice went overdue.",
  steps: [
    { label: "Stripe webhook", detail: "Fires on every invoice status change." },
    { label: "GitHub Actions", detail: "Free cron runs the check every hour." },
    { label: "Python filter", detail: "Only sends when status = 'overdue' AND >7 days." },
    { label: "Slack webhook", detail: "Posts to #billing with the client name + amount." },
  ],
  cost: "$0 / month, one afternoon to build",
  payoff: "Same alert Zapier charges $29/mo for. You wrote 40 lines of Python.",
};

const redFlagListDefaults: RedFlagListProps = {
  intro: "Your dev shop is stalling if they keep saying these three things.",
  flags: [
    { quote: "We just need two more weeks.", why: "Third time? They're rebuilding without telling you." },
    { quote: "It's an architectural decision.", why: "Translation: they picked a stack they don't know." },
    { quote: "The client changed the requirements.", why: "You didn't. They just discovered scope late." },
  ],
  takeaway: "Ask to see the last commit. If it's a Friday and it's config, run.",
};

const statCardDefaults: StatCardProps = {
  setup: "The average Zapier user pays for one automation and uses it for nothing else.",
  bigNumber: "$348", unit: "/ year",
  context: "Cost of a single-workflow Zapier subscription for 12 months.",
  source: "Zapier public pricing, 2025",
  payoff: "One Python script, one free GitHub Actions cron, same job. Zero dollars.",
};

const questionAnswerDefaults: QuestionAnswerProps = {
  question: "Can GitHub Actions replace a paid cron service?",
  tldr: "For most small business jobs, yes — free and reliable enough.",
  reasoning: [
    "2,000 free minutes/month on private repos, unlimited on public.",
    "Runs on schedule or on demand. Same triggers as paid crons.",
    "Failures email you, no extra alerting setup.",
  ],
  caveat: "Not sub-minute scheduling, and 6-hour job cap. Everything else fits.",
  payoff: "If your cron runs hourly or daily, GitHub Actions is enough.",
};

const beforeAfterDefaults: BeforeAfterProps = {
  process: "Reconciling weekly Stripe payouts into a spreadsheet.",
  before: [
    { step: "Download CSV from Stripe", time: "10 min" },
    { step: "Match rows to bookings", time: "45 min" },
    { step: "Copy totals into sheet", time: "20 min" },
    { step: "Email the accountant", time: "5 min" },
  ],
  after: [
    { step: "Weekly cron runs the script", time: "0 min" },
    { step: "Sheet updates automatically", time: "0 min" },
  ],
  saving: "80 min/week",
  payoff: "That's a full workday every month you now spend somewhere else.",
};

const buyOrBuildDefaults: BuyOrBuildProps = {
  situation: "You need a small internal admin panel for your ops team.",
  buy: {
    name: "Retool",
    cost: "$10 / user / mo",
    pros: ["Ship in a day", "No hosting", "Auth for free"],
    cons: ["Vendor lock-in", "Costs scale per user", "Limited off-happy-path"],
  },
  build: {
    name: "Custom + Vercel",
    cost: "one week + $0 / mo",
    pros: ["You own it", "Change anything", "No per-seat cost"],
    cons: ["You own the ops", "Longer to first version"],
  },
  recommendation: "buy",
  payoff: "Under 20 users, buy. Above, build. That's it.",
  audioDuration: 24, theme: codeazTheme,
};

const starRisingDefaults: StarRisingProps = {
  repo: "documenso/documenso",
  tagline: "Open-source DocuSign alternative: send, sign and store documents you host yourself.",
  stars: "6.1k", starsNote: "~140 a day · TypeScript · AGPL-3.0",
  replaces: "A per-seat e-signature subscription",
  tradeoff: "You run the server, the mailer and the backups.",
  payoff: "Signing under 200 documents a month? This pays for itself in one quarter.",
  audioDuration: 24, theme: codeazTheme,
};

export const Root: React.FC = () => (
  <>
    <Composition
      id="CostTeardown" component={CostTeardown} {...shared}
      defaultProps={costTeardownDefaults} calculateMetadata={calcMeta}
    />
    <Composition
      id="WorkflowDemo" component={WorkflowDemo} {...shared}
      defaultProps={workflowDemoDefaults} calculateMetadata={calcMeta}
    />
    <Composition
      id="RedFlagList" component={RedFlagList} {...shared}
      defaultProps={redFlagListDefaults} calculateMetadata={calcMeta}
    />
    <Composition
      id="StatCard" component={StatCard} {...shared}
      defaultProps={statCardDefaults} calculateMetadata={calcMeta}
    />
    <Composition
      id="QuestionAnswer" component={QuestionAnswer} {...shared}
      defaultProps={questionAnswerDefaults} calculateMetadata={calcMeta}
    />
    <Composition
      id="BeforeAfter" component={BeforeAfter} {...shared}
      defaultProps={beforeAfterDefaults} calculateMetadata={calcMeta}
    />
    <Composition
      id="BuyOrBuild" component={BuyOrBuild} {...shared}
      defaultProps={buyOrBuildDefaults} calculateMetadata={calcMeta}
    />
    <Composition
      id="StarRising" component={StarRising} {...shared}
      defaultProps={starRisingDefaults} calculateMetadata={calcMeta}
    />
  </>
);

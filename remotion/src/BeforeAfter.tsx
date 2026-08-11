/**
 * Before / After. Manual process (red timings) → automated version (green
 * timings) → the saving. Visual comparison; works for any "we replaced X hours
 * of work with Y minutes" story.
 */
import React from "react";
import {
  AbsoluteFill, Sequence, Audio, staticFile, useVideoConfig,
} from "remotion";
import { BgClip, Theme, codeazTheme } from "./theme";
import { familyFor } from "./lib/fonts";
import { Background, Eyebrow } from "./lib/chrome";
import { HookLine, BigNumber } from "./lib/blocks";
import { useEnter } from "./lib/anims";

export interface BeforeAfterProps {
  process: string;             // "Reconciling Stripe payouts each week"
  before: { step: string; time: string }[];  // 3-4 steps with time each
  after: { step: string; time: string }[];   // typically 1-2 steps
  saving: string;              // "Saves ~6 hours a week."
  payoff: string;
  bgClips?: BgClip[];
  narration?: string;
  audioDuration?: number;
  theme?: Theme;
}

const ColumnCard: React.FC<{
  title: string; steps: { step: string; time: string }[];
  color: string; theme: Theme; startFrame: number;
}> = ({ title, steps, color, theme, startFrame }) => (
  <div style={{
    flex: 1,
    padding: "40px 36px",
    backgroundColor: theme.colors.bgAlt,
    borderRadius: theme.radius,
    borderTop: `4px solid ${color}`,
    ...useEnter(startFrame),
  }}>
    <div style={{
      fontFamily: familyFor(theme.fonts.mono),
      fontSize: 28, color: color, letterSpacing: 3,
      textTransform: "uppercase", marginBottom: 30,
    }}>{title}</div>
    {steps.map((s, i) => (
      <div key={i} style={{
        marginBottom: 20, ...useEnter(startFrame + 15 + i * 12),
      }}>
        <div style={{
          fontFamily: familyFor(theme.fonts.mono),
          fontSize: 32, color: color, marginBottom: 4,
        }}>{s.time}</div>
        <div style={{
          fontSize: 34, color: theme.colors.fg, lineHeight: 1.25,
        }}>{s.step}</div>
      </div>
    ))}
  </div>
);

const ProcessScene: React.FC<{ text: string; theme: Theme }> = ({ text, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow tag="B/A/01" label="TASK" theme={theme} />
    <HookLine text={text} theme={theme} size={78} />
  </AbsoluteFill>
);

const CompareScene: React.FC<{
  before: BeforeAfterProps["before"];
  after: BeforeAfterProps["after"];
  theme: Theme;
}> = ({ before, after, theme }) => (
  <AbsoluteFill style={{ padding: 80, paddingTop: 140, justifyContent: "center" }}>
    <Eyebrow tag="B/A/02" label="BEFORE  AFTER" theme={theme} />
    <div style={{ display: "flex", gap: 30, marginTop: 40 }}>
      <ColumnCard title="Before" steps={before} color={theme.colors.bad} theme={theme} startFrame={0} />
      <ColumnCard title="After" steps={after} color={theme.colors.good} theme={theme} startFrame={30} />
    </div>
  </AbsoluteFill>
);

const SavingScene: React.FC<{ saving: string; payoff: string; theme: Theme }> = ({
  saving, payoff, theme,
}) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center", alignItems: "flex-start" }}>
    <Eyebrow tag="B/A/03" label="SAVED" theme={theme} />
    <BigNumber value={saving} theme={theme} color={theme.colors.good} size={120} />
    <div style={{ marginTop: 60, maxWidth: 900 }}>
      <HookLine text={payoff} theme={theme} size={60} fromFrame={40} />
    </div>
  </AbsoluteFill>
);

export const BeforeAfter: React.FC<BeforeAfterProps> = (props) => {
  const theme = props.theme || codeazTheme;
  const { durationInFrames: total } = useVideoConfig();
  const processEnd = Math.round(total * 0.15);
  const compareEnd = Math.round(total * 0.72);
  return (
    <Background theme={theme} bgClips={props.bgClips}>
      {props.narration && <Audio src={staticFile(props.narration)} />}
      <Sequence from={0} durationInFrames={processEnd}>
        <ProcessScene text={props.process} theme={theme} />
      </Sequence>
      <Sequence from={processEnd} durationInFrames={compareEnd - processEnd}>
        <CompareScene before={props.before} after={props.after} theme={theme} />
      </Sequence>
      <Sequence from={compareEnd}>
        <SavingScene saving={props.saving} payoff={props.payoff} theme={theme} />
      </Sequence>
    </Background>
  );
};

/**
 * Workflow Demo archetype. A concrete automation flow: opener scenario, N
 * numbered steps that tick on in sequence with connecting arrows, the total
 * cost line, and a repeatable payoff.
 */
import React from "react";
import {
  AbsoluteFill, Sequence, Audio, staticFile, useVideoConfig,
} from "remotion";
import { Theme, codeazTheme } from "./theme";
import { familyFor } from "./lib/fonts";
import { Background, Eyebrow } from "./lib/chrome";
import { HookLine, MetaLine } from "./lib/blocks";
import { useEnter } from "./lib/anims";

export interface WorkflowDemoProps {
  scenario: string;            // "A boutique agency wanted to DM Slack when a Stripe invoice went overdue."
  steps: { label: string; detail: string }[];   // 3-5 items
  cost: string;                // "$0 / month, one afternoon to build"
  payoff: string;
  bgVideo?: string;
  narration?: string;
  audioDuration?: number;
  theme?: Theme;
}

const ScenarioScene: React.FC<{ text: string; theme: Theme }> = ({ text, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow tag="FLOW/01" label="THE ASK" theme={theme} />
    <HookLine text={text} theme={theme} size={78} />
  </AbsoluteFill>
);

const StepsScene: React.FC<{
  steps: { label: string; detail: string }[]; theme: Theme;
}> = ({ steps, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow tag="FLOW/02" label="THE BUILD" theme={theme} />
    {steps.map((s, i) => (
      <div key={i} style={{ marginBottom: 40, ...useEnter(15 + i * 22) }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 24 }}>
          <div style={{
            fontFamily: familyFor(theme.fonts.mono),
            fontSize: 44, color: theme.colors.accent, minWidth: 80,
          }}>{String(i + 1).padStart(2, "0")}</div>
          <div>
            <div style={{
              fontFamily: familyFor(theme.fonts.display),
              fontSize: 58, fontWeight: 700, color: theme.colors.fg,
              letterSpacing: -1, marginBottom: 6,
            }}>{s.label}</div>
            <div style={{
              fontSize: 32, color: theme.colors.muted, lineHeight: 1.35, maxWidth: 780,
            }}>{s.detail}</div>
          </div>
        </div>
        {i < steps.length - 1 && (
          <div style={{
            marginLeft: 40, marginTop: 12, height: 30, width: 2,
            backgroundColor: `${theme.colors.accent}44`,
          }} />
        )}
      </div>
    ))}
  </AbsoluteFill>
);

const CostPayoffScene: React.FC<{ cost: string; payoff: string; theme: Theme }> = ({
  cost, payoff, theme,
}) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow tag="FLOW/03" label="THE COST" theme={theme} />
    <div style={{
      fontFamily: familyFor(theme.fonts.mono),
      fontSize: 68, color: theme.colors.good, letterSpacing: -1, marginBottom: 80,
      ...useEnter(0),
    }}>{cost}</div>
    <HookLine text={payoff} theme={theme} size={68} fromFrame={40} />
  </AbsoluteFill>
);

export const WorkflowDemo: React.FC<WorkflowDemoProps> = (props) => {
  const theme = props.theme || codeazTheme;
  const { durationInFrames: total } = useVideoConfig();
  const scenarioEnd = Math.round(total * 0.15);
  const stepsEnd = Math.round(total * 0.72);
  return (
    <Background theme={theme} bgVideo={props.bgVideo}>
      {props.narration && <Audio src={staticFile(props.narration)} />}
      <Sequence from={0} durationInFrames={scenarioEnd}>
        <ScenarioScene text={props.scenario} theme={theme} />
      </Sequence>
      <Sequence from={scenarioEnd} durationInFrames={stepsEnd - scenarioEnd}>
        <StepsScene steps={props.steps} theme={theme} />
      </Sequence>
      <Sequence from={stepsEnd}>
        <CostPayoffScene cost={props.cost} payoff={props.payoff} theme={theme} />
      </Sequence>
    </Background>
  );
};

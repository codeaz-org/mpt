/**
 * Stat Card. One giant surprising number front-and-centre, context underneath,
 * source noted, payoff at the end. The pattern-interrupt of the pool.
 */
import React from "react";
import {
  AbsoluteFill, Sequence, Audio, staticFile, useVideoConfig,
} from "remotion";
import { BgClip, Theme, codeazTheme } from "./theme";
import { familyFor } from "./lib/fonts";
import { Background, Eyebrow } from "./lib/chrome";
import { HookLine, MetaLine, BigNumber } from "./lib/blocks";
import { useEnter } from "./lib/anims";

export interface StatCardProps {
  setup: string;          // "SaaS founders leave this much on the table every month:"
  bigNumber: string;      // "$14,400" or "42%"
  unit?: string;          // "/ month" or "of teams"
  context: string;        // one-line explanation of what the number is
  source?: string;        // "source: Pexels 2025 pricing" or verifiable citation
  payoff: string;
  bgClips?: BgClip[];
  narration?: string;
  audioDuration?: number;
  theme?: Theme;
}

const SetupScene: React.FC<{ text: string; theme: Theme }> = ({ text, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow tag="STAT/01" label="THE NUMBER" theme={theme} />
    <HookLine text={text} theme={theme} size={82} />
  </AbsoluteFill>
);

const NumberScene: React.FC<{
  value: string; unit?: string; context: string; source?: string; theme: Theme;
}> = ({ value, unit, context, source, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center", alignItems: "center" }}>
    <div style={{
      display: "flex", alignItems: "baseline", gap: 24, marginBottom: 60,
      ...useEnter(0),
    }}>
      <BigNumber value={value} theme={theme} color={theme.colors.highlight} size={280} />
      {unit && (
        <div style={{
          fontFamily: familyFor(theme.fonts.mono),
          fontSize: 60, color: theme.colors.muted, letterSpacing: -1,
        }}>{unit}</div>
      )}
    </div>
    <div style={{ maxWidth: 900, textAlign: "center" }}>
      <MetaLine text={context} theme={theme} fromFrame={30} size={44} />
    </div>
    {source && (
      <div style={{
        marginTop: 60,
        fontFamily: familyFor(theme.fonts.mono),
        fontSize: 24, color: theme.colors.muted, opacity: 0.7,
        letterSpacing: 2, textTransform: "uppercase",
        ...useEnter(60),
      }}>{source}</div>
    )}
  </AbsoluteFill>
);

const PayoffScene: React.FC<{ text: string; theme: Theme }> = ({ text, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow tag="STAT/03" label="WHY IT MATTERS" theme={theme} />
    <HookLine text={text} theme={theme} size={72} />
  </AbsoluteFill>
);

export const StatCard: React.FC<StatCardProps> = (props) => {
  const theme = props.theme || codeazTheme;
  const { durationInFrames: total } = useVideoConfig();
  const setupEnd = Math.round(total * 0.20);
  const numberEnd = Math.round(total * 0.72);
  return (
    <Background theme={theme} bgClips={props.bgClips}>
      {props.narration && <Audio src={staticFile(props.narration)} />}
      <Sequence from={0} durationInFrames={setupEnd}>
        <SetupScene text={props.setup} theme={theme} />
      </Sequence>
      <Sequence from={setupEnd} durationInFrames={numberEnd - setupEnd}>
        <NumberScene
          value={props.bigNumber} unit={props.unit}
          context={props.context} source={props.source} theme={theme}
        />
      </Sequence>
      <Sequence from={numberEnd}>
        <PayoffScene text={props.payoff} theme={theme} />
      </Sequence>
    </Background>
  );
};

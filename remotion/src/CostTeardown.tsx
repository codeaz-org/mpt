/**
 * Cost Teardown archetype. Names a paid tool + bill, shows the free-tier stack
 * that replaces it, lands a decision-framed payoff.
 */
import React from "react";
import {
  AbsoluteFill, Sequence, Audio, staticFile,
  useVideoConfig, useCurrentFrame, interpolate,
} from "remotion";
import { BgClip, Theme, codeazTheme } from "./theme";
import { familyFor } from "./lib/fonts";
import { Background, Eyebrow } from "./lib/chrome";
import { HookLine, BigNumber } from "./lib/blocks";
import { useEnter, useLinearProgress } from "./lib/anims";

export interface CostTeardownProps {
  hook: string;
  paidTool: string;
  paidPrice: string;
  whatItDoes?: string;        // ignored on-screen; narration covers
  freeStack: string[];
  catch?: string;             // ignored on-screen; narration covers
  payoff: string;
  bgClips?: BgClip[];
  narration?: string;
  audioDuration?: number;
  theme?: Theme;
  episode?: number;
  archetypeTag?: string;
  channelName?: string;
}

const HookScene: React.FC<{ text: string; theme: Theme }> = ({ text, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow label="TEARDOWN" theme={theme} />
    <HookLine text={text} theme={theme} />
  </AbsoluteFill>
);

// Tool name small, price huge with a strike, that's it. No 'what it does' line -- the
// narration explains what the tool does. On screen, just the pain.
const PaidToolScene: React.FC<{
  tool: string; price: string; theme: Theme;
}> = ({ tool, price, theme }) => {
  const strikeWidth = useLinearProgress(30, 25) * 100;
  return (
    <AbsoluteFill style={{ padding: 100, justifyContent: "center", alignItems: "flex-start" }}>
      <div style={{ position: "relative", ...useEnter(0) }}>
        <div style={{
          fontFamily: familyFor(theme.fonts.mono),
          fontSize: 48, color: theme.colors.muted, marginBottom: 16,
          textTransform: "uppercase", letterSpacing: 2,
        }}>{tool}</div>
        <div style={{ position: "relative" }}>
          <BigNumber value={price} theme={theme} color={theme.colors.bad} size={220} />
          <div style={{
            position: "absolute", top: "50%", left: 0,
            height: 12, backgroundColor: theme.colors.bad,
            width: `${strikeWidth}%`,
            transform: "translateY(-50%) rotate(-3deg)",
          }} />
        </div>
      </div>
    </AbsoluteFill>
  );
};

// First replacement only. If the model returns a list we take the winner -- one
// clean answer beats a wall of tags.
const FreeStackScene: React.FC<{ items: string[]; theme: Theme }> = ({ items, theme }) => {
  const winner = (items || [])[0] || "";
  return (
    <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
      <div style={{
        fontFamily: familyFor(theme.fonts.mono),
        fontSize: 40, color: theme.colors.muted,
        marginBottom: 40, letterSpacing: 3, textTransform: "uppercase",
        ...useEnter(0),
      }}>Replace with</div>
      <HookLine text={winner} theme={theme} size={132} />
      <div style={{
        marginTop: 60,
        fontFamily: familyFor(theme.fonts.mono),
        fontSize: 72, fontWeight: 700, color: theme.colors.good,
        ...useEnter(30),
      }}>$0 / month</div>
    </AbsoluteFill>
  );
};

// Payoff only. Old scene stacked a 'catch:' line above -- the narration says it.
const PayoffScene: React.FC<{ payoff: string; theme: Theme }> = ({ payoff, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow label="TAKEAWAY" theme={theme} accent={theme.colors.highlight} />
    <HookLine text={payoff} theme={theme} size={84} />
  </AbsoluteFill>
);

export const CostTeardown: React.FC<CostTeardownProps> = (props) => {
  const theme = props.theme || codeazTheme;
  const { durationInFrames: total } = useVideoConfig();
  const hookEnd = Math.round(total * 0.10);
  const paidEnd = Math.round(total * 0.30);
  const stackEnd = Math.round(total * 0.67);
  return (
    <Background theme={theme} bgClips={props.bgClips}
      episode={props.episode} archetypeTag={props.archetypeTag} channelName={props.channelName}>
      {props.narration && <Audio src={staticFile(props.narration)} />}
      <Sequence from={0} durationInFrames={hookEnd}>
        <HookScene text={props.hook} theme={theme} />
      </Sequence>
      <Sequence from={hookEnd} durationInFrames={paidEnd - hookEnd}>
        <PaidToolScene tool={props.paidTool} price={props.paidPrice} theme={theme} />
      </Sequence>
      <Sequence from={paidEnd} durationInFrames={stackEnd - paidEnd}>
        <FreeStackScene items={props.freeStack} theme={theme} />
      </Sequence>
      <Sequence from={stackEnd}>
        <PayoffScene payoff={props.payoff} theme={theme} />
      </Sequence>
    </Background>
  );
};

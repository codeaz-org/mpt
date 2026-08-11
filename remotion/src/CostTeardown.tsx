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
import { HookLine, MetaLine, BigNumber, ListRow } from "./lib/blocks";
import { useEnter, useLinearProgress } from "./lib/anims";

export interface CostTeardownProps {
  hook: string;
  paidTool: string;
  paidPrice: string;
  whatItDoes: string;
  freeStack: string[];
  catch: string;
  payoff: string;
  bgClips?: BgClip[];
  narration?: string;
  audioDuration?: number;
  theme?: Theme;
}

const HookScene: React.FC<{ text: string; theme: Theme }> = ({ text, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow tag="COST/01" label="TEARDOWN" theme={theme} />
    <HookLine text={text} theme={theme} />
  </AbsoluteFill>
);

const PaidToolScene: React.FC<{
  tool: string; price: string; what: string; theme: Theme;
}> = ({ tool, price, what, theme }) => {
  const strikeWidth = useLinearProgress(30, 25) * 100;
  return (
    <AbsoluteFill style={{ padding: 100, justifyContent: "center", alignItems: "flex-start" }}>
      <div style={{ position: "relative", ...useEnter(0) }}>
        <div style={{
          fontFamily: familyFor(theme.fonts.mono),
          fontSize: 44, color: theme.colors.muted, marginBottom: 12,
          textTransform: "uppercase", letterSpacing: 2,
        }}>{tool}</div>
        <div style={{ position: "relative" }}>
          <BigNumber value={price} theme={theme} color={theme.colors.bad} />
          <div style={{
            position: "absolute", top: "50%", left: 0,
            height: 12, backgroundColor: theme.colors.bad,
            width: `${strikeWidth}%`,
            transform: "translateY(-50%) rotate(-3deg)",
          }} />
        </div>
      </div>
      <div style={{ marginTop: 60 }}>
        <MetaLine text={what} theme={theme} fromFrame={70} />
      </div>
    </AbsoluteFill>
  );
};

const FreeStackScene: React.FC<{ items: string[]; theme: Theme }> = ({ items, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <div style={{
      fontSize: 52, color: theme.colors.muted, marginBottom: 40, ...useEnter(0),
    }}>Replace it with:</div>
    {items.map((item, i) => (
      <ListRow key={i} label={item} theme={theme} fromFrame={20 + i * 25} />
    ))}
    <div style={{
      marginTop: 60,
      fontFamily: familyFor(theme.fonts.mono),
      fontSize: 60, fontWeight: 700, color: theme.colors.good,
      ...useEnter(20 + items.length * 25 + 10),
    }}>$0 / month</div>
  </AbsoluteFill>
);

const PayoffScene: React.FC<{ catch: string; payoff: string; theme: Theme }> = ({
  catch: honesty, payoff, theme,
}) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <div style={{
      fontSize: 44, color: theme.colors.muted, marginBottom: 60,
      lineHeight: 1.35, ...useEnter(0),
    }}>
      <span style={{
        color: theme.colors.bad, fontFamily: familyFor(theme.fonts.mono),
        marginRight: 12, textTransform: "uppercase", letterSpacing: 2,
      }}>catch:</span>{honesty}
    </div>
    <HookLine text={payoff} theme={theme} size={68} fromFrame={80} />
  </AbsoluteFill>
);

export const CostTeardown: React.FC<CostTeardownProps> = (props) => {
  const theme = props.theme || codeazTheme;
  const { durationInFrames: total } = useVideoConfig();
  const hookEnd = Math.round(total * 0.10);
  const paidEnd = Math.round(total * 0.30);
  const stackEnd = Math.round(total * 0.67);
  return (
    <Background theme={theme} bgClips={props.bgClips}>
      {props.narration && <Audio src={staticFile(props.narration)} />}
      <Sequence from={0} durationInFrames={hookEnd}>
        <HookScene text={props.hook} theme={theme} />
      </Sequence>
      <Sequence from={hookEnd} durationInFrames={paidEnd - hookEnd}>
        <PaidToolScene tool={props.paidTool} price={props.paidPrice} what={props.whatItDoes} theme={theme} />
      </Sequence>
      <Sequence from={paidEnd} durationInFrames={stackEnd - paidEnd}>
        <FreeStackScene items={props.freeStack} theme={theme} />
      </Sequence>
      <Sequence from={stackEnd}>
        <PayoffScene catch={props.catch} payoff={props.payoff} theme={theme} />
      </Sequence>
    </Background>
  );
};

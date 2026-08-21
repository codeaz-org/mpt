/**
 * Buy vs Build. Two side-by-side decision cards -- cost, pros, cons -- with
 * one highlighted as the recommendation. Great for "should I use Bubble or
 * hire a dev" style questions.
 */
import React from "react";
import {
  AbsoluteFill, Sequence, Audio, staticFile, useVideoConfig,
} from "remotion";
import { BgClip, Theme, codeazTheme } from "./theme";
import { familyFor } from "./lib/fonts";
import { Background, Eyebrow } from "./lib/chrome";
import { HookLine } from "./lib/blocks";
import { useEnter } from "./lib/anims";

export interface BuyOrBuildProps {
  situation: string;
  buy: { name: string; cost: string; pros: string[]; cons: string[] };
  build: { name: string; cost: string; pros: string[]; cons: string[] };
  recommendation: "buy" | "build";
  payoff: string;
  bgClips?: BgClip[];
  narration?: string;
  audioDuration?: number;
  theme?: Theme;
  episode?: number;
  channelName?: string;
}

const SituationScene: React.FC<{ text: string; theme: Theme }> = ({ text, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow label="THE SITUATION" theme={theme} />
    <HookLine text={text} theme={theme} size={78} />
  </AbsoluteFill>
);

const DecisionCard: React.FC<{
  title: string; label: string; opt: BuyOrBuildProps["buy"]; theme: Theme;
  chosen: boolean; startFrame: number;
}> = ({ title, label, opt, theme, chosen, startFrame }) => (
  <div style={{
    flex: 1,
    padding: "40px 36px",
    backgroundColor: chosen ? `${theme.colors.accent}18` : theme.colors.bgAlt,
    borderRadius: theme.radius,
    border: chosen ? `2px solid ${theme.colors.accent}` : `1px solid ${theme.colors.fg}12`,
    ...useEnter(startFrame),
  }}>
    <div style={{
      fontFamily: familyFor(theme.fonts.mono),
      fontSize: 24, color: chosen ? theme.colors.accent : theme.colors.muted,
      letterSpacing: 3, textTransform: "uppercase", marginBottom: 10,
    }}>{label}</div>
    <div style={{
      fontFamily: familyFor(theme.fonts.display),
      fontSize: 56, fontWeight: 700, color: theme.colors.fg, marginBottom: 24,
    }}>{title}</div>
    <div style={{
      fontFamily: familyFor(theme.fonts.mono),
      fontSize: 38, color: chosen ? theme.colors.accent : theme.colors.fg,
      marginBottom: 32,
    }}>{opt.cost}</div>
    <ul style={{ listStyle: "none", padding: 0 }}>
      {opt.pros.map((p, i) => (
        <li key={`p-${i}`} style={{
          fontSize: 30, color: theme.colors.fg, marginBottom: 12,
          display: "flex", gap: 12,
        }}>
          <span style={{ color: theme.colors.good, fontWeight: 700 }}>+</span>{p}
        </li>
      ))}
      {opt.cons.map((c, i) => (
        <li key={`c-${i}`} style={{
          fontSize: 30, color: theme.colors.muted, marginBottom: 12,
          display: "flex", gap: 12,
        }}>
          <span style={{ color: theme.colors.bad, fontWeight: 700 }}>−</span>{c}
        </li>
      ))}
    </ul>
  </div>
);

const CompareScene: React.FC<{
  buy: BuyOrBuildProps["buy"]; build: BuyOrBuildProps["build"];
  recommendation: "buy" | "build"; theme: Theme;
}> = ({ buy, build, recommendation, theme }) => (
  <AbsoluteFill style={{ padding: 60, paddingTop: 120, justifyContent: "center" }}>
    <Eyebrow label="THE OPTIONS" theme={theme} />
    <div style={{ display: "flex", gap: 24, marginTop: 30 }}>
      <DecisionCard
        title={buy.name} label="Buy" opt={buy} theme={theme}
        chosen={recommendation === "buy"} startFrame={0}
      />
      <DecisionCard
        title={build.name} label="Build" opt={build} theme={theme}
        chosen={recommendation === "build"} startFrame={25}
      />
    </div>
  </AbsoluteFill>
);

const PayoffScene: React.FC<{ text: string; theme: Theme }> = ({ text, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow label="THE CALL" theme={theme} accent={theme.colors.highlight} />
    <HookLine text={text} theme={theme} size={68} />
  </AbsoluteFill>
);

export const BuyOrBuild: React.FC<BuyOrBuildProps> = (props) => {
  const theme = props.theme || codeazTheme;
  const { durationInFrames: total } = useVideoConfig();
  const situationEnd = Math.round(total * 0.15);
  const compareEnd = Math.round(total * 0.78);
  return (
    <Background theme={theme} bgClips={props.bgClips}
      episode={props.episode} channelName={props.channelName}>
      {props.narration && <Audio src={staticFile(props.narration)} />}
      <Sequence from={0} durationInFrames={situationEnd}>
        <SituationScene text={props.situation} theme={theme} />
      </Sequence>
      <Sequence from={situationEnd} durationInFrames={compareEnd - situationEnd}>
        <CompareScene
          buy={props.buy} build={props.build}
          recommendation={props.recommendation} theme={theme}
        />
      </Sequence>
      <Sequence from={compareEnd}>
        <PayoffScene text={props.payoff} theme={theme} />
      </Sequence>
    </Background>
  );
};

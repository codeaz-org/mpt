/**
 * Red-Flag List. An enumerated warning card set -- "your dev shop is stalling
 * if they say these three things." Each flag is a quote + why-it-matters card
 * that ticks on in sequence. Highly forwardable format.
 */
import React from "react";
import {
  AbsoluteFill, Sequence, Audio, staticFile, useVideoConfig,
} from "remotion";
import { Theme, codeazTheme } from "./theme";
import { familyFor } from "./lib/fonts";
import { Background, Eyebrow } from "./lib/chrome";
import { HookLine, QuoteCard } from "./lib/blocks";
import { useEnter } from "./lib/anims";

export interface RedFlagListProps {
  intro: string;         // "Your dev shop is stalling if they keep saying these things."
  flags: { quote: string; why: string }[];  // exactly 3, ideally
  takeaway: string;
  bgVideo?: string;
  narration?: string;
  audioDuration?: number;
  theme?: Theme;
}

const IntroScene: React.FC<{ text: string; theme: Theme }> = ({ text, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow tag="FLAGS/01" label="RED FLAGS" theme={theme} />
    <HookLine text={text} theme={theme} />
  </AbsoluteFill>
);

const FlagsScene: React.FC<{
  flags: { quote: string; why: string }[]; theme: Theme;
}> = ({ flags, theme }) => (
  <AbsoluteFill style={{ padding: 100, paddingTop: 140, justifyContent: "flex-start" }}>
    <Eyebrow tag="FLAGS/02" label="WATCH FOR" theme={theme} />
    {flags.map((f, i) => (
      <div key={i} style={{ display: "flex", gap: 24 }}>
        <div style={{
          fontFamily: familyFor(theme.fonts.mono),
          fontSize: 44, color: theme.colors.bad, minWidth: 70,
          paddingTop: 40, ...useEnter(i * 30),
        }}>{String(i + 1).padStart(2, "0")}</div>
        <div style={{ flex: 1 }}>
          <QuoteCard quote={f.quote} why={f.why} theme={theme} fromFrame={i * 30} />
        </div>
      </div>
    ))}
  </AbsoluteFill>
);

const TakeawayScene: React.FC<{ text: string; theme: Theme }> = ({ text, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow tag="FLAGS/03" label="WHAT TO DO" theme={theme} />
    <HookLine text={text} theme={theme} size={72} />
  </AbsoluteFill>
);

export const RedFlagList: React.FC<RedFlagListProps> = (props) => {
  const theme = props.theme || codeazTheme;
  const { durationInFrames: total } = useVideoConfig();
  const introEnd = Math.round(total * 0.15);
  const flagsEnd = Math.round(total * 0.78);
  return (
    <Background theme={theme} bgVideo={props.bgVideo}>
      {props.narration && <Audio src={staticFile(props.narration)} />}
      <Sequence from={0} durationInFrames={introEnd}>
        <IntroScene text={props.intro} theme={theme} />
      </Sequence>
      <Sequence from={introEnd} durationInFrames={flagsEnd - introEnd}>
        <FlagsScene flags={props.flags} theme={theme} />
      </Sequence>
      <Sequence from={flagsEnd}>
        <TakeawayScene text={props.takeaway} theme={theme} />
      </Sequence>
    </Background>
  );
};

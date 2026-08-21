/**
 * Question / Answer. Shows the viewer's exact question as a chat-bubble card,
 * then a punchy TL;DR, then 2-3 reasoning bullets, then an honest caveat and
 * payoff. Most flexible archetype -- fits nearly any founder question.
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

export interface QuestionAnswerProps {
  question: string;
  tldr: string;               // one-sentence answer -- the only thing on-screen for the answer
  reasoning?: string[];       // ignored on-screen; narration covers these
  caveat?: string;            // ignored on-screen; narration covers
  payoff: string;
  bgClips?: BgClip[];
  narration?: string;
  audioDuration?: number;
  theme?: Theme;
  episode?: number;
  channelName?: string;
}

const QuestionScene: React.FC<{ text: string; theme: Theme }> = ({ text, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow label="ASKED" theme={theme} />
    <div style={{
      padding: "44px 48px",
      backgroundColor: theme.colors.bgAlt,
      borderRadius: theme.radius,
      borderLeft: `6px solid ${theme.colors.accent}`,
      ...useEnter(0),
    }}>
      <div style={{
        fontFamily: familyFor(theme.fonts.display),
        fontSize: 64, fontWeight: 600, color: theme.colors.fg,
        lineHeight: 1.2,
      }}>{text}</div>
    </div>
  </AbsoluteFill>
);

// One line. No bullets. The reasoning is narration; the frame is a headline.
const AnswerScene: React.FC<{ tldr: string; theme: Theme }> = ({ tldr, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow label="ANSWER" theme={theme} />
    <HookLine text={tldr} theme={theme} size={96} />
  </AbsoluteFill>
);

// Payoff only. Caveat was reading as a second body on-screen -- narration covers it.
const PayoffScene: React.FC<{ payoff: string; theme: Theme }> = ({ payoff, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow label="TAKEAWAY" theme={theme} accent={theme.colors.highlight} />
    <HookLine text={payoff} theme={theme} size={84} />
  </AbsoluteFill>
);

export const QuestionAnswer: React.FC<QuestionAnswerProps> = (props) => {
  const theme = props.theme || codeazTheme;
  const { durationInFrames: total } = useVideoConfig();
  const qEnd = Math.round(total * 0.22);
  const aEnd = Math.round(total * 0.75);
  return (
    <Background theme={theme} bgClips={props.bgClips}
      episode={props.episode} channelName={props.channelName}>
      {props.narration && <Audio src={staticFile(props.narration)} />}
      <Sequence from={0} durationInFrames={qEnd}>
        <QuestionScene text={props.question} theme={theme} />
      </Sequence>
      <Sequence from={qEnd} durationInFrames={aEnd - qEnd}>
        <AnswerScene tldr={props.tldr} theme={theme} />
      </Sequence>
      <Sequence from={aEnd}>
        <PayoffScene payoff={props.payoff} theme={theme} />
      </Sequence>
    </Background>
  );
};

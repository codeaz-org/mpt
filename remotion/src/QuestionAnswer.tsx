/**
 * Question / Answer. Shows the viewer's exact question as a chat-bubble card,
 * then a punchy TL;DR, then 2-3 reasoning bullets, then an honest caveat and
 * payoff. Most flexible archetype -- fits nearly any founder question.
 */
import React from "react";
import {
  AbsoluteFill, Sequence, Audio, staticFile, useVideoConfig,
} from "remotion";
import { Theme, codeazTheme } from "./theme";
import { familyFor } from "./lib/fonts";
import { Background, Eyebrow } from "./lib/chrome";
import { HookLine, MetaLine, ListRow } from "./lib/blocks";
import { useEnter } from "./lib/anims";

export interface QuestionAnswerProps {
  question: string;
  tldr: string;               // one-sentence answer
  reasoning: string[];        // 2-3 short bullets
  caveat: string;             // honest tradeoff / edge case
  payoff: string;
  bgVideo?: string;
  narration?: string;
  audioDuration?: number;
  theme?: Theme;
}

const QuestionScene: React.FC<{ text: string; theme: Theme }> = ({ text, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow tag="Q/01" label="ASKED" theme={theme} />
    <div style={{
      padding: "40px 44px",
      backgroundColor: theme.colors.bgAlt,
      borderRadius: theme.radius,
      borderLeft: `6px solid ${theme.colors.accent}`,
      ...useEnter(0),
    }}>
      <div style={{
        fontFamily: familyFor(theme.fonts.display),
        fontSize: 60, fontWeight: 600, color: theme.colors.fg,
        lineHeight: 1.2,
      }}>{text}</div>
    </div>
  </AbsoluteFill>
);

const AnswerScene: React.FC<{
  tldr: string; reasoning: string[]; theme: Theme;
}> = ({ tldr, reasoning, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow tag="Q/02" label="ANSWER" theme={theme} />
    <HookLine text={tldr} theme={theme} size={76} />
    <div style={{ marginTop: 60 }}>
      {reasoning.map((r, i) => (
        <ListRow
          key={i} label={r} theme={theme} chipColor={theme.colors.accent}
          fromFrame={30 + i * 20}
        />
      ))}
    </div>
  </AbsoluteFill>
);

const CaveatPayoffScene: React.FC<{
  caveat: string; payoff: string; theme: Theme;
}> = ({ caveat, payoff, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <div style={{
      fontSize: 40, color: theme.colors.muted, marginBottom: 60,
      lineHeight: 1.35, ...useEnter(0),
    }}>
      <span style={{
        color: theme.colors.highlight,
        fontFamily: familyFor(theme.fonts.mono),
        marginRight: 12, textTransform: "uppercase", letterSpacing: 2,
      }}>caveat:</span>{caveat}
    </div>
    <HookLine text={payoff} theme={theme} size={64} fromFrame={60} />
  </AbsoluteFill>
);

export const QuestionAnswer: React.FC<QuestionAnswerProps> = (props) => {
  const theme = props.theme || codeazTheme;
  const { durationInFrames: total } = useVideoConfig();
  const qEnd = Math.round(total * 0.22);
  const aEnd = Math.round(total * 0.75);
  return (
    <Background theme={theme} bgVideo={props.bgVideo}>
      {props.narration && <Audio src={staticFile(props.narration)} />}
      <Sequence from={0} durationInFrames={qEnd}>
        <QuestionScene text={props.question} theme={theme} />
      </Sequence>
      <Sequence from={qEnd} durationInFrames={aEnd - qEnd}>
        <AnswerScene tldr={props.tldr} reasoning={props.reasoning} theme={theme} />
      </Sequence>
      <Sequence from={aEnd}>
        <CaveatPayoffScene caveat={props.caveat} payoff={props.payoff} theme={theme} />
      </Sequence>
    </Background>
  );
};

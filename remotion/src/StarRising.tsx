/**
 * Star Rising. The recurring open-source segment: one repo that is gaining
 * stars fast, what it takes over, what it costs to run, who should try it.
 *
 * Unlike the other archetypes, its props are not all extracted from the
 * narration -- repo, stars, starsNote and the URL come from the GitHub API via
 * autopilot, so the numbers on screen are the numbers GitHub reported and no
 * model gets a chance to round them.
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

export interface StarRisingProps {
  repo: string;             // owner/name, straight from the API
  tagline: string;          // one line on what it does
  stars: string;            // "4.2k" -- formatted by repos.stars_label
  starsNote?: string;       // "~120 a day · TypeScript · MIT"
  replaces?: string;        // the paid tool or manual process it takes over
  tradeoff?: string;        // the honest catch; narration carries the detail
  payoff: string;
  bgClips?: BgClip[];
  narration?: string;
  audioDuration?: number;
  theme?: Theme;
  episode?: number;
  archetypeTag?: string;
  channelName?: string;
}

/** owner/name in mono, with the owner dimmed so the project name reads first. */
const RepoName: React.FC<{ repo: string; theme: Theme }> = ({ repo, theme }) => {
  const cut = repo.indexOf("/");
  const owner = cut > 0 ? repo.slice(0, cut + 1) : "";
  const name = cut > 0 ? repo.slice(cut + 1) : repo;
  return (
    <div style={{
      fontFamily: familyFor(theme.fonts.mono),
      fontSize: 62, fontWeight: 700, letterSpacing: -1,
      lineHeight: 1.1, marginBottom: 28, wordBreak: "break-word",
      ...useEnter(0),
    }}>
      <span style={{ color: theme.colors.muted }}>{owner}</span>
      <span style={{ color: theme.colors.fg }}>{name}</span>
    </div>
  );
};

const RepoScene: React.FC<{ repo: string; tagline: string; theme: Theme }> =
  ({ repo, tagline, theme }) => (
    <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
      <Eyebrow label="Star Rising" theme={theme} />
      <div style={{
        padding: "44px 48px",
        backgroundColor: theme.colors.bgAlt,
        borderRadius: theme.radius,
        borderLeft: `6px solid ${theme.colors.accent}`,
        ...useEnter(0),
      }}>
        <RepoName repo={repo} theme={theme} />
        <MetaLine text={tagline} theme={theme} size={40} fromFrame={4} />
      </div>
    </AbsoluteFill>
  );

/** The velocity beat: the number is why this repo and not another one. */
const StarsScene: React.FC<{ stars: string; note?: string; theme: Theme }> =
  ({ stars, note, theme }) => (
    <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
      <Eyebrow label="Stars" theme={theme} accent={theme.colors.highlight} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 24 }}>
        <BigNumber value={stars} theme={theme} color={theme.colors.highlight} size={200} />
        <div style={{
          fontFamily: familyFor(theme.fonts.mono),
          fontSize: 56, color: theme.colors.muted,
        }}>★</div>
      </div>
      {note && <MetaLine text={note} theme={theme} size={42} fromFrame={6} />}
    </AbsoluteFill>
  );

const ReplacesScene: React.FC<{ replaces?: string; tradeoff?: string; theme: Theme }> =
  ({ replaces, tradeoff, theme }) => (
    <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
      <Eyebrow label={replaces ? "Takes over" : "The catch"} theme={theme} />
      {replaces
        ? <HookLine text={replaces} theme={theme} size={84} />
        : <HookLine text={tradeoff || ""} theme={theme} size={76} />}
      {replaces && tradeoff && (
        <div style={{ marginTop: 40 }}>
          <MetaLine text={tradeoff} theme={theme} size={40} fromFrame={8} />
        </div>
      )}
    </AbsoluteFill>
  );

const PayoffScene: React.FC<{ payoff: string; theme: Theme }> = ({ payoff, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow label="Worth a look if" theme={theme} accent={theme.colors.good} />
    <HookLine text={payoff} theme={theme} size={84} />
  </AbsoluteFill>
);

export const StarRising: React.FC<StarRisingProps> = (props) => {
  const theme = props.theme || codeazTheme;
  const { durationInFrames: total } = useVideoConfig();
  // Four beats. The repo card holds longest -- the viewer is reading a name
  // they have never seen and needs it on screen while the hook is narrated.
  const repoEnd = Math.round(total * 0.30);
  const starsEnd = Math.round(total * 0.52);
  const replacesEnd = Math.round(total * 0.78);
  return (
    <Background theme={theme} bgClips={props.bgClips}
      episode={props.episode} archetypeTag={props.archetypeTag} channelName={props.channelName}>
      {props.narration && <Audio src={staticFile(props.narration)} />}
      <Sequence from={0} durationInFrames={repoEnd}>
        <RepoScene repo={props.repo} tagline={props.tagline} theme={theme} />
      </Sequence>
      <Sequence from={repoEnd} durationInFrames={starsEnd - repoEnd}>
        <StarsScene stars={props.stars} note={props.starsNote} theme={theme} />
      </Sequence>
      <Sequence from={starsEnd} durationInFrames={replacesEnd - starsEnd}>
        <ReplacesScene replaces={props.replaces} tradeoff={props.tradeoff} theme={theme} />
      </Sequence>
      <Sequence from={replacesEnd}>
        <PayoffScene payoff={props.payoff} theme={theme} />
      </Sequence>
    </Background>
  );
};

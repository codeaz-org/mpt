/**
 * Star Rising. The recurring open-source segment: one repo that is gaining
 * stars fast, what you get for free, what it takes over, who should try it.
 *
 * The episode opens on the hook -- the free capability, phrased as a question
 * the viewer wants answered -- and then shows the actual GitHub page panning
 * slowly, because a video about someone else's project that never shows the
 * project is asking to be believed rather than proving anything.
 *
 * Unlike the other archetypes, its props are not all extracted from the
 * narration: repo, stars, starsNote and the screenshot come from the GitHub API
 * and a headless-Chrome capture, so nothing on screen is a model's paraphrase
 * of a number.
 */
import React from "react";
import {
  AbsoluteFill, Img, Sequence, Audio, staticFile, interpolate,
  useCurrentFrame, useVideoConfig,
} from "remotion";
import { BgClip, Theme, codeazTheme } from "./theme";
import { familyFor } from "./lib/fonts";
import { Background, Eyebrow } from "./lib/chrome";
import { HookLine, MetaLine, BigNumber } from "./lib/blocks";
import { useEnter } from "./lib/anims";

export interface StarRisingProps {
  hook: string;             // the free-capability question that opens the video
  repo: string;             // owner/name, straight from the API
  tagline: string;          // one line on what it does
  stars: string;            // "4.2k" -- formatted by repos.stars_label
  starsNote?: string;       // "~120 a day · TypeScript · MIT"
  replaces?: string;        // the paid tool or manual process it takes over
  tradeoff?: string;        // the honest catch; narration carries the detail
  payoff: string;
  screenshot?: string;      // repo page capture in public/, panned on screen
  screenshotHeight?: number;
  screenshotWidth?: number;
  bgClips?: BgClip[];
  narration?: string;
  audioDuration?: number;
  theme?: Theme;
  episode?: number;
  archetypeTag?: string;
  channelName?: string;
}

/** Opening beat: the question, big. No repo name yet -- the viewer has to want
 *  the answer before the name means anything to them. */
const HookScene: React.FC<{ hook: string; theme: Theme }> = ({ hook, theme }) => (
  <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
    <Eyebrow label="Free, if you host it" theme={theme} accent={theme.colors.good} />
    <HookLine text={hook} theme={theme} size={92} />
  </AbsoluteFill>
);

/** owner/name in mono, with the owner dimmed so the project name reads first. */
const RepoName: React.FC<{ repo: string; theme: Theme; size?: number }> =
  ({ repo, theme, size = 48 }) => {
    const cut = repo.indexOf("/");
    const owner = cut > 0 ? repo.slice(0, cut + 1) : "";
    const name = cut > 0 ? repo.slice(cut + 1) : repo;
    return (
      <div style={{
        fontFamily: familyFor(theme.fonts.mono),
        fontSize: size, fontWeight: 700, letterSpacing: -1,
        lineHeight: 1.1, wordBreak: "break-word",
      }}>
        <span style={{ color: theme.colors.muted }}>{owner}</span>
        <span style={{ color: theme.colors.fg }}>{name}</span>
      </div>
    );
  };

/**
 * The repo page itself, in a browser frame, panning slowly down through the
 * README for the whole scene. The pan is linear and deliberately unhurried --
 * the point is that the viewer can read it, not that it moves.
 */
const ScreenshotScene: React.FC<{
  repo: string; file: string; imgWidth: number; imgHeight: number;
  tagline: string; theme: Theme;
}> = ({ repo, file, imgWidth, imgHeight, tagline, theme }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  // Frame geometry: a browser window centred in the 1080x1920 canvas.
  const frameWidth = 880;
  const frameHeight = 1180;
  const chromeHeight = 72;
  const viewportHeight = frameHeight - chromeHeight;
  // The capture is 1280 wide; scaling it to the frame decides how tall it renders,
  // and therefore how far there is to travel.
  const scale = frameWidth / imgWidth;
  const scaledHeight = imgHeight * scale;
  const travel = Math.max(0, scaledHeight - viewportHeight);
  // Hold briefly on the top of the page before moving, so the repo header and
  // star count register before the README slides up.
  const holdFrames = Math.min(30, Math.round(durationInFrames * 0.12));
  const offset = interpolate(
    frame, [holdFrames, durationInFrames], [0, -travel],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill style={{ padding: 100, justifyContent: "center", alignItems: "center" }}>
      <div style={{ width: frameWidth, marginBottom: 28, ...useEnter(0) }}>
        <RepoName repo={repo} theme={theme} />
        <div style={{ fontSize: 30, color: theme.colors.muted, marginTop: 10 }}>
          {tagline}
        </div>
      </div>
      <div style={{
        width: frameWidth, height: frameHeight,
        borderRadius: theme.radius + 4,
        overflow: "hidden",
        backgroundColor: theme.colors.bgAlt,
        border: `1px solid ${theme.colors.fg}1a`,
        boxShadow: "0 30px 80px rgba(0,0,0,0.55)",
        ...useEnter(3),
      }}>
        {/* Browser chrome: three dots and the URL, so the shot reads as a real
            page rather than a floating image. */}
        <div style={{
          height: chromeHeight, display: "flex", alignItems: "center", gap: 12,
          padding: "0 24px", backgroundColor: theme.colors.bg,
          borderBottom: `1px solid ${theme.colors.fg}14`,
        }}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
            <span key={c} style={{
              width: 14, height: 14, borderRadius: 999, backgroundColor: c, opacity: 0.85,
            }} />
          ))}
          <div style={{
            marginLeft: 16, flex: 1,
            fontFamily: familyFor(theme.fonts.mono),
            fontSize: 24, color: theme.colors.muted,
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>github.com/{repo}</div>
        </div>
        <div style={{ height: viewportHeight, overflow: "hidden", position: "relative" }}>
          <Img
            src={staticFile(file)}
            style={{
              position: "absolute", top: 0, left: 0,
              width: frameWidth,
              transform: `translateY(${offset}px)`,
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Fallback for the beat when no screenshot was captured: the repo card that
 *  the format used before, so a failed capture costs proof, never the episode. */
const RepoCardScene: React.FC<{ repo: string; tagline: string; theme: Theme }> =
  ({ repo, tagline, theme }) => (
    <AbsoluteFill style={{ padding: 100, justifyContent: "center" }}>
      <Eyebrow label="The project" theme={theme} />
      <div style={{
        padding: "44px 48px",
        backgroundColor: theme.colors.bgAlt,
        borderRadius: theme.radius,
        borderLeft: `6px solid ${theme.colors.accent}`,
        ...useEnter(0),
      }}>
        <RepoName repo={repo} theme={theme} size={62} />
        <div style={{ marginTop: 24 }}>
          <MetaLine text={tagline} theme={theme} size={40} fromFrame={4} />
        </div>
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
  // Five beats. The screenshot holds the longest by design: it is the proof,
  // and a pan that outruns the reader proves nothing.
  const hookEnd = Math.round(total * 0.16);
  const shotEnd = Math.round(total * 0.56);
  const starsEnd = Math.round(total * 0.72);
  const replacesEnd = Math.round(total * 0.86);
  const hasShot = Boolean(props.screenshot);
  return (
    <Background theme={theme} bgClips={props.bgClips}
      episode={props.episode} archetypeTag={props.archetypeTag} channelName={props.channelName}>
      {props.narration && <Audio src={staticFile(props.narration)} />}
      <Sequence from={0} durationInFrames={hookEnd}>
        <HookScene hook={props.hook} theme={theme} />
      </Sequence>
      <Sequence from={hookEnd} durationInFrames={shotEnd - hookEnd}>
        {hasShot ? (
          <ScreenshotScene
            repo={props.repo} file={props.screenshot as string}
            imgWidth={props.screenshotWidth || 1280}
            imgHeight={props.screenshotHeight || 5000}
            tagline={props.tagline} theme={theme}
          />
        ) : (
          <RepoCardScene repo={props.repo} tagline={props.tagline} theme={theme} />
        )}
      </Sequence>
      <Sequence from={shotEnd} durationInFrames={starsEnd - shotEnd}>
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

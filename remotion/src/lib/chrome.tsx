import React from "react";
import { AbsoluteFill, Video, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { BgClip, Theme } from "../theme";
import { familyFor } from "./fonts";

const TRANSITION_FRAMES = 15;  // ~0.5s crossfade between clips

/**
 * Page chrome shared by every template: dark ink background with an optional
 * multi-clip video montage (crossfaded), a faint grid backdrop, and the
 * cobalt "compile bar" that fills across the composition -- lifted from
 * codeaz.org.
 *
 * Multi-clip backdrop: autopilot fetches N vertical clips from Pexels using
 * the topic search terms, and we stitch them with @remotion/transitions so
 * we always cover the full narration length -- even when no single clip is
 * long enough. One clip that runs out mid-video is worse than a montage.
 */
export const Background: React.FC<React.PropsWithChildren<{
  theme: Theme;
  bgClips?: BgClip[];
  episode?: number;
  channelName?: string;
}>> = ({ theme, bgClips, episode, channelName, children }) => {
  const { durationInFrames: total } = useVideoConfig();
  const clips = (bgClips || []).filter((c) => c && c.file);
  return (
    <AbsoluteFill style={{
      backgroundColor: theme.colors.bg,
      fontFamily: familyFor(theme.fonts.body),
      color: theme.colors.fg,
    }}>
      {clips.length > 0 && (
        <AbsoluteFill>
          <ClipMontage clips={clips} total={total} />
          <AbsoluteFill style={{ backgroundColor: `${theme.colors.bg}b8` }} />
        </AbsoluteFill>
      )}
      <AbsoluteFill style={{
        backgroundImage:
          `linear-gradient(${theme.colors.bgAlt} 1px, transparent 1px), ` +
          `linear-gradient(90deg, ${theme.colors.bgAlt} 1px, transparent 1px)`,
        backgroundSize: "80px 80px",
        opacity: clips.length > 0 ? 0.18 : 0.4,
      }} />
      <CompileBar theme={theme} />
      {(channelName || episode) && (
        <ChannelBadge channel={channelName} episode={episode} theme={theme} />
      )}
      {children}
    </AbsoluteFill>
  );
};

/** Sequenced multi-clip backdrop with crossfades. Slot durations either come
 *  from the clip's own `durationInFrames` or are split evenly across `total`
 *  minus the transitions overhead. Muted -- narration owns the audio track. */
const ClipMontage: React.FC<{ clips: BgClip[]; total: number }> = ({ clips, total }) => {
  const n = clips.length;
  const transitions = Math.max(0, n - 1) * TRANSITION_FRAMES;
  // Each Sequence must be at least (adjacent transition + 1) frames, else the
  // TransitionSeries throws. Give every slot a floor of 45 frames (~1.5s).
  const defaultSlot = Math.max(45, Math.ceil((total + transitions) / n));
  return (
    <TransitionSeries>
      {clips.map((c, i) => {
        const slot = c.durationInFrames || defaultSlot;
        return (
          <React.Fragment key={i}>
            {i > 0 && (
              <TransitionSeries.Transition
                presentation={fade()}
                timing={linearTiming({ durationInFrames: TRANSITION_FRAMES })}
              />
            )}
            <TransitionSeries.Sequence durationInFrames={slot}>
              <Video
                src={staticFile(c.file)}
                muted
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            </TransitionSeries.Sequence>
          </React.Fragment>
        );
      })}
    </TransitionSeries>
  );
};

/** Thin accent-colour bar at the very top that fills left-to-right across the
 *  entire composition. Same effect as codeaz.org's scroll progress. */
export const CompileBar: React.FC<{ theme: Theme }> = ({ theme }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const w = Math.min(1, frame / durationInFrames);
  return (
    <div style={{
      position: "absolute", top: 0, left: 0, right: 0, height: 4,
      backgroundColor: `${theme.colors.accent}22`,
      zIndex: 60,
    }}>
      <div style={{
        height: "100%", backgroundColor: theme.colors.accent,
        transform: `scaleX(${w})`, transformOrigin: "left",
      }} />
    </div>
  );
};

/** Small mono uppercase section label. Used to be `tag="COST/01" label="TEARDOWN"`
 *  with a hardcoded per-scene counter that looked like a running total it wasn't.
 *  Dropped the tag/counter; the trailing rule line stays as the codeaz signature. */
export const Eyebrow: React.FC<{
  label: string;
  theme: Theme;
  accent?: string;
}> = ({ label, theme, accent }) => (
  <div style={{
    fontFamily: familyFor(theme.fonts.mono),
    fontSize: 28,
    letterSpacing: 3,
    color: accent || theme.colors.accent,
    textTransform: "uppercase",
    display: "flex",
    alignItems: "center",
    gap: 20,
    marginBottom: 40,
  }}>
    <span>{label}</span>
    <span style={{
      flex: 1, height: 1, maxWidth: 320,
      backgroundColor: `${theme.colors.fg}20`,
    }} />
  </div>
);

/** Bottom-left channel + running episode marker. Small, muted, out of the way.
 *  Numbers come from state["uploads"] length per niche, computed in autopilot. */
export const ChannelBadge: React.FC<{
  channel?: string;
  episode?: number;
  theme: Theme;
}> = ({ channel, episode, theme }) => (
  <div style={{
    position: "absolute",
    left: 60, bottom: 60,
    fontFamily: familyFor(theme.fonts.mono),
    fontSize: 24,
    letterSpacing: 2,
    textTransform: "uppercase",
    color: theme.colors.muted,
    opacity: 0.85,
    zIndex: 55,
    display: "flex", alignItems: "center", gap: 12,
  }}>
    {channel && <span>{channel}</span>}
    {channel && episode !== undefined && (
      <span style={{
        width: 4, height: 4, borderRadius: 999,
        backgroundColor: theme.colors.accent,
      }} />
    )}
    {episode !== undefined && (
      <span style={{ color: theme.colors.fg }}>#{episode}</span>
    )}
  </div>
);

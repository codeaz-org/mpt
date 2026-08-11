import React from "react";
import { AbsoluteFill, Video, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Theme } from "../theme";
import { familyFor } from "./fonts";

/**
 * Page chrome shared by every template: dark ink background with an optional
 * cover-fit muted background video, a faint grid backdrop that anchors flat
 * sections, and a thin cobalt "compile bar" at the top of the frame that
 * fills to full over the composition -- lifted from codeaz.org.
 */
export const Background: React.FC<React.PropsWithChildren<{
  theme: Theme;
  bgVideo?: string;
}>> = ({ theme, bgVideo, children }) => {
  return (
    <AbsoluteFill style={{
      backgroundColor: theme.colors.bg,
      fontFamily: familyFor(theme.fonts.body),
      color: theme.colors.fg,
    }}>
      {bgVideo && (
        <AbsoluteFill>
          <Video
            src={staticFile(bgVideo)}
            muted
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
          <AbsoluteFill style={{ backgroundColor: `${theme.colors.bg}b8` }} />
        </AbsoluteFill>
      )}
      <AbsoluteFill style={{
        backgroundImage:
          `linear-gradient(${theme.colors.bgAlt} 1px, transparent 1px), ` +
          `linear-gradient(90deg, ${theme.colors.bgAlt} 1px, transparent 1px)`,
        backgroundSize: "80px 80px",
        opacity: bgVideo ? 0.18 : 0.4,
      }} />
      <CompileBar theme={theme} />
      {children}
    </AbsoluteFill>
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

/** Small mono uppercase label above a scene. E.g. tag="COST/01" label="TEARDOWN".
 *  Trailing rule line matches codeaz.org's section headers. */
export const Eyebrow: React.FC<{
  tag: string;
  label: string;
  theme: Theme;
}> = ({ tag, label, theme }) => (
  <div style={{
    fontFamily: familyFor(theme.fonts.mono),
    fontSize: 28,
    letterSpacing: 3,
    color: theme.colors.muted,
    textTransform: "uppercase",
    display: "flex",
    alignItems: "center",
    gap: 20,
    marginBottom: 40,
  }}>
    <span style={{ color: theme.colors.accent }}>{tag}</span>
    <span>{label}</span>
    <span style={{
      flex: 1, height: 1, maxWidth: 200,
      backgroundColor: `${theme.colors.fg}20`,
    }} />
  </div>
);

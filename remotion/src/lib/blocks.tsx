import React from "react";
import { Theme } from "../theme";
import { familyFor } from "./fonts";
import { useEnter } from "./anims";

/** Big Space-Grotesk display line. The hook or a section headline. */
export const HookLine: React.FC<{
  text: string;
  theme: Theme;
  size?: number;
  fromFrame?: number;
}> = ({ text, theme, size = 92, fromFrame = 0 }) => (
  <h1 style={{
    fontFamily: familyFor(theme.fonts.display),
    fontSize: size,
    fontWeight: 700,
    lineHeight: 1.05,
    letterSpacing: -2,
    color: theme.colors.fg,
    ...useEnter(fromFrame),
  }}>{text}</h1>
);

/** Muted secondary line -- explanations, subtitles. */
export const MetaLine: React.FC<{
  text: string;
  theme: Theme;
  size?: number;
  fromFrame?: number;
}> = ({ text, theme, size = 44, fromFrame = 0 }) => (
  <div style={{
    fontSize: size,
    lineHeight: 1.35,
    color: theme.colors.muted,
    maxWidth: 900,
    ...useEnter(fromFrame),
  }}>{text}</div>
);

/** Massive JetBrains-Mono number for stat/price beats. */
export const BigNumber: React.FC<{
  value: string;
  theme: Theme;
  color?: string;
  size?: number;
  fromFrame?: number;
}> = ({ value, theme, color, size = 200, fromFrame = 0 }) => (
  <div style={{
    fontFamily: familyFor(theme.fonts.mono),
    fontSize: size,
    fontWeight: 700,
    letterSpacing: -6,
    color: color || theme.colors.accent,
    lineHeight: 1,
    ...useEnter(fromFrame),
  }}>{value}</div>
);

/** Numbered/bulleted list row that ticks on with an accent chip. */
export const ListRow: React.FC<{
  label: string;
  index?: number;
  theme: Theme;
  chipColor?: string;
  fromFrame?: number;
}> = ({ label, index, theme, chipColor, fromFrame = 0 }) => (
  <div style={{
    display: "flex",
    alignItems: "center",
    marginBottom: 24,
    ...useEnter(fromFrame),
  }}>
    {index !== undefined ? (
      <div style={{
        fontFamily: familyFor(theme.fonts.mono),
        fontSize: 40,
        color: theme.colors.muted,
        marginRight: 30,
        minWidth: 60,
      }}>{String(index).padStart(2, "0")}</div>
    ) : (
      <div style={{
        width: 20, height: 20, borderRadius: 4,
        backgroundColor: chipColor || theme.colors.good,
        marginRight: 30,
      }} />
    )}
    <div style={{
      fontFamily: familyFor(theme.fonts.display),
      fontSize: 60, fontWeight: 700, color: theme.colors.fg,
      letterSpacing: -1,
    }}>{label}</div>
  </div>
);

/** A quote-style card, used for RedFlagList entries. */
export const QuoteCard: React.FC<{
  quote: string;
  why: string;
  theme: Theme;
  accentColor?: string;
  fromFrame?: number;
}> = ({ quote, why, theme, accentColor, fromFrame = 0 }) => (
  <div style={{
    padding: "36px 44px",
    borderLeft: `6px solid ${accentColor || theme.colors.bad}`,
    backgroundColor: theme.colors.bgAlt,
    borderRadius: theme.radius,
    marginBottom: 32,
    ...useEnter(fromFrame),
  }}>
    <div style={{
      fontFamily: familyFor(theme.fonts.display),
      fontSize: 52, fontWeight: 600, color: theme.colors.fg,
      lineHeight: 1.15, marginBottom: 12,
    }}>&ldquo;{quote}&rdquo;</div>
    <div style={{
      fontSize: 32, color: theme.colors.muted, lineHeight: 1.35,
    }}>{why}</div>
  </div>
);

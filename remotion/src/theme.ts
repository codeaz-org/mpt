/**
 * A theme is passed as a prop into every template so the same JSX renders in
 * whatever brand skin the niche configures. Niches supply their theme in
 * niches.json under `theme`; remotion_render.py forwards it into every render
 * call. Templates fall back to `codeazTheme` when no theme prop arrives.
 *
 * Font families are name strings only -- the fonts themselves are loaded in
 * lib/fonts.ts using @remotion/google-fonts. To use a font not in that set,
 * add its loader there and reference it by name here.
 */
export interface Theme {
  colors: {
    bg: string;          // page background (deepest)
    bgAlt: string;       // raised cards / secondary panels
    fg: string;          // primary text
    muted: string;       // secondary text, dividers
    accent: string;      // primary brand accent (CTAs, section tags)
    good: string;        // free/positive/replaced
    bad: string;         // paid/negative/being torn down
    highlight: string;   // callouts, big-number highlights
  };
  fonts: {
    display: string;
    body: string;
    mono: string;
  };
  radius: number;        // corner radius for cards / chips
}

/** One background clip in a sequenced multi-clip backdrop. Autopilot passes
 *  an array of these -- Pexels vertical clips fetched from the topic terms --
 *  and Background stitches them with crossfades so we cover the full narration
 *  even when no single clip is long enough. */
export interface BgClip {
  file: string;              // relative filename inside public/
  durationInFrames?: number; // slot length; if missing, total is split evenly
}

/** Pulled directly from codeaz.org's :root CSS variables. */
export const codeazTheme: Theme = {
  colors: {
    bg: "#101418",
    bgAlt: "#161B21",
    fg: "#F3EFE8",
    muted: "#7A8494",
    accent: "#2E5BFF",
    good: "#3ddc84",
    bad: "#E63946",
    highlight: "#F5B700",
  },
  fonts: {
    display: "Space Grotesk",
    body: "Inter",
    mono: "JetBrains Mono",
  },
  radius: 10,
};

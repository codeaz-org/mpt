/**
 * App Rescue. The video version of rescue.codeaz.org: the founder's app as it is
 * now, set crooked on a dark ground, then one orange line sweeps up the frame and
 * leaves the fixed version on a light ground. Ends on the URL.
 *
 * It deliberately ignores the stock-footage backdrop the other formats use: the
 * split IS the visual, and it has to read as the same brand as the landing page
 * a viewer is sent to. Colours and type match the site.
 */
import React from "react";
import {
  AbsoluteFill, Audio, Easing, interpolate, spring, staticFile,
  useCurrentFrame, useVideoConfig,
} from "remotion";
import { familyFor } from "./lib/fonts";
import { Theme } from "./theme";

export interface RescueSplitProps {
  hook: string;          // statement naming what visibly breaks
  symptoms: string[];    // 2-3 short lines, what the founder sees (from the bank)
  cause: string;         // one plain sentence: why it happens
  fixes: string[];       // 2-3 short lines, the proper fix (from the bank)
  payoff?: string;       // last spoken line, shown above the URL
  url: string;           // rescue.codeaz.org
  builders?: string;     // "Lovable · Bolt · v0"
  // Which App Rescue format this is. Each draws its dark side differently:
  //   explainer  crooked "Broken" symptom lines
  //   check      the same, under "Is this your app?"; after side = numbered steps
  //   prompt_fix the prompts the founder tried, as chat bubbles
  //   checklist  a big item number and the checklist line
  //   question   the real question, quoted, with where it was asked
  format?: "explainer" | "check" | "prompt_fix" | "checklist" | "question";
  labelNow?: string;
  labelAfter?: string;
  number?: number;       // checklist item
  of?: number;
  asked?: string;        // the founder's question, verbatim
  askedOn?: string;      // "r/lovable"
  seriesTag?: string;    // "CHECK · 03"
  narration?: string;
  audioDuration?: number;
  theme?: Theme;
  episode?: number;
  archetypeTag?: string;
  channelName?: string;
}

/** The site's palette. Fixed rather than themed: this format exists to look like
 *  the page it links to. */
const C = {
  before: "#1F1B18", beforeInk: "#EFE8E1", beforeSoft: "#ABA095", beforeAccent: "#FB923C",
  after: "#FAF8F5", afterInk: "#1B1815", afterSoft: "#5B534C", accent: "#C2410C",
};
const DISPLAY = () => familyFor("Archivo");
const TEXT = () => familyFor("Geist");

// Deterministic tilts so every render of a script looks the same. Kept small: a
// wrapped two-line symptom tilted further than this runs into the line below it.
const TILT = [-0.8, 1.1, -1.3, 1.5];
const SHIFT = [0, 26, 8, 34];

const ease = Easing.bezier(0.23, 1, 0.32, 1);

// Keep text clear of the TikTok / Reels / Shorts overlays: the caption and buttons
// cover roughly the bottom 380px and the action rail the right 150px.
const SAFE = "230px 150px 380px 96px";

function useRise(from: number) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = spring({ frame: frame - from, fps, config: { damping: 200 } });
  return { opacity: t, transform: `translateY(${interpolate(t, [0, 1], [36, 0])}px)` };
}

const Tag: React.FC<{ label: string; bg: string; ink: string }> = ({ label, bg, ink }) => (
  <span style={{
    fontFamily: TEXT(), fontWeight: 600, fontSize: 32, letterSpacing: 1,
    background: bg, color: ink, padding: "6px 16px", borderRadius: 10, whiteSpace: "nowrap",
  }}>{label}</span>
);

const Label: React.FC<{ text: string; color: string }> = ({ text, color }) => (
  <div style={{ fontFamily: TEXT(), fontWeight: 500, fontSize: 38, color, marginBottom: 32,
                letterSpacing: 0.5 }}>{text}</div>
);

/** One crooked "broken" line. */
const Broken: React.FC<{ text: string; i: number; from: number }> = ({ text, i, from }) => {
  const rise = useRise(from);
  return (
    <div style={{ ...rise, marginBottom: 48 }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 22,
        transform: `translateX(${SHIFT[i % 4]}px) rotate(${TILT[i % 4]}deg)`,
        transformOrigin: "0% 60%",
      }}>
        <Tag label="Broken" bg="rgba(251,146,60,0.16)" ink={C.beforeAccent} />
        <span style={{ fontFamily: DISPLAY(), fontWeight: 600, fontSize: 64, lineHeight: 1.12,
                       color: C.beforeInk, letterSpacing: -1 }}>{text}</span>
      </div>
    </div>
  );
};

/** One straight "fixed" line. */
const Fixed: React.FC<{ text: string; from: number }> = ({ text, from }) => {
  const rise = useRise(from);
  return (
    <div style={{ ...rise, display: "flex", alignItems: "baseline", gap: 22, marginBottom: 30 }}>
      <Tag label="Fixed" bg="rgba(194,65,12,0.12)" ink={C.accent} />
      <span style={{ fontFamily: DISPLAY(), fontWeight: 600, fontSize: 60, lineHeight: 1.15,
                     color: C.afterInk, letterSpacing: -1 }}>{text}</span>
    </div>
  );
};

/** A prompt the founder sent the AI, as a slightly crooked chat bubble. */
const PromptBubble: React.FC<{ text: string; i: number; from: number }> = ({ text, i, from }) => {
  const rise = useRise(from);
  return (
    <div style={{ ...rise, marginBottom: 40 }}>
      <div style={{
        display: "inline-block", maxWidth: 760,
        transform: `translateX(${SHIFT[i % 4]}px) rotate(${TILT[i % 4] * 0.7}deg)`,
        background: "rgba(239,232,225,0.08)", border: "2px solid rgba(239,232,225,0.16)",
        borderRadius: "34px 34px 34px 8px", padding: "28px 38px",
        fontFamily: TEXT(), fontWeight: 500, fontSize: 54, lineHeight: 1.2, color: C.beforeInk,
      }}>"{text}"</div>
    </div>
  );
};

/** Numbered step for the "check it yourself" format. */
const Step: React.FC<{ text: string; n: number; from: number }> = ({ text, n, from }) => {
  const rise = useRise(from);
  return (
    <div style={{ ...rise, display: "flex", alignItems: "baseline", gap: 28, marginBottom: 34 }}>
      <span style={{ fontFamily: DISPLAY(), fontWeight: 700, fontSize: 72, color: C.accent,
                     minWidth: 60, lineHeight: 1 }}>{n}</span>
      <span style={{ fontFamily: DISPLAY(), fontWeight: 600, fontSize: 56, lineHeight: 1.15,
                     color: C.afterInk, letterSpacing: -1 }}>{text}</span>
    </div>
  );
};

export const RescueSplit: React.FC<RescueSplitProps> = (props) => {
  const frame = useCurrentFrame();
  const { durationInFrames: total, height } = useVideoConfig();

  // Timeline, as fractions of the narration so any script length fits.
  const tSymptoms = Math.round(total * 0.16);
  const tSweepStart = Math.round(total * 0.46);
  const tSweepEnd = Math.round(total * 0.58);
  const tFixes = Math.round(total * 0.6);
  const tCta = Math.round(total * 0.82);

  // The line: starts below the frame, sweeps to the top. Everything above it is the
  // "now" layer, everything below is "after".
  const sweep = interpolate(frame, [tSweepStart, tSweepEnd], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease,
  });
  const lineY = (1 - sweep) * height;

  const hookOut = interpolate(frame, [tSymptoms - 10, tSymptoms], [1, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const fixesOut = interpolate(frame, [tCta - 10, tCta], [1, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const hookRise = useRise(4);
  const causeRise = useRise(tSweepStart + 8);
  const ctaRise = useRise(tCta + 4);
  const urlRise = useRise(tCta + 16);
  const tag = props.seriesTag || (props.archetypeTag && props.episode
    ? `${props.archetypeTag} · ${String(props.episode).padStart(2, "0")}` : "APP RESCUE");
  const fmt = props.format || "explainer";
  const labelNow = props.labelNow || "Your app now";
  const labelAfter = props.labelAfter || "After a proper fix";
  const listRise = useRise(tSymptoms + 6);

  return (
    <AbsoluteFill style={{ background: C.after }}>
      {props.narration && <Audio src={staticFile(props.narration)} />}

      {/* AFTER layer: cause, fixes, then the ask */}
      <AbsoluteFill style={{ padding: SAFE, justifyContent: "center" }}>
        {frame < tCta && (
          <div style={{ opacity: fixesOut }}>
            <Label text={fmt === "prompt_fix" ? "Why prompting can't fix it"
                         : fmt === "question" ? "What's going on" : "Why it happens"}
                   color={C.afterSoft} />
            <div style={{ ...causeRise, fontFamily: DISPLAY(), fontWeight: 600, fontSize: 66,
                          lineHeight: 1.12, color: C.afterInk, letterSpacing: -1.2,
                          marginBottom: 90 }}>{props.cause}</div>
            <Label text={labelAfter} color={C.accent} />
            {props.fixes.slice(0, 3).map((f, i) => fmt === "check"
              ? <Step key={i} text={f} n={i + 1} from={tFixes + i * 14} />
              : <Fixed key={i} text={f} from={tFixes + i * 14} />)}
          </div>
        )}
        {frame >= tCta && (
          <AbsoluteFill style={{ padding: SAFE, justifyContent: "center" }}>
            <div style={{ ...ctaRise, fontFamily: DISPLAY(), fontWeight: 700, fontSize: 104,
                          lineHeight: 1.0, color: C.afterInk, letterSpacing: -3 }}>
              Get your app unstuck.
            </div>
            {props.payoff && (
              <div style={{ ...ctaRise, fontFamily: TEXT(), fontSize: 44, lineHeight: 1.4,
                            color: C.afterSoft, marginTop: 40 }}>{props.payoff}</div>
            )}
            <div style={{ ...urlRise, marginTop: 70, alignSelf: "flex-start",
                          background: C.accent, color: "#fff", fontFamily: DISPLAY(),
                          fontWeight: 700, fontSize: 64, padding: "26px 44px",
                          borderRadius: 18, letterSpacing: -1 }}>{props.url}</div>
            <div style={{ ...urlRise, fontFamily: TEXT(), fontSize: 36, color: C.afterSoft,
                          marginTop: 30 }}>Written audit in 72 hours. Fixed prices.</div>
          </AbsoluteFill>
        )}
      </AbsoluteFill>

      {/* NOW layer: hook, then crooked symptoms. Clipped to above the line. */}
      <AbsoluteFill style={{
        background: C.before, clipPath: `inset(0 0 ${height - lineY}px 0)`,
        padding: SAFE, justifyContent: "center",
      }}>
        <Label text={labelNow} color={C.beforeSoft} />
        {frame < tSymptoms + 4 ? (
          <div style={{ ...hookRise, opacity: hookRise.opacity as number * hookOut,
                        fontFamily: DISPLAY(), fontWeight: 700, fontSize: 108, lineHeight: 1.03,
                        color: C.beforeInk, letterSpacing: -2.5,
                        transform: `${hookRise.transform} rotate(-1.2deg)` }}>
            {props.hook}
          </div>
        ) : (
          <div style={{ marginTop: 40 }}>
            {fmt === "prompt_fix" ? props.symptoms.slice(0, 2).map((s, i) => (
              <PromptBubble key={i} text={s} i={i} from={tSymptoms + 6 + i * 30} />
            )) : fmt === "checklist" ? (
              <div style={listRise}>
                <div style={{ fontFamily: DISPLAY(), fontWeight: 700, fontSize: 260, lineHeight: 0.9,
                              color: C.beforeAccent, letterSpacing: -8 }}>
                  #{props.number ?? 1}
                </div>
                <div style={{ fontFamily: TEXT(), fontSize: 36, color: C.beforeSoft,
                              margin: "18px 0 40px" }}>of {props.of ?? 20}</div>
                <div style={{ fontFamily: DISPLAY(), fontWeight: 600, fontSize: 72, lineHeight: 1.08,
                              color: C.beforeInk, letterSpacing: -2,
                              transform: "rotate(-1deg)" }}>{props.symptoms[0]}</div>
              </div>
            ) : fmt === "question" && props.asked ? (
              <div style={listRise}>
                <div style={{ fontFamily: DISPLAY(), fontWeight: 600, fontSize: 70, lineHeight: 1.12,
                              color: C.beforeInk, letterSpacing: -1.5 }}>“{props.asked}”</div>
                {props.askedOn && (
                  <div style={{ fontFamily: TEXT(), fontSize: 38, color: C.beforeSoft,
                                marginTop: 36 }}>Asked on {props.askedOn}</div>
                )}
              </div>
            ) : props.symptoms.slice(0, 3).map((s, i) => (
              <Broken key={i} text={s} i={i} from={tSymptoms + 6 + i * 22} />
            ))}
          </div>
        )}
        {props.builders && (
          <div style={{ position: "absolute", left: 96, bottom: 400, fontFamily: TEXT(),
                        fontSize: 32, color: C.beforeSoft }}>{props.builders}</div>
        )}
      </AbsoluteFill>

      {/* The line */}
      {sweep > 0 && sweep < 1 && (
        <div style={{ position: "absolute", left: 0, right: 0, top: lineY - 3, height: 6,
                      background: C.accent }} />
      )}

      {/* Brand + series badge, top */}
      <div style={{ position: "absolute", top: 90, left: 96, right: 96, display: "flex",
                    justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontFamily: DISPLAY(), fontWeight: 700, fontSize: 46, letterSpacing: -1,
                       color: lineY > 140 ? C.beforeInk : C.afterInk }}>
          Code<span style={{ color: lineY > 140 ? C.beforeAccent : C.accent }}>AZ</span>
        </span>
        <span style={{ fontFamily: TEXT(), fontWeight: 600, fontSize: 28, letterSpacing: 2,
                       color: lineY > 140 ? C.beforeSoft : C.afterSoft }}>{tag}</span>
      </div>
    </AbsoluteFill>
  );
};

import { spring, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

/** Fade + rise entrance used by every scene so the whole video reads as one piece. */
export function useEnter(fromFrame = 0, _durationHint = 15) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = spring({ frame: frame - fromFrame, fps, config: { damping: 200 } });
  return {
    opacity: t,
    transform: `translateY(${interpolate(t, [0, 1], [30, 0])}px)`,
  };
}

/** 0 → 1 clamp; useful for drawing a strike-through or filling a bar over N frames. */
export function useLinearProgress(fromFrame: number, durationFrames: number) {
  const frame = useCurrentFrame();
  return interpolate(frame, [fromFrame, fromFrame + durationFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

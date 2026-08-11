/**
 * Load the codeaz font trio once, at module import, so every template gets
 * the family strings without needing to load fonts of its own. If a niche
 * later ships a different theme with different families, add its loaders
 * here and reference them by name from that niche's theme.
 */
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadSpaceGrotesk } from "@remotion/google-fonts/SpaceGrotesk";
import { loadFont as loadJetBrainsMono } from "@remotion/google-fonts/JetBrainsMono";

const inter = loadInter();
const space = loadSpaceGrotesk();
const mono = loadJetBrainsMono();

/** Match a theme's font-name string to the actually-loaded family. Falls back
 *  to system-ui if the name isn't loaded. */
export function familyFor(name: string): string {
  const map: Record<string, string> = {
    "Inter": inter.fontFamily,
    "Space Grotesk": space.fontFamily,
    "JetBrains Mono": mono.fontFamily,
  };
  return map[name] || "system-ui, sans-serif";
}

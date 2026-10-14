/**
 * Load the codeaz font trio once, at module import, so every template gets
 * the family strings without needing to load fonts of its own. If a niche
 * later ships a different theme with different families, add its loaders
 * here and reference them by name from that niche's theme.
 */
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadSpaceGrotesk } from "@remotion/google-fonts/SpaceGrotesk";
import { loadFont as loadJetBrainsMono } from "@remotion/google-fonts/JetBrainsMono";
// App Rescue matches rescue.codeaz.org, which is set in Archivo and Geist.
import { loadFont as loadArchivo } from "@remotion/google-fonts/Archivo";
import { loadFont as loadGeist } from "@remotion/google-fonts/Geist";

const inter = loadInter();
const space = loadSpaceGrotesk();
const mono = loadJetBrainsMono();
const archivo = loadArchivo("normal", { weights: ["500", "600", "700"], subsets: ["latin"] });
const geist = loadGeist("normal", { weights: ["400", "500", "600"], subsets: ["latin"] });

/** Match a theme's font-name string to the actually-loaded family. Falls back
 *  to system-ui if the name isn't loaded. */
export function familyFor(name: string): string {
  const map: Record<string, string> = {
    "Inter": inter.fontFamily,
    "Space Grotesk": space.fontFamily,
    "JetBrains Mono": mono.fontFamily,
    "Archivo": archivo.fontFamily,
    "Geist": geist.fontFamily,
  };
  return map[name] || "system-ui, sans-serif";
}

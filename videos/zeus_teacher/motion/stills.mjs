// Renders sample stills at the given times (seconds) in one bundle: node stills.mjs 3 7 12 ...
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import path from "node:path";

const times = process.argv.slice(2).map(Number);
const scale = Number(process.env.SCALE ?? 0.5);
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts") });
const composition = await selectComposition({ serveUrl, id: process.env.COMP ?? "Zeus" });
for (const t of times) {
  const frame = Math.min(composition.durationInFrames - 1, Math.round(t * 30));
  const output = `out/stills/${process.env.COMP ?? "main"}-t${String(t).replace(".", "_")}.png`;
  await renderStill({ serveUrl, composition, frame, output, scale });
  console.log(output);
}

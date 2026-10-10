import React from "react";
import { Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

// Colour = meaning, every scene: cyan = the bot (game colour), amber = you, red = the mistake,
// green = the smooth version / the fix, ink = the teacher's notes.
export const C = {
  ink: "#F4EFE6",
  dim: "#A9A49A",
  amber: "#F0A53A",
  red: "#E5483D",
  green: "#6FD08C",
  bot: "#5AE1D7",
  dark: "#14110E",
  sky: "#2C2E30",
  floor: "#1E1F20",
  grid: "#4E5052",
};
export const HAND = "'Segoe Print', 'Ink Free', cursive";
export const SANS = "'Segoe UI', Arial, sans-serif";

export const OUT = Easing.bezier(0.16, 1, 0.3, 1);
export const IN_OUT = Easing.bezier(0.65, 0, 0.35, 1);
export const cl = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const useNow = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return frame / fps;
};
export const ramp = (now: number, t: number, dur = 0.4, ease = OUT) => interpolate(now, [t, t + dur], [0, 1], { ...cl, easing: ease });
export const springAt = (now: number, t: number, fps = 30) =>
  now < t ? 0 : spring({ frame: (now - t) * fps, fps, config: { damping: 13, stiffness: 180, mass: 0.7 } });
export const life = (now: number, t: number, out?: number, inDur = 0.25, outDur = 0.3) =>
  Math.min(ramp(now, t, inDur), out === undefined ? 1 : 1 - ramp(now, out, outDur, IN_OUT));

const rnd = (n: number) => {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};

// ---------------------------------------------------------------- marker strokes (from the Positioning Rebuild kit)
const BOIL = 3; // frames per boil step (drawn "on 3s")
export const smooth = (pts: [number, number][]) => {
  if (pts.length < 3) return `M${pts.map((p) => p.join(" ")).join(" L")}`;
  let d = `M${pts[0][0]} ${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0]} ${c1[1]} ${c2[0]} ${c2[1]} ${p2[0]} ${p2[1]}`;
  }
  return d;
};
const densify = (pts: [number, number][], step = 36) => {
  const out: [number, number][] = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
    const n = Math.max(1, Math.round(Math.hypot(bx - ax, by - ay) / step));
    for (let k = 0; k < n; k++) out.push([ax + ((bx - ax) * k) / n, ay + ((by - ay) * k) / n]);
  }
  out.push(pts[pts.length - 1]);
  return out;
};
export const useBoil = (seed: number, amp: number, pts: [number, number][]) => {
  const frame = useCurrentFrame();
  const step = Math.floor(frame / BOIL);
  return pts.map(([x, y], i) => [x + (rnd(seed + i * 7.3 + step * 19.1) - 0.5) * amp, y + (rnd(seed + i * 3.1 + step * 11.7 + 50) - 0.5) * amp] as [number, number]);
};

export const Marker: React.FC<{
  pts: [number, number][];
  t: number;
  dur?: number;
  color: string;
  w?: number;
  head?: boolean;
  dash?: boolean;
  out?: number;
  seed?: number;
  curve?: number;
}> = ({ pts, t, dur = 0.5, color, w = 8, head = false, dash = false, out, seed = 1, curve = 0 }) => {
  const now = useNow();
  let base = pts;
  if (curve && pts.length === 2) {
    const [[ax, ay], [bx, by]] = pts;
    const len = Math.hypot(bx - ax, by - ay) || 1;
    const nx = -(by - ay) / len, ny = (bx - ax) / len;
    base = [pts[0], [(ax + bx) / 2 + nx * curve, (ay + by) / 2 + ny * curve], pts[1]];
  }
  const dense = densify(base, 30);
  const b = useBoil(seed * 13 + t * 7, 2.2, dense);
  if (now < t) return null;
  const op = life(now, t, out, 0.05);
  if (op <= 0) return null;
  const p = ramp(now, t, dur, IN_OUT);
  const d = smooth(b);
  const n = b.length;
  const [ex, ey] = b[n - 1];
  const [px, py] = b[Math.max(0, n - 3)];
  const ang = Math.atan2(ey - py, ex - px);
  const hl = 8 + w * 2.4;
  const hp = ramp(now, t + dur * 0.85, 0.15);
  const hd = `M${ex - hl * Math.cos(ang - 0.5)} ${ey - hl * Math.sin(ang - 0.5)} L${ex} ${ey} L${ex - hl * Math.cos(ang + 0.5)} ${ey - hl * Math.sin(ang + 0.5)}`;
  return (
    <g opacity={op * 0.95}>
      {dash ? (
        <path d={d} fill="none" stroke={color} strokeWidth={w} strokeLinecap="round" strokeDasharray={`${w * 2.2} ${w * 2}`} opacity={p} />
      ) : (
        <path d={d} fill="none" stroke={color} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - p} />
      )}
      {head && hp > 0 && <path d={hd} fill="none" stroke={color} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - hp} />}
    </g>
  );
};

export const Loop: React.FC<{ cx: number; cy: number; rx: number; ry?: number; t: number; dur?: number; color: string; w?: number; out?: number; seed?: number }> = ({
  cx, cy, rx, ry, t, dur = 0.5, color, w = 6, out, seed = 3,
}) => {
  const r2 = ry ?? rx;
  const pts: [number, number][] = [];
  const N = 22;
  for (let i = 0; i <= N; i++) {
    const a = -2.2 + (i / N) * Math.PI * 2.18;
    const wob = 1 + (rnd(seed * 31 + i) - 0.5) * 0.07 + (i / N) * 0.06;
    pts.push([cx + rx * wob * Math.cos(a), cy + r2 * wob * Math.sin(a)]);
  }
  return <Marker pts={pts} t={t} dur={dur} color={color} w={w} out={out} seed={seed} />;
};

export const Tick: React.FC<{ x: number; y: number; s?: number; t: number; color?: string; w?: number }> = ({ x, y, s = 22, t, color = C.green, w = 7 }) => (
  <Marker pts={[[x - s, y], [x - s * 0.3, y + s * 0.7], [x + s, y - s * 0.9]]} t={t} dur={0.25} color={color} w={w} seed={5} />
);

/** A bracket between two points: the distance being pointed at, with end ticks. */
export const Bracket: React.FC<{ a: [number, number]; b: [number, number]; t: number; color: string; out?: number; w?: number }> = ({ a, b, t, color, out, w = 6 }) => {
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
  const nx = (-(b[1] - a[1]) / len) * 16, ny = ((b[0] - a[0]) / len) * 16;
  return (
    <g>
      <Marker pts={[[a[0] - nx, a[1] - ny], [a[0] + nx, a[1] + ny]]} t={t} dur={0.12} color={color} w={w} out={out} seed={11} />
      <Marker pts={[a, b]} t={t + 0.1} dur={0.3} color={color} w={w} out={out} seed={12} />
      <Marker pts={[[b[0] - nx, b[1] - ny], [b[0] + nx, b[1] + ny]]} t={t + 0.38} dur={0.12} color={color} w={w} out={out} seed={13} />
    </g>
  );
};

/** The teacher's handwritten note: writes on left to right like a pen, dark halo so it reads over the game. */
export const Note: React.FC<{ x: number; y: number; t: number; size?: number; color?: string; anchor?: "start" | "middle" | "end"; out?: number; lines: string[]; dur?: number }> = ({
  x, y, t, size = 46, color = C.ink, anchor = "start", out, lines, dur,
}) => {
  const now = useNow();
  if (now < t) return null;
  const op = life(now, t, out, 0.1);
  if (op <= 0) return null;
  const chars = lines.join("").length;
  const p = ramp(now, t, dur ?? Math.min(1.2, 0.25 + chars * 0.025), (k) => k);
  const wMax = Math.max(...lines.map((l) => l.length)) * size * 0.62 + 40;
  const x0 = anchor === "start" ? x - 20 : anchor === "middle" ? x - wMax / 2 : x - wMax;
  const id = `note${Math.round(t * 100)}_${Math.round(x)}_${Math.round(y)}`;
  return (
    <g opacity={op}>
      <clipPath id={id}>
        <rect x={x0} y={y - size * 1.4} width={wMax * p} height={size * 1.25 * lines.length + size * 0.8} />
      </clipPath>
      <g clipPath={`url(#${id})`}>
        {lines.map((l, i) => (
          <text key={i} x={x} y={y + i * size * 1.25} fill={color} fontFamily={HAND} fontWeight={700} fontSize={size} textAnchor={anchor}
            stroke={C.dark} strokeWidth={size * 0.16} strokeLinejoin="round" style={{ paintOrder: "stroke" }}>
            {l}
          </text>
        ))}
      </g>
    </g>
  );
};

/** Small label (not handwriting): speed, zoom, run source. */
export const Label: React.FC<{ x: number; y: number; t?: number; text: string; color?: string; size?: number; anchor?: "start" | "middle" | "end"; out?: number }> = ({
  x, y, t = 0, text, color = C.dim, size = 24, anchor = "start", out,
}) => {
  const now = useNow();
  if (now < t) return null;
  const op = life(now, t, out, 0.25);
  return (
    <text x={x} y={y} fill={color} opacity={op} fontFamily={SANS} fontWeight={600} fontSize={size} letterSpacing="0.06em" textAnchor={anchor}
      stroke={C.dark} strokeWidth={4} style={{ paintOrder: "stroke" }}>
      {text}
    </text>
  );
};

/** Lesson number in the corner, hand-circled, so a lesson is easy to find when scrubbing. */
export const Chapter: React.FC<{ n: number; title: string }> = ({ n, title }) => (
  <g>
    <Loop cx={70} cy={66} rx={34} ry={32} t={0.1} color={C.ink} w={5} seed={n * 7} />
    <text x={70} y={82} textAnchor="middle" fill={C.ink} fontFamily={HAND} fontWeight={700} fontSize={44}>{n}</text>
    <Note x={122} y={84} t={0.35} size={40} lines={[title]} />
  </g>
);

/** Light grain and a vignette over everything. */
export const Finish: React.FC = () => {
  const frame = useCurrentFrame();
  const seed = Math.floor(frame / 2) % 97;
  return (
    <g pointerEvents="none">
      <defs>
        <radialGradient id="vig" cx="50%" cy="50%" r="75%">
          <stop offset="55%" stopColor="#000" stopOpacity={0} />
          <stop offset="100%" stopColor="#000" stopOpacity={0.5} />
        </radialGradient>
        <filter id={`grain${seed}`} x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={seed} />
          <feColorMatrix type="saturate" values="0" />
        </filter>
      </defs>
      <rect width={1920} height={1080} fill="url(#vig)" />
      <rect width={1920} height={1080} filter={`url(#grain${seed})`} opacity={0.07} style={{ mixBlendMode: "overlay" }} />
    </g>
  );
};

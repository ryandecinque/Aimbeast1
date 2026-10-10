import React from "react";
import { C, SANS, useBoil, smooth } from "./kit";
import data from "./data.json";

// One recorded moment (60 samples a second): Ryan's aim, the bot's visible centre, and the smooth version's aim
// (same 133 ms reaction). Written by moments.py from the AimRecorder files.
export type Clip = {
  run: string; score: number; t0: number; hw: number; hh: number; cam: number[];
  yaw: number[]; pitch: number[]; bot: number[][]; botyaw: number[]; botpitch: number[]; hits: number[];
  aimspd: number[]; botspd: number[]; smooth: (number[] | null)[]; smoothspd?: (number | null)[];
  timeleft: number[]; mark: Record<string, number>;
};
export const D = data as unknown as { turn: Clip; brake: Clip; far: Clip; open: Clip; topdown: { cam: number[]; path: number[][] }; chart: { s: number; pps: number; dist: number }[] };

const HFOV = 103;
const rad = (d: number) => (d * Math.PI) / 180;
const lerp = (a: number, b: number, u: number) => a + (b - a) * u;
const at = (arr: number[], s: number) => {
  const i = Math.max(0, Math.min(arr.length - 1.001, s));
  const k = Math.floor(i);
  return lerp(arr[k], arr[Math.min(k + 1, arr.length - 1)], i - k);
};
const atSmooth = (c: Clip, s: number): [number, number] | null => {
  const k = Math.max(0, Math.min(c.smooth.length - 1, Math.floor(s)));
  const a = c.smooth[k], b = c.smooth[Math.min(k + 1, c.smooth.length - 1)];
  if (!a) return null;
  if (!b) return [a[0], a[1]];
  return [lerp(a[0], b[0], s - k), lerp(a[1], b[1], s - k)];
};
/** Aim (yaw, pitch) at sample s, for Ryan or the smooth version (falls back to Ryan before the smooth one starts). */
export const aimAt = (c: Clip, s: number, who: "you" | "smooth" = "you"): [number, number] => {
  if (who === "smooth") {
    const v = atSmooth(c, s);
    if (v) return v;
  }
  return [at(c.yaw, s), at(c.pitch, s)];
};
/** Visible bot centre in world space at sample s (bot height from where the hits landed). */
export const botAt = (c: Clip, s: number): [number, number, number] => {
  const k = Math.max(0, Math.min(c.bot.length - 1.001, s));
  const i = Math.floor(k), u = k - i, j = Math.min(i + 1, c.bot.length - 1);
  const x = lerp(c.bot[i][0], c.bot[j][0], u), y = lerp(c.bot[i][1], c.bot[j][1], u);
  const hd = Math.hypot(x - c.cam[0], y - c.cam[1]);
  return [x, y, c.cam[2] + Math.tan(rad(at(c.botpitch, s))) * hd];
};
export const distAt = (c: Clip, s: number) => {
  const b = botAt(c, s);
  return Math.hypot(b[0] - c.cam[0], b[1] - c.cam[1]);
};

export type Panel = { x: number; y: number; w: number; h: number; zoom: number };
export type View = { cam: number[]; yaw: number; pitch: number; f: number; ox: number; oy: number };
export const view = (c: Clip, s: number, p: Panel, who: "you" | "smooth" = "you"): View => {
  const [yaw, pitch] = aimAt(c, s, who);
  // zoom 1 = Ryan's own 103° view across the panel's width
  return { cam: c.cam, yaw, pitch, f: (p.w / 2 / Math.tan(rad(HFOV / 2))) * p.zoom, ox: p.x + p.w / 2, oy: p.y + p.h / 2 };
};
/** pb_video.py's projection: world point -> screen, or null if behind the camera. */
export const proj = (v: View, x: number, y: number, z: number): [number, number] | null => {
  const cy = Math.cos(rad(v.yaw)), sy = Math.sin(rad(v.yaw)), cp = Math.cos(rad(v.pitch)), sp = Math.sin(rad(v.pitch));
  const dx = x - v.cam[0], dy = y - v.cam[1], dz = z - v.cam[2];
  const fwd = dx * cy + dy * sy, right = -dx * sy + dy * cy;
  const fz = fwd * cp + dz * sp, up = -fwd * sp + dz * cp;
  if (fz < 5) return null;
  return [v.ox + (right / fz) * v.f, v.oy - (up / fz) * v.f];
};
/** Where an aim direction (yaw, pitch) at distance d lands on screen in view v. */
export const projAim = (v: View, yaw: number, pitch: number, d: number) =>
  proj(v, v.cam[0] + d * Math.cos(rad(pitch)) * Math.cos(rad(yaw)), v.cam[1] + d * Math.cos(rad(pitch)) * Math.sin(rad(yaw)), v.cam[2] + d * Math.sin(rad(pitch)));
/** Bot on screen: centre and half-sizes in px. */
export const botScreen = (c: Clip, s: number, v: View) => {
  const b = botAt(c, s);
  const p = proj(v, ...b);
  const fz = Math.hypot(b[0] - v.cam[0], b[1] - v.cam[1]);
  return p ? { x: p[0], y: p[1], rx: Math.max(2.5, (c.hw / fz) * v.f), ry: Math.max(2.5, (c.hh / fz) * v.f) } : null;
};

let uid = 0;
/** The in-game view, rebuilt from the recording, inside a panel. Optional trails of the last `trail` samples. */
export const Game: React.FC<{
  c: Clip; s: number; p: Panel; who?: "you" | "smooth"; trail?: number; trailFrom?: number; botTrail?: boolean; hud?: boolean; frame?: boolean; dimmed?: number;
}> = ({ c, s, p, who = "you", trail = 0, trailFrom, botTrail = false, hud = false, frame = true, dimmed = 0 }) => {
  const v = view(c, s, p, who);
  const id = React.useMemo(() => `gp${uid++}`, []);
  // floor grid (pb_video.py): 250-unit squares, 350 below the camera
  const FLOOR = c.cam[2] - 350, step = 250, span = 2750;
  const gx0 = Math.round(c.cam[0] / step) * step, gy0 = Math.round(c.cam[1] / step) * step + 1500;
  const lines: string[] = [];
  for (let k = -span; k <= span; k += step) {
    for (const [a, b] of [[[gx0 + k, gy0 - span], [gx0 + k, gy0 + span]], [[gx0 - span, gy0 + k], [gx0 + span, gy0 + k]]] as number[][][]) {
      let d = "";
      let pen = false;
      for (let q = 0; q <= 24; q++) {
        const u = q / 24;
        const pt = proj(v, a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, FLOOR);
        if (pt && Math.abs(pt[0] - v.ox) < 6000 && Math.abs(pt[1] - v.oy) < 6000) { d += `${pen ? "L" : "M"}${pt[0].toFixed(1)} ${pt[1].toFixed(1)}`; pen = true; } else pen = false;
      }
      if (d) lines.push(d);
    }
  }
  const [ay, ap] = aimAt(c, s, who);
  const hz = proj(v, v.cam[0] + 1e6 * Math.cos(rad(ay)), v.cam[1] + 1e6 * Math.sin(rad(ay)), v.cam[2]);
  const hy = hz ? hz[1] : ap < 0 ? p.y : p.y + p.h;
  const b = botScreen(c, s, v);
  // trails: past aim directions and past bot positions, drawn into the current (frozen) view
  const tr: [number, number][] = [], bt: [number, number][] = [];
  if (trail > 0) {
    const s0 = Math.max(trailFrom ?? 0, s - trail);
    for (let k = s0; k <= s + 1e-6; k += 1) {
      const [yy, pp] = aimAt(c, k, who);
      const q = projAim(v, yy, pp, distAt(c, k));
      if (q) tr.push(q);
      if (botTrail) { const bb = proj(v, ...botAt(c, k)); if (bb) bt.push(bb); }
    }
  }
  const col = who === "you" ? C.amber : C.green;
  const tl = Math.max(0, Math.ceil(at(c.timeleft, s) - 1e-6));
  return (
    <g>
      <clipPath id={id}><rect x={p.x} y={p.y} width={p.w} height={p.h} rx={frame ? 6 : 0} /></clipPath>
      <g clipPath={`url(#${id})`}>
        <rect x={p.x} y={p.y} width={p.w} height={p.h} fill={C.floor} />
        <rect x={p.x} y={p.y} width={p.w} height={Math.max(0, Math.min(p.h, hy - p.y))} fill={C.sky} />
        {lines.map((d, i) => <path key={i} d={d} stroke={C.grid} strokeWidth={1.2} fill="none" />)}
        {bt.length > 1 && <path d={`M${bt.map((q) => q.map((n) => n.toFixed(1)).join(" ")).join(" L")}`} stroke={C.bot} strokeWidth={4} strokeDasharray="10 9" fill="none" opacity={0.85} />}
        {b && <rect x={b.x - b.rx} y={b.y - b.ry} width={2 * b.rx} height={2 * b.ry} rx={b.rx} fill={C.bot} />}
        {tr.length > 1 && tr.slice(1).map((q, i) => (
          <line key={i} x1={tr[i][0]} y1={tr[i][1]} x2={q[0]} y2={q[1]} stroke={col} strokeWidth={5} strokeLinecap="round" opacity={0.2 + 0.8 * (i / tr.length)} />
        ))}
        <circle cx={v.ox} cy={v.oy} r={p.zoom > 1 ? 7 : 4} fill={who === "you" ? "#FF4A3C" : C.green} stroke={C.dark} strokeWidth={1.5} />
        {hud && (
          <g fontFamily={SANS} fontWeight={700} textAnchor="middle" fill={C.ink}>
            <text x={p.x + p.w / 2} y={p.y + 62} fontSize={50}>{`${Math.floor(tl / 60)}:${String(tl % 60).padStart(2, "0")}`}</text>
            <text x={p.x + p.w / 2} y={p.y + 106} fontSize={34}>{Math.max(0, Math.round(at(c.hits, s)))}</text>
            <text x={p.x + p.w / 2} y={p.y + p.h - 40} fontSize={24} fontWeight={400}>ZEUS TRACK EVO - NOBLINK</text>
          </g>
        )}
        {dimmed > 0 && <rect x={p.x} y={p.y} width={p.w} height={p.h} fill="#0C0A10" opacity={dimmed} />}
      </g>
      {frame && p.w < 1900 && <rect x={p.x} y={p.y} width={p.w} height={p.h} rx={6} fill="none" stroke={col} strokeWidth={3} opacity={0.8} />}
    </g>
  );
};

/** Hand-drawn speed graph: the bot's speed (cyan) and an aim speed (amber = Ryan, green = smooth), drawn up to sample s. */
export const SpeedGraph: React.FC<{ c: Clip; s: number; a: number; b: number; x: number; y: number; w: number; h: number; who?: "you" | "smooth"; top?: number }> = ({
  c, s, a, b, x, y, w, h, who = "you", top,
}) => {
  const ys = (who === "you" ? c.aimspd : (c.smoothspd ?? []).map((v) => v ?? 0)).slice(a, b);
  const mx = top ?? Math.max(...c.aimspd.slice(a, b), ...c.botspd.slice(a, b)) * 1.08;
  const X = (k: number) => x + ((k - a) / (b - a)) * w;
  const Y = (v: number) => y + h - (Math.min(v, mx) / mx) * h;
  const end = Math.min(b - 1, Math.floor(s));
  const pts = (arr: number[]) => {
    const o: [number, number][] = [];
    for (let k = a; k <= end; k += 2) o.push([X(k), Y(arr[k - a] ?? 0)]);
    return o;
  };
  const botP = useBoil(41, 1.6, pts(c.botspd.slice(a, b)));
  const aimP = useBoil(43, 1.6, pts(ys));
  const axis = useBoil(47, 1.4, [[x, y - 8], [x, y + h], [x + w, y + h]]);
  return (
    <g>
      <path d={smooth(axis)} stroke={C.dim} strokeWidth={3} fill="none" strokeLinecap="round" />
      <text x={x + 12} y={y + 4} fill={C.dim} fontFamily={SANS} fontWeight={600} fontSize={22}>speed</text>
      {botP.length > 1 && <path d={smooth(botP)} stroke={C.bot} strokeWidth={5} fill="none" strokeLinecap="round" />}
      {aimP.length > 1 && <path d={smooth(aimP)} stroke={who === "you" ? C.amber : C.green} strokeWidth={5} fill="none" strokeLinecap="round" />}
      <text x={x + w} y={y + h + 34} textAnchor="end" fill={C.dim} fontFamily={SANS} fontWeight={600} fontSize={22}>
        <tspan fill={C.bot}>bot</tspan>  ·  <tspan fill={who === "you" ? C.amber : C.green}>{who === "you" ? "your aim" : "smooth aim"}</tspan>
      </text>
    </g>
  );
};
export const graphPoint = (c: Clip, k: number, a: number, b: number, x: number, y: number, w: number, h: number, top?: number): [number, number] => {
  const mx = top ?? Math.max(...c.aimspd.slice(a, b), ...c.botspd.slice(a, b)) * 1.08;
  return [x + ((k - a) / (b - a)) * w, y + h - (Math.min(c.aimspd[k], mx) / mx) * h];
};

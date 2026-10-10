import React from "react";
import { Bracket, C, Chapter, Label, Loop, Marker, Note, SANS, Tick, life, ramp, useBoil, smooth, useNow } from "./kit";
import { botScreen, Clip, D, distAt, Game, graphPoint, graphTop, Panel, projAim, SpeedGraph, view, aimAt } from "./game";

// Piecewise playback: [scene time, sample] knots; holds before the first and after the last (a freeze).
const play = (t: number, knots: [number, number][]) => {
  if (t <= knots[0][0]) return knots[0][1];
  for (let i = 1; i < knots.length; i++) {
    const [t0, s0] = knots[i - 1], [t1, s1] = knots[i];
    if (t <= t1) return s0 + ((s1 - s0) * (t - t0)) / (t1 - t0);
  }
  return knots[knots.length - 1][1];
};
const FULL: Panel = { x: 0, y: 0, w: 1920, h: 1080, zoom: 1 };
const fade = (t: number, a: number, b: number) => Math.min(ramp(t, a, 0.3), 1 - ramp(t, b - 0.3, 0.3));
const Fade: React.FC<{ t: number; a: number; b: number; children: React.ReactNode }> = ({ t, a, b, children }) =>
  t < a || t > b ? null : <g opacity={fade(t, a, b)}>{children}</g>;
const secs = (c: Clip, s: number) => `${c.run.slice(0, 10)} ${c.run.slice(11, 13)}:${c.run.slice(13, 15)} run (${c.score}) · ${(c.t0 + s / 60).toFixed(1)} s in`;

/** Where the aim is relative to the bot, on screen, in a view. */
const aimVsBot = (c: Clip, s: number, p: Panel, who: "you" | "smooth" = "you") => {
  const v = view(c, s, p, who);
  const b = botScreen(c, s, v)!;
  return { v, b, aim: [v.ox, v.oy] as [number, number] };
};
/** Bot's direction of travel on screen at sample s (unit vector), in view v. */
const botDir = (c: Clip, s: number, p: Panel) => {
  const v = view(c, s, p);
  const b0 = botScreen(c, s - 4, v)!, b1 = botScreen(c, s + 4, v)!;
  const l = Math.hypot(b1.x - b0.x, b1.y - b0.y) || 1;
  return [(b1.x - b0.x) / l, (b1.y - b0.y) / l] as [number, number];
};

// ================================================================ 0. cold open: his real run tonight
export const Open: React.FC = () => {
  const t = useNow();
  const c = D.open;
  const s = play(t, [[0, 0], [5.4, 324]]);
  const dim = 0.3 * ramp(t, 5.4, 0.5);
  return (
    <g>
      <Game c={c} s={s} p={FULL} hud dimmed={dim} />
      <Label x={1890} y={1050} anchor="end" text="Rebuilt from your aim data · Oct 10, 21:49" />
      <Loop cx={960} cy={92} rx={110} ry={62} t={5.7} color={C.amber} />
      <Note x={1090} y={110} t={6.1} lines={["Tonight's best run: 523."]} />
      <Note x={960} y={820} t={7.6} anchor="middle" size={58} lines={["Let's find where the points go."]} />
    </g>
  );
};

// ================================================================ 1. how the bot moves (top-down, his real round)
export const HowItMoves: React.FC = () => {
  const t = useNow();
  const td = D.topdown;
  const S = 0.32, cx = td.cam[0], cy = td.cam[1];
  // looking along +y: the player's right is -x, so flip x to match what he sees
  const P = (x: number, y: number): [number, number] => [960 - (x - cx) * S, 1000 - (y - cy) * S];
  const tPlay = play(t, [[0.6, 0], [5.6, 20]]);
  const pts = td.path.filter((q) => q[2] <= tPlay).map((q) => P(q[0], q[1]));
  const now = pts[pts.length - 1];
  const grid = [] as React.ReactNode[];
  for (let gx = -1500; gx <= 1500; gx += 250) grid.push(<line key={`x${gx}`} x1={P(cx + gx, cy)[0]} y1={70} x2={P(cx + gx, cy)[0]} y2={1060} stroke={C.grid} strokeWidth={1} opacity={0.5} />);
  for (let gy = 0; gy <= 2900; gy += 250) grid.push(<line key={`y${gy}`} x1={300} y1={P(cx, cy + gy)[1]} x2={1620} y2={P(cx, cy + gy)[1]} stroke={C.grid} strokeWidth={1} opacity={0.5} />);
  const you = P(cx, cy);
  const boiled = useBoil(9, 1.2, pts.length > 1 ? pts : [you, you]);
  // the zig-zag close-up: the stretch around 11-13 s into the round
  const zz = td.path.filter((q) => q[2] > 10.5 && q[2] < 13).map((q) => P(q[0], q[1]));
  const zx = zz.reduce((a, q) => a + q[0], 0) / Math.max(1, zz.length), zy = zz.reduce((a, q) => a + q[1], 0) / Math.max(1, zz.length);
  return (
    <g>
      <rect width={1920} height={1080} fill={C.floor} />
      {grid}
      <Label x={1600} y={1050} anchor="end" text="Seen from above · one real round, Oct 10, 21:49" />
      <circle cx={you[0]} cy={you[1]} r={16} fill={C.amber} stroke={C.dark} strokeWidth={3} />
      <Note x={you[0] + 34} y={you[1] + 14} t={0.2} size={40} lines={["you"]} />
      {pts.length > 1 && <path d={smooth(boiled)} stroke={C.bot} strokeWidth={4} fill="none" strokeLinecap="round" strokeLinejoin="round" />}
      {now && <circle cx={now[0]} cy={now[1]} r={14} fill={C.bot} stroke={C.dark} strokeWidth={3} />}
      <Note x={1180} y={180} t={0.8} lines={["Every round it starts far…"]} />
      <Note x={1180} y={560} t={3.6} lines={["…and walks in.", "20 seconds a round."]} />
      <Loop cx={zx} cy={zy} rx={170} ry={95} t={6.6} color={C.ink} w={5} />
      <Note x={120} y={zy - 150} t={7.0} anchor="start" lines={["Left, right, left…"]} out={13.6} />
      <Note x={120} y={zy - 90} t={8.2} anchor="start" size={38} lines={["it turns every 0.2–0.4 s"]} out={13.6} />
      <Note x={250} y={250} t={10.4} size={44} lines={["3 rounds a run.", "Each one starts far."]} />
    </g>
  );
};

// ================================================================ lesson 1: when it turns, you keep going
export const Lesson1: React.FC = () => {
  const t = useNow();
  const c = D.turn;
  const { i, peak } = c.mark;
  const Z: Panel = { x: 0, y: 0, w: 1920, h: 1080, zoom: 2.5 };
  // A: real speed, full view
  const sA = play(t, [[0.3, 20], [2.9, 136]]);
  // B: quarter speed, zoomed, freeze on the run-through
  const sB = play(t, [[3.2, i - 30], [3.2 + (peak - (i - 30)) / 15, peak]]);
  const tFreeze = 3.2 + (peak - (i - 30)) / 15;
  // C: side by side, the same moment
  const L: Panel = { x: 40, y: 170, w: 900, h: 660, zoom: 3.5 }, R: Panel = { x: 980, y: 170, w: 900, h: 660, zoom: 3.5 };
  const tC = 16.6;
  const tC2 = tC + (peak - (i - 30)) / 21;
  const sC = play(t, [[tC, i - 30], [tC2, peak], [tC2 + 4.2, peak], [tC2 + 4.2 + 45 / 21, peak + 45]]);
  // geometry for the drawings
  const fB = aimVsBot(c, peak, Z);
  const dir = botDir(c, peak, Z);
  const edge = (b: { x: number; rx: number }, ax: number): [number, number] => [b.x + Math.sign(ax - b.x) * b.rx, 0];
  const fL = aimVsBot(c, peak, L), fR = aimVsBot(c, peak, R, "smooth");
  const eL = edge(fL.b, fL.aim[0]), eR = edge(fR.b, fR.aim[0]);
  const prev = projAim(fB.v, ...aimAt(c, peak - 6), distAt(c, peak - 6))!;
  const ad = [fB.aim[0] - prev[0], fB.aim[1] - prev[1]]; const al = Math.hypot(ad[0], ad[1]) || 1;
  return (
    <g>
      <Fade t={t} a={0} b={3.25}>
        <Game c={c} s={sA} p={FULL} />
        <Label x={1890} y={1040} anchor="end" text={`Real speed · ${secs(c, 20)}`} />
      </Fade>
      <Fade t={t} a={2.95} b={16.7}>
        <Game c={c} s={sB} p={Z} trail={36} botTrail />
        <Label x={1890} y={1040} anchor="end" t={3.0} text={t < tFreeze ? "¼ speed · zoomed 2.5×" : "paused · zoomed 2.5×"} />
        <Marker pts={[[fB.b.x - dir[0] * 20, fB.b.y + fB.b.ry + 60], [fB.b.x + dir[0] * 180, fB.b.y + fB.b.ry + 60]]} t={tFreeze + 0.3} dur={0.4} head color={C.bot} w={8} />
        <Note x={fB.b.x + dir[0] * 40} y={fB.b.y + fB.b.ry + 140} t={tFreeze + 0.6} anchor="middle" lines={["It turned."]} />
        <Marker pts={[[fB.aim[0] - (ad[0] / al) * 160, fB.aim[1] - 120], [fB.aim[0] + (ad[0] / al) * 40, fB.aim[1] - 120]]} t={tFreeze + 1.9} dur={0.4} head color={C.amber} w={8} />
        <Note x={fB.aim[0]} y={fB.aim[1] - 170} t={tFreeze + 2.1} anchor="middle" lines={["You kept going."]} />
        <Loop cx={fB.aim[0]} cy={fB.aim[1]} rx={42} t={tFreeze + 3.4} color={C.red} />
        <Bracket a={[edge(fB.b, fB.aim[0])[0], fB.aim[1] + 70]} b={[fB.aim[0], fB.aim[1] + 70]} t={tFreeze + 3.9} color={C.red} />
        <Note x={960} y={230} t={tFreeze + 4.4} anchor="middle" lines={["Through it, and out the other side."]} />
        <Note x={960} y={940} t={tFreeze + 6.6} anchor="middle" size={40} color={C.ink} lines={["This happens on about 4 in 10 turns, in all 21 of your runs."]} />
      </Fade>
      <Fade t={t} a={16.5} b={99}>
        <rect width={1920} height={1080} fill={C.dark} />
        <Game c={c} s={sC} p={L} trail={36} botTrail />
        <Game c={c} s={sC} p={R} who="smooth" trail={36} trailFrom={i - 30} botTrail />
        <text x={L.x} y={150} fill={C.amber} fontFamily={SANS} fontWeight={700} fontSize={34}>YOU</text>
        <text x={R.x} y={150} fill={C.green} fontFamily={SANS} fontWeight={700} fontSize={34}>SMOOTH VERSION <tspan fill={C.dim} fontSize={24}>same moment, same 133 ms reaction</tspan></text>
        <Label x={960} y={870} anchor="middle" text={t > tC2 && t < tC2 + 4.2 ? "paused · zoomed 3.5×" : "⅓ speed · zoomed 3.5×"} />
        <Bracket a={[eL[0], fL.aim[1] + 60]} b={[fL.aim[0], fL.aim[1] + 60]} t={tC2 + 0.3} out={tC2 + 4.2} color={C.red} />
        <Bracket a={[eR[0], fR.aim[1] + 60]} b={[fR.aim[0], fR.aim[1] + 60]} t={tC2 + 0.9} out={tC2 + 4.2} color={C.green} />
        <Note x={960} y={930} t={tC2 + 1.3} anchor="middle" lines={["Same reaction. Half as far past…"]} out={tC2 + 4.4} />
        <Note x={960} y={930} t={tC2 + 4.6} anchor="middle" lines={["…and back on the bot sooner."]} />
      </Fade>
      <Chapter n={1} title="When it turns" />
    </g>
  );
};

// ================================================================ lesson 2: behind, sprint, brake
export const Lesson2: React.FC = () => {
  const t = useNow();
  const c = D.brake;
  const { sprint, brake } = c.mark;
  const a = sprint - 30, b = brake + 30;
  const Z: Panel = { x: 0, y: 0, w: 1920, h: 700, zoom: 2.5 };
  const sA = play(t, [[0.3, 20], [2.9, 136]]);
  // explain the graph first, then play
  const tP = 8.6, tF = tP + (brake + 8 - a) / 15;
  const sB = play(t, [[tP, a], [tF, brake + 8]]);
  const GX = 300, GY = 770, GW = 1250, GH = 170;
  const pS = graphPoint(c, sprint, a, b, GX, GY, GW, GH), pB = graphPoint(c, brake, a, b, GX, GY, GW, GH);
  const fB = aimVsBot(c, brake + 8, Z);
  const dir = botDir(c, brake + 8, Z);
  // side by side
  const L: Panel = { x: 40, y: 150, w: 900, h: 520, zoom: 3 }, R: Panel = { x: 980, y: 150, w: 900, h: 520, zoom: 3 };
  const tC = tF + 10.6;
  const sC = play(t, [[tC, a], [tC + (b - a) / 15, b]]);
  const top = graphTop(c, a, b);
  return (
    <g>
      <Fade t={t} a={0} b={3.25}>
        <Game c={c} s={sA} p={FULL} />
        <Label x={1890} y={1040} anchor="end" text={`Real speed · ${secs(c, 20)}`} />
      </Fade>
      <Fade t={t} a={2.95} b={tC + 0.1}>
        <rect width={1920} height={1080} fill={C.dark} />
        <Game c={c} s={sB} p={Z} trail={30} botTrail frame={false} />
        <Label x={1890} y={680} anchor="end" text={t < tP ? "zoomed 2.5×" : t < tF ? "¼ speed · zoomed 2.5×" : "paused · zoomed 2.5×"} />
        <SpeedGraph c={c} s={sB} a={a} b={b} x={GX} y={GY} w={GW} h={GH} botReveal={ramp(t, 4.9, 1.2)} axisOn={ramp(t, 3.3, 0.4)} />
        <Note x={960} y={620} t={3.4} anchor="middle" lines={["This graph is speed. Higher = moving faster."]} out={4.8} />
        <Note x={960} y={620} t={5.0} anchor="middle" lines={["Cyan line: how fast the bot moves. Pretty steady."]} out={7.7} />
        <Note x={960} y={620} t={7.8} anchor="middle" lines={["Orange line: how fast your crosshair moves."]} out={tP + 1.5} />
        <Loop cx={pS[0]} cy={pS[1]} rx={46} ry={36} t={tF + 0.3} color={C.red} />
        <Note x={pS[0] + 70} y={pS[1] + 4} t={tF + 0.6} size={42} lines={["too fast: catching up"]} />
        <Loop cx={pB[0]} cy={pB[1]} rx={46} ry={36} t={tF + 2.0} color={C.red} seed={8} />
        <Note x={pB[0] + 70} y={pB[1] - 40} t={tF + 2.3} size={42} lines={["too slow: braking"]} />
        <Marker pts={[[fB.b.x - dir[0] * 20, fB.b.y - fB.b.ry - 50], [fB.b.x + dir[0] * 170, fB.b.y - fB.b.ry - 50]]} t={tF + 3.8} dur={0.4} head color={C.bot} w={8} out={tF + 7.2} />
        <Note x={fB.b.x + dir[0] * 60} y={fB.b.y - fB.b.ry - 90} t={tF + 4.0} anchor="middle" lines={["It never slowed down."]} out={tF + 7.2} />
        <Bracket a={[fB.aim[0], fB.aim[1] + 60]} b={[fB.b.x - Math.sign(fB.b.x - fB.aim[0]) * fB.b.rx, fB.aim[1] + 60]} t={tF + 5.0} color={C.red} out={tF + 7.2} />
        <Note x={fB.aim[0]} y={fB.aim[1] + 140} t={tF + 5.3} anchor="middle" lines={["So you're behind it again."]} out={tF + 7.2} />
        <Note x={960} y={560} t={tF + 7.4} anchor="middle" size={50} lines={["When you're off the bot,", "9 times in 10 you're behind it, not past it."]} />
      </Fade>
      <Fade t={t} a={tC - 0.2} b={99}>
        <rect width={1920} height={1080} fill={C.dark} />
        <Game c={c} s={sC} p={L} trail={30} botTrail />
        <Game c={c} s={sC} p={R} who="smooth" trail={30} trailFrom={a} botTrail />
        <text x={L.x} y={130} fill={C.amber} fontFamily={SANS} fontWeight={700} fontSize={34}>YOU</text>
        <text x={R.x} y={130} fill={C.green} fontFamily={SANS} fontWeight={700} fontSize={34}>SMOOTH VERSION <tspan fill={C.dim} fontSize={24}>same 133 ms reaction</tspan></text>
        <SpeedGraph c={c} s={sC} a={a} b={b} x={L.x + 90} y={730} w={650} h={150} size={24} top={top} botReveal={1} />
        <SpeedGraph c={c} s={sC} a={a} b={b} x={R.x + 90} y={730} w={650} h={150} size={24} who="smooth" top={top} botReveal={1} />
        <Note x={1430} y={600} t={tC + (b - a) / 15 + 0.3} anchor="middle" size={42} lines={["Green stays on cyan:", "same speed as the bot."]} />
        <Note x={490} y={600} t={tC + (b - a) / 15 + 2.0} anchor="middle" size={42} lines={["Orange jumps above", "and below it."]} />
      </Fade>
      <Chapter n={2} title="Behind: sprint, then brake" />
    </g>
  );
};

// ================================================================ lesson 3: the far start
// Bars per 5 s of a round (average of all 21 runs), with the bot drawn at its real on-screen size under each.
export const Lesson3: React.FC = () => {
  const t = useNow();
  const c = D.far;
  const ch = D.chart;
  const avg = (a: number, b: number, k: "pps" | "dist") => ch.filter((q) => q.s >= a && q.s < b).reduce((s, q) => s + q[k], 0) / ch.filter((q) => q.s >= a && q.s < b).length;
  const blocks = [0, 5, 10, 15].map((s0) => ({ s0, pps: avg(s0, s0 + 5, "pps"), dist: avg(s0, s0 + 5, "dist") }));
  const X0 = 560, BW = 300, BASE = 650, PX = 34;
  const F = 960 / Math.tan((51.5 * Math.PI) / 180); // Ryan's 103° view on a 1920-wide screen
  // the far moment
  const freeze = 84;
  const Z: Panel = { x: 0, y: 0, w: 1920, h: 1080, zoom: 4 };
  const t1 = 14.3;
  const sA = play(t, [[t1, 30], [t1 + 2.0, 150]]);
  const t2 = t1 + 2.35, tF = t2 + (freeze - 40) / 24;
  const sB = play(t, [[t2, 40], [tF, freeze]]);
  const fB = aimVsBot(c, freeze, Z);
  const L: Panel = { x: 40, y: 170, w: 900, h: 660, zoom: 5 }, R: Panel = { x: 980, y: 170, w: 900, h: 660, zoom: 5 };
  const tC = tF + 7.2;
  const sC = play(t, [[tC, 40], [tC + 100 / 24, 140]]);
  const lab = { fill: C.ink, fontFamily: SANS, fontWeight: 600, fontSize: 28 } as const;
  const b0 = BASE - blocks[0].pps * PX;
  return (
    <g>
      <Fade t={t} a={0} b={t1 + 0.1}>
        <rect width={1920} height={1080} fill={C.dark} />
        <Marker pts={[[X0 - 10, BASE], [X0 + 4 * BW + 10, BASE]]} t={0.3} dur={0.5} color={C.dim} w={4} />
        {[0, 5, 10, 15, 20].map((s, k) => <text key={s} x={X0 + k * BW} y={BASE + 42} textAnchor="middle" {...lab} fill={C.dim} opacity={ramp(t, 0.5, 0.3)}>{`${s} s`}</text>)}
        <text x={X0 - 40} y={BASE + 42} textAnchor="end" {...lab} opacity={ramp(t, 0.5, 0.3)}>time in the round</text>
        <text x={X0 - 40} y={820} textAnchor="end" {...lab} opacity={ramp(t, 1.6, 0.3)}>how big it looks</text>
        <text x={X0 - 40} y={440} textAnchor="end" {...lab} opacity={ramp(t, 5.8, 0.3)}>points each second</text>
        {blocks.map((q, k) => {
          const cx = X0 + k * BW + BW / 2;
          const rx = (31.5 / q.dist) * F, ry = (49.5 / q.dist) * F;
          const pop = ramp(t, 1.8 + k * 0.35, 0.3);
          const grow = ramp(t, 5.9 + k * 0.3, 0.5);
          const hgt = q.pps * PX * grow;
          return (
            <g key={k}>
              <rect x={cx - rx} y={810 - ry} width={2 * rx} height={2 * ry} rx={rx} fill={C.bot} opacity={pop} />
              <rect x={cx - 90} y={BASE - hgt} width={180} height={hgt} rx={4} fill={k === 0 ? C.amber : "#8C7A5E"} />
              <text x={cx} y={BASE - hgt - 18} textAnchor="middle" fill={C.ink} fontFamily={SANS} fontWeight={700} fontSize={48} opacity={grow >= 1 ? 1 : 0}>{Math.round(q.pps)}</text>
            </g>
          );
        })}
        <Note x={960} y={170} t={0.4} anchor="middle" lines={["Each round lasts 20 seconds."]} out={2.9} />
        <Note x={960} y={170} t={3.0} anchor="middle" lines={["It starts far away (small) and walks in (big)."]} out={5.6} />
        <Note x={960} y={170} t={5.8} anchor="middle" lines={["How many points you score each second", "(average of your 21 runs)"]} out={8.6} />
        <Loop cx={X0 + BW / 2} cy={(b0 - 70 + 860) / 2} rx={150} ry={(860 - b0 + 70) / 2} t={8.8} color={C.red} />
        <Note x={960} y={170} t={9.0} anchor="middle" lines={["Far away, you score the least."]} out={11.6} />
        <Note x={960} y={170} t={11.8} anchor="middle" lines={["That's the start of every round, 3 times a run."]} />
      </Fade>
      <Fade t={t} a={t1} b={t2 + 0.05}>
        <Game c={c} s={sA} p={FULL} />
        <Label x={1890} y={1040} anchor="end" text={`Real speed · ${secs(c, 30)}`} />
      </Fade>
      <Fade t={t} a={t2 - 0.3} b={tC + 0.1}>
        <Game c={c} s={sB} p={Z} trail={40} botTrail />
        <Label x={1890} y={1040} anchor="end" text={t < tF ? "0.4× speed · zoomed 4×" : "paused · zoomed 4×"} />
        <Loop cx={fB.b.x} cy={fB.b.y} rx={fB.b.rx + 34} ry={fB.b.ry + 34} t={tF + 0.3} color={C.bot} seed={6} />
        <Note x={fB.b.x} y={fB.b.y - fB.b.ry - 60} t={tF + 0.6} anchor="middle" lines={["Far away it's tiny."]} />
        <Loop cx={fB.aim[0]} cy={fB.aim[1]} rx={36} t={tF + 2.1} color={C.red} seed={2} />
        <Note x={960} y={860} t={tF + 2.5} anchor="middle" size={52} lines={["Same wobble as up close. Smaller bot."]} />
      </Fade>
      <Fade t={t} a={tC - 0.2} b={99}>
        <rect width={1920} height={1080} fill={C.dark} />
        <Game c={c} s={sC} p={L} trail={40} botTrail />
        <Game c={c} s={sC} p={R} who="smooth" trail={40} trailFrom={40} botTrail />
        <text x={L.x} y={150} fill={C.amber} fontFamily={SANS} fontWeight={700} fontSize={34}>YOU</text>
        <text x={R.x} y={150} fill={C.green} fontFamily={SANS} fontWeight={700} fontSize={34}>SMOOTH VERSION <tspan fill={C.dim} fontSize={24}>same 133 ms reaction</tspan></text>
        <Label x={960} y={870} anchor="middle" text="0.4× speed · zoomed 5×" />
        <Note x={1430} y={930} t={tC + 1.6} anchor="middle" lines={["Small, slow, steady. It stays on."]} />
      </Fade>
      <Chapter n={3} title="The far start" />
    </g>
  );
};

// ================================================================ what's fine
export const Fine: React.FC = () => {
  const t = useNow();
  const c = D.open;
  return (
    <g>
      <Game c={c} s={play(t, [[0, 0], [9, 270]])} p={FULL} dimmed={0.72} />
      <Note x={300} y={300} t={0.3} size={56} lines={["Not your problem:"]} />
      <Tick x={330} y={430} t={1.2} />
      <Note x={390} y={448} t={1.4} lines={["Reaction: 133 ms, the same every run."]} />
      <Tick x={330} y={560} t={3.6} />
      <Note x={390} y={578} t={3.8} lines={["Up-down hops: almost never why you miss."]} />
      <Note x={390} y={650} t={5.2} size={40} color={C.dim} lines={["Leave them for now."]} />
    </g>
  );
};

// ================================================================ what to do
const Mini: React.FC<{ k: number; x: number; y: number; t: number }> = ({ k, x, y, t }) => {
  const now = useNow();
  const op = life(now, t, undefined, 0.2);
  if (now < t) return null;
  if (k === 1)
    return (
      <g opacity={op}>
        <rect x={x - 18} y={y - 20} width={36} height={40} rx={18} fill={C.bot} />
        <Marker pts={[[x - 10, y + 44], [x - 80, y + 44]]} t={t + 0.2} dur={0.3} head color={C.bot} w={6} />
        <Marker pts={[[x + 120, y], [x + 22, y]]} t={t + 0.5} dur={0.35} color={C.green} w={6} />
        <circle cx={x + 22} cy={y} r={7} fill={C.green} />
      </g>
    );
  if (k === 2)
    return (
      <g opacity={op}>
        <Marker pts={[[x - 80, y + 10], [x + 120, y + 10]]} t={t + 0.2} dur={0.4} color={C.bot} w={6} />
        <Marker pts={[[x - 80, y - 4], [x + 120, y - 4]]} t={t + 0.4} dur={0.4} color={C.green} w={6} seed={3} />
      </g>
    );
  return (
    <g opacity={op}>
      <rect x={x - 7} y={y - 8} width={14} height={16} rx={7} fill={C.bot} />
      <circle cx={x - 2} cy={y} r={4} fill={C.green} />
      <Loop cx={x} cy={y} rx={34} t={t + 0.3} color={C.ink} w={4} />
    </g>
  );
};
export const ToDo: React.FC = () => {
  const cues = [
    "When it turns: stop your hand, then follow.",
    "Match its speed. No sprint, no brake.",
    "First 5 s of each round: small and slow.",
  ];
  return (
    <g>
      <rect width={1920} height={1080} fill={C.dark} />
      <Note x={250} y={220} t={0.2} size={60} lines={["What to do next session"]} />
      {cues.map((q, k) => (
        <g key={k}>
          <Mini k={k + 1} x={360} y={400 + k * 190} t={1.0 + k * 3.2} />
          <Note x={560} y={418 + k * 190} t={1.2 + k * 3.2} size={50} lines={[`${k + 1}. ${q}`]} />
        </g>
      ))}
      <Note x={560} y={920} t={11.2} size={36} color={C.dim} lines={["Cue 1 is your own note from Oct 8: land on the near edge."]} />
    </g>
  );
};

export const End: React.FC = () => {
  const t = useNow();
  return (
    <g>
      <Game c={D.open} s={play(t, [[0, 120], [4, 240]])} p={FULL} dimmed={0.7} />
      <Note x={960} y={520} t={0.2} anchor="middle" size={52} lines={["Built from your 21 Zeus runs, Oct 8–10."]} />
      <Label x={960} y={600} t={0.6} anchor="middle" text="The smooth version is a model with your reaction time, not a recording." />
    </g>
  );
};

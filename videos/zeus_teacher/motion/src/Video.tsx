import React from "react";
import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";
import { Finish, ramp } from "./kit";
import { End, Fine, HowItMoves, Lesson1, Lesson2, Lesson3, Open, ToDo } from "./scenes";

const FPS = 30;
const XF = 0.3; // dissolve between scenes (s)
export const SCENES: [string, React.FC, number][] = [
  ["open", Open, 10.5],
  ["moves", HowItMoves, 14],
  ["lesson1", Lesson1, 28],
  ["lesson2", Lesson2, 27.5],
  ["lesson3", Lesson3, 28],
  ["fine", Fine, 8],
  ["todo", ToDo, 15],
  ["end", End, 4],
];
export const START: number[] = [];
let acc = 0;
for (const [, , d] of SCENES) { START.push(acc); acc += d; }
export const TOTAL = acc + XF;

const Fader: React.FC<{ first: boolean; children: React.ReactNode }> = ({ first, children }) => {
  const t = useCurrentFrame() / FPS;
  return <g opacity={first ? 1 : ramp(t, 0, XF)}>{children}</g>;
};

export const Zeus: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: "#14110E" }}>
    {SCENES.map(([name, S, d], k) => (
      <Sequence key={name} name={name} from={Math.round(START[k] * FPS)} durationInFrames={Math.round((d + XF) * FPS)} layout="none">
        <AbsoluteFill>
          <svg width={1920} height={1080} viewBox="0 0 1920 1080">
            <Fader first={k === 0}><S /></Fader>
          </svg>
        </AbsoluteFill>
      </Sequence>
    ))}
    <AbsoluteFill>
      <svg width={1920} height={1080} viewBox="0 0 1920 1080"><Finish /></svg>
    </AbsoluteFill>
  </AbsoluteFill>
);

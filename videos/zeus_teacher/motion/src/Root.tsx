import React from "react";
import { Composition } from "remotion";
import { TOTAL, Zeus } from "./Video";

export const RemotionRoot: React.FC = () => <Composition id="Zeus" component={Zeus} durationInFrames={Math.ceil(TOTAL * 30)} fps={30} width={1920} height={1080} />;

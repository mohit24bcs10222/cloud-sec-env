import { AbsoluteFill, Sequence } from "remotion";
import { Hook } from "./scenes/Hook";
import { ThemeCard } from "./scenes/ThemeCard";
import { Environment } from "./scenes/Environment";
import { RewardDesign } from "./scenes/RewardDesign";
import { Results } from "./scenes/Results";
import { Closing } from "./scenes/Closing";
import { FPS } from "./theme";

const sec = (s: number) => Math.round(s * FPS);

export const BEATS = [
  { component: Hook, durationSec: 15 },
  { component: ThemeCard, durationSec: 25 },
  { component: Environment, durationSec: 30 },
  { component: RewardDesign, durationSec: 35 },
  { component: Results, durationSec: 30 },
  { component: Closing, durationSec: 15 },
] as const;

export const TOTAL_FRAMES = BEATS.reduce(
  (acc, b) => acc + sec(b.durationSec),
  0,
);

export const Main: React.FC = () => {
  let cursor = 0;
  return (
    <AbsoluteFill style={{ background: "#0b1020" }}>
      {BEATS.map((b, i) => {
        const start = cursor;
        const dur = sec(b.durationSec);
        cursor += dur;
        const C = b.component;
        return (
          <Sequence key={i} from={start} durationInFrames={dur} layout="none">
            <C />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

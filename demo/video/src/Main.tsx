import { AbsoluteFill, Sequence } from "remotion";
import { Hook } from "./scenes/Hook";
import { EnvOverview } from "./scenes/EnvOverview";
import { OpusRollout } from "./scenes/OpusRollout";
import { RewardDesign } from "./scenes/RewardDesign";
import { Results } from "./scenes/Results";
import { Takeaway } from "./scenes/Takeaway";
import { FPS } from "./theme";

const sec = (s: number) => Math.round(s * FPS);

export const BEATS = [
  { component: Hook, durationSec: 15 },
  { component: EnvOverview, durationSec: 15 },
  { component: OpusRollout, durationSec: 25 },
  { component: RewardDesign, durationSec: 30 },
  { component: Results, durationSec: 25 },
  { component: Takeaway, durationSec: 10 },
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

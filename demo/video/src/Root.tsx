import "./index.css";
import { Composition } from "remotion";
import { Main, TOTAL_FRAMES } from "./Main";
import { FPS, WIDTH, HEIGHT } from "./theme";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="CloudSecEnvDemo"
        component={Main}
        durationInFrames={TOTAL_FRAMES}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
      />
    </>
  );
};

import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { theme } from "../theme";

export const SceneTitle: React.FC<{ kicker: string; title: string }> = ({
  kicker,
  title,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 18, stiffness: 120 } });
  const y = interpolate(s, [0, 1], [20, 0]);
  return (
    <div style={{ opacity: s, transform: `translateY(${y}px)` }}>
      <div
        style={{
          color: theme.accent,
          fontSize: 22,
          fontWeight: 600,
          letterSpacing: 4,
          textTransform: "uppercase",
          marginBottom: 10,
        }}
      >
        {kicker}
      </div>
      <div
        style={{
          color: theme.text,
          fontSize: 64,
          fontWeight: 800,
          lineHeight: 1.1,
        }}
      >
        {title}
      </div>
    </div>
  );
};

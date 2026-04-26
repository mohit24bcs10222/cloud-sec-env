import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
  Sequence,
} from "remotion";
import { theme } from "../theme";

const TitleCard: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = spring({ frame, fps, config: { damping: 18, stiffness: 110 } });
  const fadeOut = interpolate(frame, [fps * 4, fps * 4.8], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        opacity: fadeOut,
      }}
    >
      <div
        style={{
          opacity: sp,
          transform: `translateY(${interpolate(sp, [0, 1], [20, 0])}px)`,
          textAlign: "center",
        }}
      >
        <div
          style={{
            color: theme.accent,
            fontSize: 26,
            letterSpacing: 6,
            fontWeight: 600,
            textTransform: "uppercase",
            marginBottom: 28,
          }}
        >
          OpenEnv Hackathon
        </div>
        <div
          style={{
            color: theme.text,
            fontSize: 84,
            fontWeight: 800,
            lineHeight: 1.05,
            marginBottom: 18,
          }}
        >
          Theme 3
        </div>
        <div
          style={{
            color: theme.textMuted,
            fontSize: 38,
            fontWeight: 500,
          }}
        >
          Professional Tasks · World Modeling
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Speaker: React.FC<{
  who: string;
  role: string;
  line: string;
  followup?: string;
  align: "left" | "right";
  color: string;
  delay: number;
  followupDelay?: number;
}> = ({ who, role, line, followup, align, color, delay, followupDelay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = spring({
    frame: frame - delay,
    fps,
    config: { damping: 18, stiffness: 100 },
  });
  const followSp = followup
    ? spring({
        frame: frame - (followupDelay ?? delay + 30),
        fps,
        config: { damping: 18, stiffness: 100 },
      })
    : 0;
  const slide = interpolate(sp, [0, 1], [align === "left" ? -40 : 40, 0]);
  return (
    <div
      style={{
        opacity: sp,
        transform: `translateX(${slide}px)`,
        alignSelf: align === "left" ? "flex-start" : "flex-end",
        maxWidth: 880,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          marginBottom: 14,
          flexDirection: align === "right" ? "row-reverse" : "row",
        }}
      >
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: 48,
            background: color,
            color: "#0b1020",
            fontSize: 22,
            fontWeight: 800,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: `0 0 18px ${color}55`,
          }}
        >
          {who[0]}
        </div>
        <div style={{ textAlign: align }}>
          <div
            style={{
              color: theme.text,
              fontSize: 22,
              fontWeight: 700,
            }}
          >
            {who}
          </div>
          <div
            style={{
              color: theme.textMuted,
              fontSize: 16,
              letterSpacing: 2,
              textTransform: "uppercase",
            }}
          >
            {role}
          </div>
        </div>
      </div>
      <div
        style={{
          background: theme.panel,
          border: `1px solid ${color}55`,
          borderRadius: 16,
          padding: "22px 28px",
          color: theme.text,
          fontSize: 30,
          fontWeight: 500,
          lineHeight: 1.4,
        }}
      >
        “{line}”
        {followup ? (
          <span style={{ opacity: followSp }}>
            <span style={{ color }}> {followup}</span>
          </span>
        ) : null}
      </div>
    </div>
  );
};

const Dialogue: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = spring({ frame, fps, config: { damping: 20, stiffness: 80 } });
  return (
    <AbsoluteFill style={{ padding: 80, justifyContent: "center" }}>
      <div
        style={{
          opacity: sp,
          color: theme.accent,
          fontSize: 22,
          letterSpacing: 4,
          fontWeight: 600,
          textTransform: "uppercase",
          marginBottom: 8,
        }}
      >
        The capability gap
      </div>
      <div
        style={{
          opacity: sp,
          color: theme.text,
          fontSize: 56,
          fontWeight: 800,
          lineHeight: 1.05,
          marginBottom: 56,
          maxWidth: 1500,
        }}
      >
        Frontier models name the cause. They miss the senior move:
        <br />
        <span style={{ color: theme.amber }}>ruling out the wrong one.</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 36 }}>
        <Speaker
          who="Junior"
          role="ships the first hypothesis"
          line="It's the database."
          align="left"
          color={theme.cyan}
          delay={20}
        />
        <Speaker
          who="Senior"
          role="rules out the wrong one"
          line="It's the database — and here's why it's not the load balancer."
          align="right"
          color={theme.amber}
          delay={70}
        />
      </div>
    </AbsoluteFill>
  );
};

export const ThemeCard: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at top, ${theme.bgAccent}, ${theme.bg} 70%)`,
      }}
    >
      <Sequence from={0} durationInFrames={fps * 5} layout="none">
        <TitleCard />
      </Sequence>
      <Sequence from={fps * 5} layout="none">
        <Dialogue />
      </Sequence>
    </AbsoluteFill>
  );
};

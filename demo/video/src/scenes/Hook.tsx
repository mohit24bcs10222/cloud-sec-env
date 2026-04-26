import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { theme } from "../theme";
import { Caption } from "../components/Caption";

const Pulse: React.FC<{ children: React.ReactNode; delay?: number }> = ({
  children,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({
    frame: frame - delay,
    fps,
    config: { damping: 14, stiffness: 90 },
  });
  return (
    <div
      style={{
        opacity: s,
        transform: `scale(${interpolate(s, [0, 1], [0.92, 1])})`,
      }}
    >
      {children}
    </div>
  );
};

export const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const flash = Math.sin((frame / fps) * 2 * Math.PI * 1.2) * 0.5 + 0.5;

  // Caption switches mid-beat
  const showSecond = frame > 7 * fps;

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at top, ${theme.bgAccent}, ${theme.bg} 70%)`,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <Pulse delay={4}>
        <div
          style={{
            background: theme.panel,
            border: `2px solid ${theme.red}`,
            borderRadius: 18,
            padding: "32px 56px",
            minWidth: 1100,
            boxShadow: `0 0 ${40 + flash * 30}px ${theme.red}55`,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 18,
              marginBottom: 14,
            }}
          >
            <div
              style={{
                width: 16,
                height: 16,
                borderRadius: 16,
                background: theme.red,
                boxShadow: `0 0 16px ${theme.red}`,
              }}
            />
            <div
              style={{
                color: theme.red,
                fontSize: 22,
                fontWeight: 700,
                letterSpacing: 4,
              }}
            >
              SEV-2 · PAGED
            </div>
            <div
              style={{
                marginLeft: "auto",
                color: theme.textMuted,
                fontFamily: theme.mono,
                fontSize: 20,
              }}
            >
              02:14:07 UTC
            </div>
          </div>
          <div
            style={{
              color: theme.text,
              fontSize: 44,
              fontWeight: 700,
              fontFamily: theme.mono,
              marginBottom: 8,
            }}
          >
            auth_svc_5xx_rate_cloud2
          </div>
          <div style={{ color: theme.textMuted, fontSize: 26 }}>
            error rate <span style={{ color: theme.red }}>8.7%</span> ·
            tenant <span style={{ color: theme.amber }}>acme-corp</span> ·
            cloud-2 <span style={{ color: theme.red }}>↑</span>
          </div>
        </div>
      </Pulse>

      <div
        style={{
          marginTop: 44,
          color: theme.textMuted,
          fontSize: 28,
          fontFamily: theme.mono,
          opacity: interpolate(frame, [12, 30], [0, 1], {
            extrapolateRight: "clamp",
          }),
        }}
      >
        30 tool calls. one answer.
      </div>

      <Caption
        text={
          showSecond
            ? "We built an environment that turns this into a benchmark — and a reward signal that captures what senior SREs actually do."
            : "It's 2 a.m. Your cloud platform just paged you. One region throws 8.7% errors. You have 30 tool calls and a single answer."
        }
      />
    </AbsoluteFill>
  );
};

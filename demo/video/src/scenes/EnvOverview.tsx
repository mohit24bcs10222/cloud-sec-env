import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { theme } from "../theme";
import { Caption } from "../components/Caption";
import { SceneTitle } from "../components/SceneTitle";

const Cloud: React.FC<{
  name: string;
  status: "ok" | "alert";
  delay: number;
}> = ({ name, status, delay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({
    frame: frame - delay,
    fps,
    config: { damping: 16, stiffness: 100 },
  });
  const color = status === "alert" ? theme.red : theme.green;
  return (
    <div
      style={{
        opacity: s,
        transform: `translateY(${interpolate(s, [0, 1], [20, 0])}px)`,
        background: theme.panel,
        border: `2px solid ${color}55`,
        borderRadius: 14,
        padding: "20px 24px",
        width: 280,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            width: 12,
            height: 12,
            borderRadius: 12,
            background: color,
            boxShadow: `0 0 12px ${color}`,
          }}
        />
        <div
          style={{
            color: theme.text,
            fontSize: 24,
            fontWeight: 700,
            fontFamily: theme.mono,
          }}
        >
          {name}
        </div>
      </div>
      <div style={{ marginTop: 14, display: "grid", gap: 6 }}>
        {[
          "auth-svc",
          "sts-broker",
          "api-gw",
          "billing-svc",
          "kms-proxy",
        ].map((svc) => (
          <div
            key={svc}
            style={{
              color: theme.textMuted,
              fontFamily: theme.mono,
              fontSize: 18,
            }}
          >
            · {svc}
          </div>
        ))}
      </div>
    </div>
  );
};

const ToolPill: React.FC<{ name: string; delay: number }> = ({
  name,
  delay,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({
    frame: frame - delay,
    fps,
    config: { damping: 14, stiffness: 110 },
  });
  return (
    <div
      style={{
        opacity: s,
        transform: `scale(${interpolate(s, [0, 1], [0.85, 1])})`,
        background: theme.panelLight,
        border: `1px solid ${theme.accent}55`,
        color: theme.text,
        padding: "10px 22px",
        borderRadius: 999,
        fontFamily: theme.mono,
        fontSize: 22,
        fontWeight: 500,
      }}
    >
      {name}
    </div>
  );
};

export const EnvOverview: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: theme.bg, padding: 80 }}>
      <SceneTitle kicker="The environment" title="Three clouds. Six tools. Real noise." />

      <div
        style={{
          display: "flex",
          gap: 36,
          marginTop: 60,
          justifyContent: "center",
        }}
      >
        <Cloud name="cloud-1" status="ok" delay={6} />
        <Cloud name="cloud-2" status="alert" delay={12} />
        <Cloud name="cloud-3" status="ok" delay={18} />
      </div>

      <div
        style={{
          marginTop: 56,
          display: "flex",
          flexWrap: "wrap",
          gap: 16,
          justifyContent: "center",
        }}
      >
        {[
          "logs_search",
          "trace_get",
          "metric_query",
          "ticket_search",
          "slack_search",
          "kb_search",
        ].map((t, i) => (
          <ToolPill key={t} name={t} delay={36 + i * 5} />
        ))}
      </div>

      <Caption text="Three clouds. Six tools — logs, traces, metrics, tickets, Slack, an internal KB. Messy-but-coherent. Real production noise." />
    </AbsoluteFill>
  );
};

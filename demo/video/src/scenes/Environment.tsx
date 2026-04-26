import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
  Sequence,
} from "remotion";
import { theme } from "../theme";
import { SceneTitle } from "../components/SceneTitle";

const TOOLS = [
  "logs_search",
  "metric_query",
  "trace_get",
  "ticket_search",
  "slack_search",
  "kb_search",
];

const Cloud: React.FC<{
  name: string;
  status: "ok" | "alert";
  delay: number;
}> = ({ name, status, delay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = spring({
    frame: frame - delay,
    fps,
    config: { damping: 16, stiffness: 100 },
  });
  const color = status === "alert" ? theme.red : theme.green;
  return (
    <div
      style={{
        opacity: sp,
        transform: `translateY(${interpolate(sp, [0, 1], [16, 0])}px)`,
        background: theme.panel,
        border: `2px solid ${color}66`,
        borderRadius: 12,
        padding: "14px 22px",
        minWidth: 200,
        textAlign: "center",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 10,
        }}
      >
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
            fontFamily: theme.mono,
            fontSize: 24,
            fontWeight: 700,
          }}
        >
          {name}
        </div>
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
  const sp = spring({
    frame: frame - delay,
    fps,
    config: { damping: 14, stiffness: 110 },
  });
  return (
    <div
      style={{
        opacity: sp,
        transform: `scale(${interpolate(sp, [0, 1], [0.85, 1])})`,
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

type Step = {
  step: number;
  call: string;
  result: string;
  highlight?: "amber" | "green" | "red";
};

const STEPS: Step[] = [
  { step: 1, call: "kb_search(query=\"oidc rotation\")", result: "runbook hit · sts-broker pubkey rotation" },
  { step: 4, call: "logs_search(cloud=cloud-2, service=auth-svc)", result: "423 lines · WARN signature_invalid", highlight: "red" },
  { step: 9, call: "ticket_search(query=\"OIDC\")", result: "CHG-1891 · CHG-1888 (same engineer, 1 day apart)", highlight: "amber" },
  { step: 13, call: "metric_query(auth_5xx_rate by cloud)", result: "cloud-1: 0.1% · cloud-2: 8.7% · cloud-3: 0.0%" },
  { step: 16, call: "slack_search(channel=#infra-terraform)", result: "m.chen: state-lock contention 04-12", highlight: "green" },
];

const StepRow: React.FC<{ s: Step; appearAt: number }> = ({ s, appearAt }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = spring({
    frame: frame - appearAt,
    fps,
    config: { damping: 18, stiffness: 110 },
  });
  const accent =
    s.highlight === "amber"
      ? theme.amber
      : s.highlight === "green"
      ? theme.green
      : s.highlight === "red"
      ? theme.red
      : theme.accent;
  return (
    <div
      style={{
        opacity: sp,
        transform: `translateX(${interpolate(sp, [0, 1], [-24, 0])}px)`,
        background: s.highlight ? theme.panelLight : theme.panel,
        border: `1px solid ${s.highlight ? accent + "88" : theme.panelLight}`,
        borderRadius: 10,
        padding: "14px 20px",
        marginBottom: 12,
        fontFamily: theme.mono,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 16 }}>
        <span
          style={{
            color: accent,
            fontSize: 18,
            fontWeight: 700,
            minWidth: 80,
          }}
        >
          step {String(s.step).padStart(2, "0")}
        </span>
        <span style={{ color: theme.text, fontSize: 22, fontWeight: 500 }}>
          {s.call}
        </span>
      </div>
      <div
        style={{
          color: theme.textMuted,
          fontSize: 19,
          marginTop: 6,
          paddingLeft: 96,
        }}
      >
        → {s.result}
      </div>
    </div>
  );
};

const TicketSplit: React.FC<{ delay: number }> = ({ delay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = spring({
    frame: frame - delay,
    fps,
    config: { damping: 18, stiffness: 100 },
  });
  return (
    <div
      style={{
        opacity: sp,
        transform: `translateY(${interpolate(sp, [0, 1], [20, 0])}px)`,
        marginTop: 36,
        display: "flex",
        gap: 28,
      }}
    >
      <TicketCard
        id="CHG-1888"
        verdict="not the cause"
        detail="shipped to cloud-1 AND cloud-2 — but cloud-1 is healthy"
        color={theme.textMuted}
        cross
      />
      <TicketCard
        id="CHG-1891"
        verdict="root cause"
        detail="OIDC key rotation · failed silently on cloud-2 due to tf state-lock contention"
        color={theme.green}
      />
    </div>
  );
};

const TicketCard: React.FC<{
  id: string;
  verdict: string;
  detail: string;
  color: string;
  cross?: boolean;
}> = ({ id, verdict, detail, color, cross }) => (
  <div
    style={{
      flex: 1,
      background: theme.panel,
      border: `1px solid ${color}66`,
      borderRadius: 14,
      padding: 22,
      position: "relative",
    }}
  >
    {cross ? (
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: 12,
          right: 12,
          height: 2,
          background: theme.red + "cc",
          transform: "translateY(-50%)",
        }}
      />
    ) : null}
    <div
      style={{
        color: color,
        fontSize: 16,
        fontWeight: 700,
        letterSpacing: 3,
        textTransform: "uppercase",
        marginBottom: 6,
      }}
    >
      {verdict}
    </div>
    <div
      style={{
        color: theme.text,
        fontSize: 32,
        fontWeight: 700,
        fontFamily: theme.mono,
        marginBottom: 8,
      }}
    >
      {id}
    </div>
    <div style={{ color: theme.textMuted, fontSize: 19, lineHeight: 1.4 }}>
      {detail}
    </div>
  </div>
);

const SetupPanel: React.FC = () => {
  return (
    <AbsoluteFill style={{ padding: 80 }}>
      <SceneTitle
        kicker="The environment"
        title="Six tools. Three clouds. One real failure."
      />
      <div
        style={{
          display: "flex",
          gap: 22,
          marginTop: 50,
          justifyContent: "center",
        }}
      >
        <Cloud name="cloud-1" status="ok" delay={4} />
        <Cloud name="cloud-2" status="alert" delay={10} />
        <Cloud name="cloud-3" status="ok" delay={16} />
      </div>
      <div
        style={{
          marginTop: 40,
          display: "flex",
          flexWrap: "wrap",
          gap: 14,
          justifyContent: "center",
        }}
      >
        {TOOLS.map((t, i) => (
          <ToolPill key={t} name={t} delay={28 + i * 5} />
        ))}
      </div>
    </AbsoluteFill>
  );
};

const InvestigationPanel: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ padding: 80 }}>
      <SceneTitle
        kicker="The investigation"
        title="Two suspects. Only one ships to a healthy cloud."
      />
      <div style={{ marginTop: 36, maxWidth: 1700 }}>
        {STEPS.map((s, i) => (
          <StepRow
            key={s.step}
            s={s}
            appearAt={Math.round(20 + i * fps * 1.2)}
          />
        ))}
      </div>
      <TicketSplit delay={Math.round(20 + STEPS.length * fps * 1.2 + 10)} />
    </AbsoluteFill>
  );
};

export const Environment: React.FC = () => {
  const { fps, durationInFrames } = useVideoConfig();
  const setupDur = Math.round(fps * 9);
  const investigationDur = durationInFrames - setupDur;
  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <Sequence from={0} durationInFrames={setupDur} layout="none">
        <SetupPanel />
      </Sequence>
      <Sequence from={setupDur} durationInFrames={investigationDur} layout="none">
        <InvestigationPanel />
      </Sequence>
    </AbsoluteFill>
  );
};

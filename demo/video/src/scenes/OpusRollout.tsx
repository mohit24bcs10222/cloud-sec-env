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

type Step = {
  step: number;
  call: string;
  result: string;
  highlight?: boolean;
};

const STEPS: Step[] = [
  {
    step: 1,
    call: "logs_search(cloud=cloud-2, service=auth-svc)",
    result: "423 lines · WARN signature_invalid",
  },
  {
    step: 5,
    call: "trace_get(trace_id=tr_8b3c01)",
    result: "JWT verify failed at sts-broker",
    highlight: true,
  },
  {
    step: 8,
    call: "ticket_search(query=OIDC rotation)",
    result: "CHG-1891 · CHG-1888 · CHG-1872",
  },
  {
    step: 14,
    call: "slack_search(channel=#infra-terraform)",
    result: "m.chen: state-lock contention 04-12",
    highlight: true,
  },
  {
    step: 18,
    call: "metric_query(auth_5xx_rate by cloud)",
    result: "cloud-1: 0.1% · cloud-2: 8.7% · cloud-3: 0.0%",
  },
  {
    step: 22,
    call: "submit_answer(...)",
    result: "root_cause: tf state-lock dropped key on cloud-2",
    highlight: true,
  },
];

const StepRow: React.FC<{ s: Step; appearAt: number }> = ({ s, appearAt }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = spring({
    frame: frame - appearAt,
    fps,
    config: { damping: 18, stiffness: 110 },
  });
  return (
    <div
      style={{
        opacity: sp,
        transform: `translateX(${interpolate(sp, [0, 1], [-20, 0])}px)`,
        background: s.highlight ? theme.panelLight : theme.panel,
        border: `1px solid ${
          s.highlight ? theme.amber + "88" : theme.panelLight
        }`,
        borderRadius: 10,
        padding: "16px 22px",
        marginBottom: 12,
        fontFamily: theme.mono,
      }}
    >
      <div
        style={{ display: "flex", alignItems: "baseline", gap: 16 }}
      >
        <span
          style={{
            color: s.highlight ? theme.amber : theme.accent,
            fontSize: 18,
            fontWeight: 700,
            minWidth: 70,
          }}
        >
          step {String(s.step).padStart(2, "0")}
        </span>
        <span
          style={{ color: theme.text, fontSize: 22, fontWeight: 500 }}
        >
          {s.call}
        </span>
      </div>
      <div
        style={{
          color: theme.textMuted,
          fontSize: 19,
          marginTop: 6,
          paddingLeft: 86,
        }}
      >
        → {s.result}
      </div>
    </div>
  );
};

export const OpusRollout: React.FC = () => {
  const { fps } = useVideoConfig();
  const totalSec = 25;
  const stepInterval = (totalSec * fps - 60) / STEPS.length;

  return (
    <AbsoluteFill style={{ background: theme.bg, padding: 80 }}>
      <SceneTitle
        kicker="Watch Opus 4.5 investigate"
        title="Two suspects. Only one ships to a healthy cloud."
      />

      <div style={{ marginTop: 50, maxWidth: 1500 }}>
        {STEPS.map((s, i) => (
          <StepRow
            key={s.step}
            s={s}
            appearAt={Math.round(20 + i * stepInterval)}
          />
        ))}
      </div>

      <Caption text="JWT signature failures → Terraform key rotation. Two suspects: CHG-1891 and CHG-1888. The right answer rules out the wrong one — CHG-1888 also shipped to cloud-1, and cloud-1 is healthy." />
    </AbsoluteFill>
  );
};

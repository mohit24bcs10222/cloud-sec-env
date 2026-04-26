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

const KEYWORD_DIMS = [
  { label: "names CHG-1891", pass: true },
  { label: "names cloud-2", pass: true },
  { label: "mentions state-lock", pass: true },
  { label: "mentions key rotation", pass: true },
  { label: "names sts-broker", pass: true },
  { label: "names auth-svc", pass: true },
];

const JUDGE_DIMS = [
  { label: "root_cause_correct", score: 0.95 },
  { label: "fix_actionable", score: 0.9 },
  { label: "evidence_supported_claims", score: 0.88, highlight: true },
  { label: "explicit_elimination", score: 0.92, highlight: true },
  { label: "investigation_efficiency", score: 0.8 },
  { label: "blast_radius_correct", score: 0.85 },
  { label: "tool_use_quality", score: 0.78 },
  { label: "answer_clarity", score: 0.9 },
  { label: "diagnostic_depth", score: 0.86 },
];

const Check: React.FC<{ pass: boolean }> = ({ pass }) => (
  <div
    style={{
      width: 24,
      height: 24,
      borderRadius: 24,
      background: pass ? theme.green : theme.red,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      color: "#0b1020",
      fontWeight: 800,
      fontSize: 16,
    }}
  >
    {pass ? "✓" : "✗"}
  </div>
);

const ScoreBar: React.FC<{
  score: number;
  highlight?: boolean;
  delay: number;
}> = ({ score, highlight, delay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = spring({
    frame: frame - delay,
    fps,
    config: { damping: 20, stiffness: 80 },
  });
  const color = highlight ? theme.amber : theme.cyan;
  return (
    <div
      style={{
        height: 10,
        background: theme.bgAccent,
        borderRadius: 8,
        overflow: "hidden",
        flex: 1,
      }}
    >
      <div
        style={{
          width: `${sp * score * 100}%`,
          height: "100%",
          background: color,
          boxShadow: `0 0 10px ${color}88`,
        }}
      />
    </div>
  );
};

export const RewardDesign: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rightAppears = 4 * fps;
  const rightSpring = spring({
    frame: frame - rightAppears,
    fps,
    config: { damping: 18, stiffness: 100 },
  });

  return (
    <AbsoluteFill style={{ background: theme.bg, padding: 80 }}>
      <SceneTitle
        kicker="The reward function"
        title="Composable. Trajectory-aware. Hard to game."
      />

      <div style={{ display: "flex", gap: 32, marginTop: 50, height: 720 }}>
        {/* Left: keyword rubric */}
        <div
          style={{
            flex: 1,
            background: theme.panel,
            border: `1px solid ${theme.panelLight}`,
            borderRadius: 16,
            padding: 32,
          }}
        >
          <div
            style={{
              color: theme.accent,
              fontSize: 18,
              fontWeight: 700,
              letterSpacing: 3,
              textTransform: "uppercase",
            }}
          >
            Primary · deterministic
          </div>
          <div
            style={{
              color: theme.text,
              fontSize: 32,
              fontWeight: 700,
              marginTop: 4,
            }}
          >
            Keyword rubric (6 dims)
          </div>
          <div style={{ color: theme.textMuted, fontSize: 18, marginTop: 6 }}>
            no API key · runs in milliseconds
          </div>

          <div style={{ marginTop: 28 }}>
            {KEYWORD_DIMS.map((d, i) => {
              const sp = spring({
                frame: frame - (10 + i * 6),
                fps,
                config: { damping: 16, stiffness: 100 },
              });
              return (
                <div
                  key={d.label}
                  style={{
                    opacity: sp,
                    display: "flex",
                    alignItems: "center",
                    gap: 14,
                    padding: "12px 0",
                    borderBottom: `1px solid ${theme.panelLight}`,
                    fontFamily: theme.mono,
                    fontSize: 22,
                    color: theme.text,
                  }}
                >
                  <Check pass={d.pass} />
                  {d.label}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: LLM judge */}
        <div
          style={{
            flex: 1.15,
            background: theme.panel,
            border: `1px solid ${theme.purple}55`,
            borderRadius: 16,
            padding: 32,
            opacity: rightSpring,
            transform: `translateX(${interpolate(rightSpring, [0, 1], [40, 0])}px)`,
          }}
        >
          <div
            style={{
              color: theme.purple,
              fontSize: 18,
              fontWeight: 700,
              letterSpacing: 3,
              textTransform: "uppercase",
            }}
          >
            Auxiliary · Sonnet judge
          </div>
          <div
            style={{
              color: theme.text,
              fontSize: 32,
              fontWeight: 700,
              marginTop: 4,
            }}
          >
            Trajectory-aware (9 dims)
          </div>
          <div style={{ color: theme.textMuted, fontSize: 18, marginTop: 6 }}>
            grades the answer against the actual tool-call trail
          </div>

          <div style={{ marginTop: 22 }}>
            {JUDGE_DIMS.map((d, i) => (
              <div
                key={d.label}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                  padding: "10px 0",
                }}
              >
                <div
                  style={{
                    fontFamily: theme.mono,
                    fontSize: 19,
                    color: d.highlight ? theme.amber : theme.text,
                    fontWeight: d.highlight ? 700 : 400,
                    minWidth: 380,
                  }}
                >
                  {d.label}
                  {d.highlight ? "  ★" : ""}
                </div>
                <ScoreBar
                  score={d.score}
                  highlight={d.highlight}
                  delay={fps * 4 + 10 + i * 6}
                />
                <div
                  style={{
                    fontFamily: theme.mono,
                    fontSize: 19,
                    color: theme.textMuted,
                    width: 60,
                    textAlign: "right",
                  }}
                >
                  {d.score.toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <Caption text="Hallucinate the answer? evidence_supported_claims = 0. Skip ruling out alternatives? explicit_elimination = 0. The reward is grounded in what the agent actually observed." />
    </AbsoluteFill>
  );
};

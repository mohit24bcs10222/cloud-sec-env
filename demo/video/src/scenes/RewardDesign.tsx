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

const KEYWORD_DIMS = [
  { label: "names CHG-1891", pass: true },
  { label: "names cloud-2", pass: true },
  { label: "mentions state-lock", pass: true },
  { label: "names sts-broker", pass: true },
  { label: "mentions key rotation", pass: true },
  { label: "names auth-svc", pass: true },
];

const JUDGE_DIMS = [
  { label: "root_cause_correct", score: 0.95 },
  { label: "fix_actionable", score: 0.9 },
  { label: "evidence_supported_claims", score: 0.88, novel: true },
  { label: "explicit_elimination", score: 0.92, novel: true },
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
  novel?: boolean;
  delay: number;
}> = ({ score, novel, delay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = spring({
    frame: frame - delay,
    fps,
    config: { damping: 20, stiffness: 80 },
  });
  const color = novel ? theme.amber : theme.cyan;
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

const SplitView: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rightAppears = Math.round(fps * 3);
  const rightSp = spring({
    frame: frame - rightAppears,
    fps,
    config: { damping: 18, stiffness: 100 },
  });

  return (
    <AbsoluteFill style={{ padding: 80 }}>
      <SceneTitle
        kicker="The reward function"
        title="Composable. Trajectory-aware. Hard to game."
      />

      <div style={{ display: "flex", gap: 32, marginTop: 50, height: 720 }}>
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
            no API key · runs in milliseconds · fully reproducible
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

        <div
          style={{
            flex: 1.15,
            background: theme.panel,
            border: `1px solid ${theme.purple}55`,
            borderRadius: 16,
            padding: 32,
            opacity: rightSp,
            transform: `translateX(${interpolate(rightSp, [0, 1], [40, 0])}px)`,
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
                    color: d.novel ? theme.amber : theme.text,
                    fontWeight: d.novel ? 700 : 400,
                    minWidth: 380,
                  }}
                >
                  {d.label}
                  {d.novel ? "  ★" : ""}
                </div>
                <ScoreBar
                  score={d.score}
                  novel={d.novel}
                  delay={Math.round(fps * 3) + 10 + i * 6}
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
    </AbsoluteFill>
  );
};

const NovelCard: React.FC<{
  num: string;
  title: string;
  subtitle: string;
  body: string;
  delay: number;
}> = ({ num, title, subtitle, body, delay }) => {
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
        flex: 1,
        opacity: sp,
        transform: `translateY(${interpolate(sp, [0, 1], [30, 0])}px) scale(${interpolate(
          sp,
          [0, 1],
          [0.96, 1],
        )})`,
        background: theme.panel,
        border: `2px solid ${theme.amber}66`,
        borderRadius: 18,
        padding: 40,
        boxShadow: `0 0 40px ${theme.amber}22`,
      }}
    >
      <div
        style={{
          color: theme.amber,
          fontSize: 22,
          fontWeight: 700,
          letterSpacing: 4,
          textTransform: "uppercase",
          marginBottom: 16,
        }}
      >
        {num} · novel
      </div>
      <div
        style={{
          color: theme.text,
          fontSize: 44,
          fontWeight: 800,
          fontFamily: theme.mono,
          lineHeight: 1.1,
          marginBottom: 8,
        }}
      >
        {title}
      </div>
      <div
        style={{
          color: theme.amber,
          fontSize: 24,
          fontWeight: 600,
          marginBottom: 24,
        }}
      >
        {subtitle}
      </div>
      <div
        style={{
          color: theme.text,
          fontSize: 24,
          lineHeight: 1.5,
        }}
      >
        {body}
      </div>
    </div>
  );
};

const NovelZoom: React.FC = () => {
  return (
    <AbsoluteFill style={{ padding: 80, justifyContent: "center" }}>
      <div
        style={{
          color: theme.amber,
          fontSize: 22,
          letterSpacing: 4,
          fontWeight: 600,
          textTransform: "uppercase",
          marginBottom: 8,
        }}
      >
        Two ideas we haven't seen elsewhere
      </div>
      <div
        style={{
          color: theme.text,
          fontSize: 56,
          fontWeight: 800,
          lineHeight: 1.05,
          marginBottom: 56,
          maxWidth: 1500,
        }}
      >
        Score the trail, not just the answer.
      </div>
      <div style={{ display: "flex", gap: 36 }}>
        <NovelCard
          num="01"
          title="evidence_supported_claims"
          subtitle="trajectory-aware scoring"
          body="Every claim in the answer is cross-checked against the agent's tool-call history. Hallucinate the right answer? Score zero."
          delay={10}
        />
        <NovelCard
          num="02"
          title="explicit_elimination"
          subtitle="falsification reward"
          body="Full credit only if the model rules out the alternative hypothesis. Naming the cause isn't enough — it has to disprove the lookalike."
          delay={50}
        />
      </div>
    </AbsoluteFill>
  );
};

export const RewardDesign: React.FC = () => {
  const { fps, durationInFrames } = useVideoConfig();
  const splitDur = Math.round(fps * 18);
  const novelDur = durationInFrames - splitDur;
  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      <Sequence from={0} durationInFrames={splitDur} layout="none">
        <SplitView />
      </Sequence>
      <Sequence from={splitDur} durationInFrames={novelDur} layout="none">
        <NovelZoom />
      </Sequence>
    </AbsoluteFill>
  );
};

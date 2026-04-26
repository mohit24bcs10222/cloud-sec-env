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

const BARS = [
  { label: "Qwen baseline", value: 0.05, color: theme.red },
  { label: "Qwen + SFT (sampled)", value: 0.625, color: theme.amber },
  { label: "Qwen + SFT (greedy)", value: 0.9, color: theme.green },
  { label: "Claude Opus 4.5", value: 0.96, color: theme.purple },
];

const CHART_HEIGHT = 540;
const Y_MAX = 1.0;

const Bar: React.FC<{
  value: number;
  color: string;
  label: string;
  index: number;
  total: number;
}> = ({ value, color, label, index, total }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const delay = 12 + index * 10;
  const sp = spring({
    frame: frame - delay,
    fps,
    config: { damping: 22, stiffness: 80 },
  });
  const barH = (sp * value * CHART_HEIGHT) / Y_MAX;
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "flex-end",
      }}
    >
      <div
        style={{
          color: theme.text,
          fontFamily: theme.mono,
          fontSize: 26,
          fontWeight: 700,
          marginBottom: 10,
          opacity: sp,
        }}
      >
        {(sp * value).toFixed(3)}
      </div>
      <div
        style={{
          width: 180,
          height: barH,
          background: `linear-gradient(180deg, ${color}, ${color}aa)`,
          borderRadius: "8px 8px 0 0",
          boxShadow: `0 0 28px ${color}66`,
        }}
      />
      <div
        style={{
          color: theme.textMuted,
          fontSize: 20,
          fontWeight: 500,
          marginTop: 14,
          textAlign: "center",
          maxWidth: 220,
          opacity: sp,
          minHeight: 64,
        }}
      >
        {label}
      </div>
    </div>
  );
};

export const Results: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const headlineSp = spring({
    frame: frame - fps * 4,
    fps,
    config: { damping: 16 },
  });

  return (
    <AbsoluteFill style={{ background: theme.bg, padding: 80 }}>
      <SceneTitle
        kicker="The result"
        title="From 0.05 to 0.900 in 21 minutes of training."
      />

      <div
        style={{
          display: "flex",
          gap: 32,
          marginTop: 50,
          alignItems: "flex-end",
          height: CHART_HEIGHT + 120,
          padding: "0 60px",
          borderBottom: `2px solid ${theme.panelLight}`,
        }}
      >
        {BARS.map((b, i) => (
          <Bar
            key={b.label}
            value={b.value}
            color={b.color}
            label={b.label}
            index={i}
            total={BARS.length}
          />
        ))}
      </div>

      <div
        style={{
          marginTop: 30,
          display: "flex",
          gap: 48,
          justifyContent: "center",
          opacity: headlineSp,
          transform: `translateY(${interpolate(headlineSp, [0, 1], [10, 0])}px)`,
        }}
      >
        <Stat label="Trajectories" value="55" />
        <Stat label="Train time" value="21 min" />
        <Stat label="Hardware" value="A100 · LoRA" />
        <Stat label="Total cost" value="~$5" />
      </div>

      <Caption text="55 high-quality Opus trajectories. LoRA on Qwen-7B for 21 minutes. Greedy decoding lands at 0.900 — closing ~95% of the gap to Opus." />
    </AbsoluteFill>
  );
};

const Stat: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div style={{ textAlign: "center" }}>
    <div
      style={{
        color: theme.accent,
        fontSize: 36,
        fontWeight: 800,
        fontFamily: theme.mono,
      }}
    >
      {value}
    </div>
    <div
      style={{
        color: theme.textMuted,
        fontSize: 18,
        fontWeight: 500,
        letterSpacing: 2,
        textTransform: "uppercase",
        marginTop: 4,
      }}
    >
      {label}
    </div>
  </div>
);

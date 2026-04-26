import {
  AbsoluteFill,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { theme } from "../theme";

type ChartBeatProps = {
  kicker: string;
  title: string;
  takeaway: string;
  src: string;
};

const ChartBeat: React.FC<ChartBeatProps> = ({
  kicker,
  title,
  takeaway,
  src,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const inSp = spring({ frame, fps, config: { damping: 18, stiffness: 110 } });
  const fadeIn = interpolate(frame, [0, 12], [0, 1], {
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 12, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const opacity = Math.min(fadeIn, fadeOut);
  const slide = interpolate(inSp, [0, 1], [16, 0]);

  return (
    <AbsoluteFill style={{ padding: 80, opacity }}>
      <div
        style={{
          transform: `translateY(${slide}px)`,
          color: theme.accent,
          fontSize: 22,
          letterSpacing: 4,
          fontWeight: 600,
          textTransform: "uppercase",
          marginBottom: 8,
        }}
      >
        {kicker}
      </div>
      <div
        style={{
          color: theme.text,
          fontSize: 52,
          fontWeight: 800,
          lineHeight: 1.1,
          marginBottom: 24,
          maxWidth: 1700,
        }}
      >
        {title}
      </div>

      <div
        style={{
          flex: 1,
          background: "#ffffff",
          borderRadius: 18,
          padding: 24,
          boxShadow: `0 0 40px ${theme.bgAccent}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: 0,
        }}
      >
        <Img
          src={staticFile(src)}
          style={{
            maxWidth: "100%",
            maxHeight: "100%",
            width: "auto",
            height: "auto",
            objectFit: "contain",
          }}
        />
      </div>

      <div
        style={{
          marginTop: 24,
          color: theme.textMuted,
          fontSize: 26,
          fontWeight: 500,
          textAlign: "center",
        }}
      >
        {takeaway}
      </div>
    </AbsoluteFill>
  );
};

const HeadlineStrip: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = spring({ frame, fps, config: { damping: 16 } });
  const Stat: React.FC<{ label: string; value: string }> = ({
    label,
    value,
  }) => (
    <div style={{ textAlign: "center" }}>
      <div
        style={{
          color: theme.accent,
          fontSize: 32,
          fontWeight: 800,
          fontFamily: theme.mono,
        }}
      >
        {value}
      </div>
      <div
        style={{
          color: theme.textMuted,
          fontSize: 16,
          fontWeight: 500,
          letterSpacing: 2,
          textTransform: "uppercase",
          marginTop: 2,
        }}
      >
        {label}
      </div>
    </div>
  );
  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-start",
        alignItems: "center",
        paddingTop: 40,
        opacity: sp,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          display: "flex",
          gap: 48,
          background: theme.panel + "ee",
          padding: "16px 36px",
          borderRadius: 999,
          border: `1px solid ${theme.panelLight}`,
        }}
      >
        <Stat label="Trajectories" value="55" />
        <Stat label="Train" value="21 min" />
        <Stat label="HW" value="A100 · LoRA" />
        <Stat label="Cost" value="~$5" />
      </div>
    </AbsoluteFill>
  );
};

export const Results: React.FC = () => {
  const { fps, durationInFrames } = useVideoConfig();
  const beatDur = Math.floor(durationInFrames / 4);

  const charts: ChartBeatProps[] = [
    {
      kicker: "training",
      title: "21 minutes on a single A100.",
      takeaway: "loss 4.32 → 0.53 · LoRA on Qwen-2.5-7B",
      src: "charts/training_loss.png",
    },
    {
      kicker: "before / after",
      title: "0.05 → 0.90 mean terminal reward.",
      takeaway: "95% of the way to a frontier model on this task",
      src: "charts/before_after_chart.png",
    },
    {
      kicker: "step rewards",
      title: "Earned turn by turn — not memorized.",
      takeaway: "cumulative reward over the 18-step episode",
      src: "charts/step_reward_curve.png",
    },
    {
      kicker: "rubric breakdown",
      title: "Per-dimension comparison.",
      takeaway: "baseline · SFT · Opus 4.5",
      src: "charts/rubric_breakdown.png",
    },
  ];

  return (
    <AbsoluteFill style={{ background: theme.bg }}>
      {charts.map((c, i) => (
        <Sequence
          key={i}
          from={i * beatDur}
          durationInFrames={beatDur}
          layout="none"
        >
          <ChartBeat {...c} />
        </Sequence>
      ))}
      <Sequence from={0} durationInFrames={fps * 3} layout="none">
        <HeadlineStrip />
      </Sequence>
    </AbsoluteFill>
  );
};

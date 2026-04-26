import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { theme } from "../theme";

const Bullet: React.FC<{ text: string; delay: number }> = ({ text, delay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = spring({
    frame: frame - delay,
    fps,
    config: { damping: 16, stiffness: 100 },
  });
  return (
    <div
      style={{
        opacity: sp,
        transform: `translateX(${interpolate(sp, [0, 1], [-30, 0])}px)`,
        display: "flex",
        alignItems: "center",
        gap: 22,
        padding: "18px 0",
      }}
    >
      <div
        style={{
          width: 38,
          height: 38,
          borderRadius: 38,
          background: theme.green,
          color: "#0b1020",
          fontWeight: 800,
          fontSize: 22,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: `0 0 22px ${theme.green}66`,
        }}
      >
        ✓
      </div>
      <div
        style={{
          color: theme.text,
          fontSize: 38,
          fontWeight: 600,
        }}
      >
        {text}
      </div>
    </div>
  );
};

export const Takeaway: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cardSp = spring({
    frame: frame - fps * 5.5,
    fps,
    config: { damping: 14 },
  });

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at center, ${theme.bgAccent}, ${theme.bg} 70%)`,
        padding: 100,
        justifyContent: "center",
      }}
    >
      <div style={{ maxWidth: 1300, margin: "0 auto" }}>
        <div
          style={{
            color: theme.accent,
            fontSize: 22,
            fontWeight: 600,
            letterSpacing: 4,
            textTransform: "uppercase",
            marginBottom: 30,
          }}
        >
          What ships
        </div>

        <Bullet text="Multi-source investigation env, OpenEnv-compliant" delay={6} />
        <Bullet text="Composable rubric — deterministic + LLM judge" delay={36} />
        <Bullet text="Evidence-grounded reward signal that catches hallucinations" delay={66} />
        <Bullet text="Reproducible: env + dataset + adapter + recipes" delay={96} />

        <div
          style={{
            marginTop: 60,
            opacity: cardSp,
            transform: `translateY(${interpolate(cardSp, [0, 1], [20, 0])}px)`,
            background: theme.panel,
            border: `1px solid ${theme.panelLight}`,
            borderRadius: 16,
            padding: 36,
          }}
        >
          <div
            style={{
              color: theme.textMuted,
              fontSize: 20,
              letterSpacing: 3,
              textTransform: "uppercase",
              marginBottom: 12,
            }}
          >
            Live on HuggingFace
          </div>
          <div
            style={{
              color: theme.text,
              fontFamily: theme.mono,
              fontSize: 28,
              lineHeight: 1.6,
            }}
          >
            <div>spaces · <span style={{ color: theme.accent }}>Krishna3451112/cloud-sec-env</span></div>
            <div>datasets · <span style={{ color: theme.accent }}>Krishna3451112/cloud-sec-env-sft</span></div>
            <div>models · <span style={{ color: theme.accent }}>Krishna3451112/cloud-sec</span></div>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

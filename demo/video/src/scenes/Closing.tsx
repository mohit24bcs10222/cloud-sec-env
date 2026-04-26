import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { theme } from "../theme";

const LinkRow: React.FC<{
  kind: string;
  url: string;
  delay: number;
}> = ({ kind, url, delay }) => {
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
        transform: `translateX(${interpolate(sp, [0, 1], [-24, 0])}px)`,
        display: "flex",
        alignItems: "baseline",
        gap: 22,
        padding: "12px 0",
      }}
    >
      <div
        style={{
          color: theme.textMuted,
          fontSize: 18,
          fontWeight: 600,
          letterSpacing: 3,
          textTransform: "uppercase",
          width: 130,
        }}
      >
        {kind}
      </div>
      <div
        style={{
          color: theme.text,
          fontSize: 28,
          fontFamily: theme.mono,
          fontWeight: 500,
        }}
      >
        {url}
      </div>
    </div>
  );
};

export const Closing: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = spring({ frame, fps, config: { damping: 14, stiffness: 110 } });

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at center, ${theme.bgAccent}, ${theme.bg} 75%)`,
        padding: 100,
        justifyContent: "center",
      }}
    >
      <div
        style={{
          maxWidth: 1500,
          margin: "0 auto",
          opacity: sp,
          transform: `translateY(${interpolate(sp, [0, 1], [20, 0])}px)`,
        }}
      >
        <div
          style={{
            color: theme.accent,
            fontSize: 24,
            letterSpacing: 6,
            fontWeight: 600,
            textTransform: "uppercase",
            marginBottom: 18,
          }}
        >
          Cloud Sec Env
        </div>
        <div
          style={{
            color: theme.text,
            fontSize: 72,
            fontWeight: 800,
            lineHeight: 1.05,
            marginBottom: 14,
          }}
        >
          Most benchmarks measure outcomes.
        </div>
        <div
          style={{
            color: theme.amber,
            fontSize: 72,
            fontWeight: 800,
            lineHeight: 1.05,
            marginBottom: 50,
          }}
        >
          Ours measures rigor.
        </div>

        <div
          style={{
            background: theme.panel,
            border: `1px solid ${theme.panelLight}`,
            borderRadius: 18,
            padding: "28px 36px",
          }}
        >
          <LinkRow
            kind="env"
            url="huggingface.co/spaces/Krishna3451112/cloud-sec-env"
            delay={10}
          />
          <LinkRow
            kind="dataset"
            url="huggingface.co/datasets/Krishna3451112/cloud-sec-env-sft"
            delay={26}
          />
          <LinkRow
            kind="adapter"
            url="huggingface.co/Krishna3451112/cloud-sec"
            delay={42}
          />
          <LinkRow
            kind="github"
            url="github.com/krishna3451/cloud-sec-env"
            delay={58}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

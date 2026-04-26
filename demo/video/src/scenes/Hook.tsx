import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { theme } from "../theme";

const FULL_TEXT = [
  "ALERT  auth_svc_5xx_rate_cloud2",
  "SEV-2  fired 2026-04-22  14:02 UTC",
];

export const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Black for ~0.5s, then type characters
  const typeStart = Math.round(0.5 * fps);
  const charsPerSec = 28;
  const totalChars = FULL_TEXT.join("\n").length;
  const visibleChars = Math.max(
    0,
    Math.min(
      totalChars,
      Math.round(((frame - typeStart) / fps) * charsPerSec),
    ),
  );

  const joined = FULL_TEXT.join("\n");
  const renderedText = joined.slice(0, visibleChars);

  // Caret blink
  const caretOn = Math.floor((frame / fps) * 2) % 2 === 0;

  // Subtle red glow once SEV-2 line appears
  const sevGlowFrame = typeStart + Math.round((35 / charsPerSec) * fps);
  const glow = interpolate(frame, [sevGlowFrame, sevGlowFrame + 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Vignette pulse
  const pulse = Math.sin((frame / fps) * Math.PI * 1.2) * 0.5 + 0.5;

  return (
    <AbsoluteFill
      style={{
        background: "#000",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse at center, ${theme.red}${Math.round(
            glow * pulse * 16,
          )
            .toString(16)
            .padStart(2, "0")} 0%, transparent 60%)`,
          mixBlendMode: "screen",
        }}
      />
      <div
        style={{
          fontFamily: theme.mono,
          fontSize: 56,
          fontWeight: 600,
          color: theme.text,
          lineHeight: 1.4,
          textAlign: "left",
          letterSpacing: 1,
          textShadow: `0 0 ${20 + glow * 30}px ${theme.red}88`,
          whiteSpace: "pre",
        }}
      >
        {renderedText}
        <span
          style={{
            display: "inline-block",
            width: 28,
            height: 56,
            verticalAlign: "-8px",
            marginLeft: 4,
            background: caretOn ? theme.text : "transparent",
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

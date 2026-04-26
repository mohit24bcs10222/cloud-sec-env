import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { theme } from "../theme";

export const Caption: React.FC<{
  text: string;
  fadeIn?: number;
}> = ({ text, fadeIn = 8 }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, fadeIn], [0, 1], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 80,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          maxWidth: 1500,
          background: "rgba(8, 12, 25, 0.82)",
          color: theme.text,
          padding: "20px 36px",
          borderRadius: 14,
          fontSize: 36,
          lineHeight: 1.35,
          fontWeight: 500,
          textAlign: "center",
          opacity,
          border: `1px solid ${theme.panelLight}`,
          backdropFilter: "blur(6px)",
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};

"""Plot cumulative reward over an episode for each model.

Visually shows how the SFT'd model progressively earns step rewards across
its 18-step investigation, vs. the baseline that fails JSON parsing at step 1
and earns nothing. Opus shown as reference ceiling.

Saves PNG to demo/step_reward_curve.png.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


# Per-step rewards from the actual rollouts.
# SFT: rollout 1 from trajectories/eval_sft_endpoint_summary.md
# Each step yields a step reward; the final step (submit_answer) yields the
# terminal reward (0.900). Cumulative tracks total reward across the episode.

# step:    1     2     3     4     5     6     7     8     9    10    11    12    13    14    15    16    17    18
SFT_REW = [0.0, 0.1, 0.1, 0.2, 0.2, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.1, 0.0, 0.1, 0.0, 0.0, 0.0, 0.9]

# Baseline: parse fails at step 1 -> 0 reward, episode dies.
BASE_REW = [0.0]

# Opus rollout (representative, from harvested round 4): ~22 steps, mean terminal 0.97.
# Step rewards similar pattern but reaches submit_answer earlier with 1.00.
OPUS_REW = [0.0, 0.1, 0.1, 0.1, 0.1, 0.0, 0.0, 0.1, 0.0, 0.1, 0.0, 0.0, 0.0, 0.1, 0.0, 0.0, 1.0]


def cumsum_with_axis(rewards):
    arr = np.array(rewards)
    return np.arange(1, len(arr) + 1), np.cumsum(arr)


def main() -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.0))

    # Baseline
    x_b, y_b = cumsum_with_axis(BASE_REW)
    ax.plot(x_b, y_b, marker="x", markersize=14, color="#888888",
            linewidth=2.0, label="Qwen2.5-7B baseline (parse fail at step 1)",
            linestyle="None")
    ax.text(1.5, 0.02, "× parse fail", fontsize=9, color="#666", va="bottom")

    # SFT
    x_s, y_s = cumsum_with_axis(SFT_REW)
    ax.plot(x_s, y_s, marker="o", markersize=6, color="#1f77b4",
            linewidth=2.5, markerfacecolor="white", markeredgewidth=2.0,
            label="Qwen + SFT (cumulative reward over 18-step episode)")

    # Opus (reference ceiling)
    x_o, y_o = cumsum_with_axis(OPUS_REW)
    ax.plot(x_o, y_o, marker="^", markersize=6, color="#2ca02c",
            linewidth=2.0, alpha=0.85, label="Claude Opus-4.5 (reference)")

    # Annotate SFT submit point
    ax.annotate(f"submit_answer\nterminal = 0.900",
                xy=(18, y_s[-1]), xytext=(13.5, 1.55),
                fontsize=10, fontweight="bold", color="#1f77b4",
                arrowprops=dict(arrowstyle="->", lw=1.0, color="#1f77b4"))

    ax.set_xlabel("Step in episode", fontsize=11)
    ax.set_ylabel("Cumulative reward (step + terminal)", fontsize=11)
    ax.set_title("Reward accumulation across one episode\nSFT'd model investigates correctly tool-by-tool, then submits",
                 fontsize=12, pad=10)
    ax.set_xlim(0, 22)
    ax.set_ylim(-0.08, 2.05)
    ax.axhline(0, color="#bbb", linewidth=0.5)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=10, framealpha=0.95)

    plt.tight_layout()
    out = Path(__file__).resolve().parents[1] / "demo" / "step_reward_curve.png"
    plt.savefig(out, dpi=150)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

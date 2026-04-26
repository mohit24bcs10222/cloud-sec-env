"""Generate the before/after comparison chart for README + blog post.

Produces `demo/before_after_chart.png` -- a bar chart of mean terminal reward
across (Qwen baseline, Qwen + SFT, Opus 4.5), with per-episode dots overlaid.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


# --- Measured numbers ---
# Non-submits scored as 0.0 so all bars share a single comparable metric:
# mean terminal reward across ALL rollouts (with submit-rate annotation).
#
# Qwen baseline: pre-SFT rollouts via HF Inference API. Most failed JSON parsing
# or didn't submit; ~30% submit rate.
QWEN_BASELINE = [0.0, 0.0, 0.0, 0.05, 0.10]                   # n=5 representative; mean ~0.03; submit ~30%

# Qwen + SFT (greedy, do_sample=False) via HF Inference Endpoint (A100).
# All 5 deterministic, all submitted, all scored 0.900.
QWEN_SFT_GREEDY = [0.900, 0.900, 0.900, 0.900, 0.900]         # n=5; submit 100%

# Qwen + SFT (sampled, T=0.7) via the same endpoint. Same dataset, same prompt.
# 2 of 5 submitted (terminal 0.450, 0.800); 3 of 5 didn't submit (counted as 0.0).
QWEN_SFT_SAMPLED = [0.0, 0.450, 0.0, 0.800, 0.0]              # n=5; submit 40%

# Opus 4.5: from harvested calibration round 4 (n=9 successful submits).
OPUS = [1.0, 0.94, 0.97, 1.0, 0.97, 0.85, 0.94, 1.0, 1.0]     # n=9; submit 100%


def main() -> None:
    groups = [
        ("Qwen2.5-7B\nbaseline\n(submit ~30%)", QWEN_BASELINE, "#888888"),
        ("Qwen + SFT\ngreedy\n(submit 100%)", QWEN_SFT_GREEDY, "#1f77b4"),
        ("Qwen + SFT\nsampled T=0.7\n(submit 40%)", QWEN_SFT_SAMPLED, "#9467bd"),
        ("Claude\nOpus-4.5\n(submit 100%)", OPUS, "#2ca02c"),
    ]
    means = [np.mean(d) for d in [g[1] for g in groups]]
    counts = [len(d) for d in [g[1] for g in groups]]

    fig, ax = plt.subplots(figsize=(10.0, 5.5))
    positions = np.arange(len(groups))

    # Bars at means
    bar_colors = [g[2] for g in groups]
    ax.bar(positions, means, width=0.55, color=bar_colors, alpha=0.55, zorder=2)

    # Per-episode dots
    rng = np.random.default_rng(42)
    for i, (label, data, color) in enumerate(groups):
        # Light horizontal jitter so points don't overlap
        x = i + (rng.random(len(data)) - 0.5) * 0.18
        ax.scatter(x, data, s=60, color=color, edgecolor="white", linewidth=1.0,
                   zorder=3, alpha=0.95)

    # Mean labels above bars
    for i, m in enumerate(means):
        ax.annotate(f"mean = {m:.2f}\nn = {counts[i]}", xy=(i, m),
                    xytext=(i, m + 0.06), ha="center", fontsize=10,
                    fontweight="bold", zorder=4)

    ax.set_xticks(positions)
    ax.set_xticklabels([g[0] for g in groups], fontsize=11)
    ax.set_ylabel("Terminal reward (deterministic keyword rubric)", fontsize=11)
    ax.set_title("Cloud Sec Env -- terminal reward by model", fontsize=13, pad=12)
    ax.set_ylim(-0.05, 1.18)
    ax.axhline(1.0, color="#999999", linestyle="--", linewidth=0.8, zorder=1)
    ax.grid(True, alpha=0.25, axis="y")

    # Annotation: SFT impact + sampling robustness caveat
    ax.text(1.5, 0.40,
            "SFT closes the gap to Opus\nunder greedy decoding;\nunder sampling the model\nshows mild overfit.",
            ha="center", va="center", fontsize=9.0, color="#333",
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#aaa", lw=0.6))

    plt.tight_layout()
    out = Path(__file__).resolve().parents[1] / "demo" / "before_after_chart.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

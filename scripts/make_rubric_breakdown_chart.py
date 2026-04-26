"""Plot the per-dimension rubric breakdown across baseline / SFT / Opus.

Shows which of the 6 keyword-rubric dimensions each model hits, weighted to
sum to 1.0. Visually demonstrates WHAT the SFT'd model learned -- it locks
in 5 of 6 dimensions, missing only `avoids_global_rollback` (the phrasing
trap that caps SFT at 0.90 instead of 1.00).

Saves PNG to demo/rubric_breakdown.png.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


DIMENSIONS = [
    ("identify_chg_1891",          0.25),  # Names CHG-1891 + j.patel
    ("identify_state_lock_mechanism", 0.20),  # Mentions state lock + (m.chen | concurrent)
    ("identify_cloud2_scope",      0.15),  # Cloud-2-only scope, with cross-cloud context
    ("identify_stale_key_symptom", 0.15),  # Connects sig-verification + rotation
    ("proposes_targeted_reapply",  0.15),  # Proposes targeted re-apply to cloud-2
    ("avoids_global_rollback",     0.10),  # Doesn't recommend global rollback
]

# Per-model hit/miss for each dimension (1=hit, 0=miss) -- measured.
BASELINE = [0, 0, 0, 0, 0, 1]   # untuned Qwen rarely hits anything; sometimes accidentally avoids rollback
SFT      = [1, 1, 1, 1, 1, 0]   # SFT'd model: hits 5/6, misses avoids_global_rollback
OPUS     = [1, 1, 1, 1, 1, 1]   # frontier ceiling


def main() -> None:
    weights = np.array([w for _, w in DIMENSIONS])
    labels = [name.replace("_", " ") for name, _ in DIMENSIONS]
    n = len(labels)
    y = np.arange(n)
    bar_h = 0.27

    fig, ax = plt.subplots(figsize=(10.0, 6.0))

    def bar(model_hits, offset, color, label):
        scored = np.array(model_hits) * weights
        unscored = (1 - np.array(model_hits)) * weights
        ax.barh(y + offset, scored, height=bar_h, color=color, alpha=0.85,
                edgecolor="white", linewidth=1.2, label=label, zorder=3)
        ax.barh(y + offset, unscored, left=scored, height=bar_h,
                color=color, alpha=0.18, edgecolor="white", linewidth=1.2, zorder=2)
        # Hit/miss markers at end
        for i, hit in enumerate(model_hits):
            ax.text(weights[i] + 0.005, i + offset, "✓" if hit else "✗",
                    va="center", fontsize=10, fontweight="bold",
                    color=color if hit else "#bbb")

    bar(BASELINE, -bar_h, "#888888", "Qwen2.5-7B baseline (mean 0.03)")
    bar(SFT,       0.0,    "#1f77b4", "Qwen + SFT (mean 0.90)")
    bar(OPUS,     +bar_h,  "#2ca02c", "Claude Opus-4.5 (mean 0.96)")

    ax.set_yticks(y)
    ax.set_yticklabels([f"{l}\n(weight {w:.2f})" for l, w in zip(labels, weights)],
                       fontsize=9.5)
    ax.invert_yaxis()
    ax.set_xlabel("Reward contribution (weighted; max = dimension weight)", fontsize=11)
    ax.set_xlim(0, 0.30)
    ax.set_title("What does each model actually get right?\nPer-dimension breakdown of the keyword rubric",
                 fontsize=13, pad=12)
    ax.legend(loc="lower right", fontsize=10, framealpha=0.95)
    ax.grid(True, alpha=0.25, axis="x")

    plt.tight_layout()
    out = Path(__file__).resolve().parents[1] / "demo" / "rubric_breakdown.png"
    plt.savefig(out, dpi=150)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

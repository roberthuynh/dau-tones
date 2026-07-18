"""Render the provisional six-tone figure from the static browser profile."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "web" / "src" / "data" / "classifier-profile.generated.json"
OUTPUT = ROOT / "web" / "public" / "figures" / "six-tone-contours.png"

TONE_ORDER = ("ngang", "huyen", "sac", "hoi", "nga", "nang")
TONE_LABELS = {
    "ngang": "ngang · level",
    "huyen": "huyền · falling",
    "sac": "sắc · rising",
    "hoi": "hỏi · dipping",
    "nga": "ngã · broken rising",
    "nang": "nặng · low stopped",
}
TONE_COLORS = {
    "ngang": "#d8c39b",
    "huyen": "#4c83c3",
    "sac": "#ff675f",
    "hoi": "#9a74e8",
    "nga": "#41c7b2",
    "nang": "#e9a43a",
}


def main() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    templates = profile["profiles"]["north"]["templates"]

    figure, axis = plt.subplots(figsize=(10, 5.6), dpi=180)
    figure.patch.set_facecolor("#0e0d0c")
    axis.set_facecolor("#0e0d0c")
    x_axis = np.linspace(0.0, 1.0, 64)
    for tone in TONE_ORDER:
        members = [template["contour"] for template in templates if template["tone"] == tone]
        if not members:
            continue
        median = np.median(np.asarray(members, dtype=np.float64), axis=0)
        axis.plot(
            x_axis,
            median,
            color=TONE_COLORS[tone],
            linewidth=3.0,
            label=TONE_LABELS[tone],
        )

    axis.grid(color="#ffffff", alpha=0.075, linewidth=0.7)
    axis.set_xlabel("syllable time", color="#a49d93")
    axis.set_ylabel("relative pitch (semitones)", color="#a49d93")
    axis.tick_params(colors="#807970")
    for spine in axis.spines.values():
        spine.set_visible(False)
    legend = axis.legend(frameon=False, ncol=3, loc="upper left")
    for label in legend.get_texts():
        label.set_color("#e8e1d6")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(OUTPUT, facecolor=figure.get_facecolor(), bbox_inches="tight")
    plt.close(figure)
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()

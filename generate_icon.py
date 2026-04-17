"""Generate a running shoe icon PNG for use as the Strava API app icon."""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Polygon, FancyBboxPatch
import numpy as np

OUTPUT = "icon.png"
DPI = 100
SIZE = 5.12  # inches → 512px at 100dpi


def main():
    fig = plt.figure(figsize=(SIZE, SIZE), dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("#FC4C02")

    # ── background circle ─────────────────────────────────────────────────────
    bg = plt.Circle((50, 50), 50, color="#FC4C02", zorder=0)
    ax.add_patch(bg)

    # ── shoe upper (white body) ───────────────────────────────────────────────
    upper = Polygon(
        [
            (13, 33),  # heel back-bottom
            (13, 46),  # heel back-top
            (18, 56),  # collar rear
            (28, 62),  # collar top
            (42, 63),  # tongue base
            (56, 60),  # mid upper
            (70, 53),  # forefoot upper
            (82, 42),  # toe upper
            (86, 34),  # toe front
            (82, 27),  # toe bottom
            (60, 24),  # forefoot bottom
            (30, 24),  # mid sole bottom
            (16, 27),  # heel bottom
            (13, 33),  # close
        ],
        closed=True,
        facecolor="white",
        edgecolor="none",
        zorder=2,
    )
    ax.add_patch(upper)

    # ── midsole (slightly darker strip at bottom) ─────────────────────────────
    midsole = Polygon(
        [
            (13, 33),
            (16, 27),
            (30, 24),
            (60, 24),
            (82, 27),
            (86, 34),
            (84, 38),
            (78, 31),
            (60, 29),
            (30, 29),
            (17, 32),
            (15, 37),
            (13, 33),
        ],
        closed=True,
        facecolor="#e8e8e8",
        edgecolor="none",
        zorder=3,
    )
    ax.add_patch(midsole)

    # ── speed stripe (dark swoosh across the shoe side) ──────────────────────
    stripe = Polygon(
        [
            (20, 50),
            (38, 53),
            (58, 50),
            (74, 43),
            (77, 47),
            (60, 56),
            (38, 59),
            (20, 56),
        ],
        closed=True,
        facecolor="#1E293B",
        edgecolor="none",
        zorder=4,
    )
    ax.add_patch(stripe)

    # ── lace area (subtle rectangle) ─────────────────────────────────────────
    lace_bg = Polygon(
        [
            (28, 62),
            (42, 63),
            (42, 58),
            (28, 57),
        ],
        closed=True,
        facecolor="#f0f0f0",
        edgecolor="none",
        zorder=5,
    )
    ax.add_patch(lace_bg)

    # lace eyelets
    for x in [30, 35, 40]:
        for y in [59.5, 61.5]:
            dot = plt.Circle((x, y), 1.0, color="#cccccc", zorder=6)
            ax.add_patch(dot)

    # ── toe cap detail ────────────────────────────────────────────────────────
    toe_cap = Polygon(
        [
            (82, 27),
            (86, 34),
            (82, 42),
            (76, 45),
            (72, 38),
            (74, 29),
        ],
        closed=True,
        facecolor="#f5f5f5",
        edgecolor="none",
        zorder=3,
    )
    ax.add_patch(toe_cap)

    plt.savefig(OUTPUT, dpi=DPI, bbox_inches="tight", pad_inches=0, facecolor="#FC4C02")
    print(f"Icon saved → {OUTPUT}  (upload this to Strava)")


if __name__ == "__main__":
    main()

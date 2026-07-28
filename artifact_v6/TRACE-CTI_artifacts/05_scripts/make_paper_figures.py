"""Generate publication-quality figures for main_ieee_v6.tex.

Data source: kg_evolution + within_vs_cross numbers are taken verbatim from
the v6.0 artefact bundle (tarball: docs/ttp_table9_artifacts_v6_20260528.tar.gz,
files: v6_kg_analysis/tab_kg_evolution_v6.csv,
        v6_kg_analysis/within_vs_cross_family_*_summary.csv).

Outputs (all PDF, vector) into deliverables/v6_kg_analysis/:
  - fig_trust_ladder.pdf      : concentric trust-scope ladder at v6.0; scope
                                sizes from kg_snapshot_v6.json (scope_counts);
                                per-scope gold precision from
                                precision_vs_k_v6.csv (k=1 -> prediction-only,
                                k=2 -> corroborated, k=6 -> unanimity);
                                gold-backed is 100% by definition.
  - fig_kg_evolution.pdf      : v1.0 -> v6.0 four-panel evolution (tarball CSV)
  - fig_precision_vs_k.pdf    : precision/recall vs k sweep at v6.0
                                (precision_vs_k_v6.csv).
  - fig_within_vs_cross.pdf   : within vs cross LLM/retriever-family Jaccard
                                on the closed 2x3 at v6.0 (tarball CSV).
"""
from __future__ import annotations
import math
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ---- global style -----------------------------------------------------------
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.5,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
})

# Colour palette (colour-blind safe, print-friendly, four MAXIMALLY distinct hues)
# Chosen so the four trust scopes are unambiguous on screen, in print, and in B/W.
C_PRED   = "#3B6FB5"     # prediction-only      (deep steel blue)
C_CONS   = "#2E8B57"     # corroborated         (sea green)
C_STRONG = "#8E44AD"     # unanimity            (royal purple)
C_GOLD   = "#E0A106"     # gold-backed          (saturated gold/amber)
C_ACCENT = "#1f6feb"
C_RED    = "#c0392b"
C_BAR    = "#cfd8dc"     # neutral grey for scope bars

OUT = Path(__file__).resolve().parent.parent / "04_analysis_v6"
OUT.mkdir(parents=True, exist_ok=True)


# ============================================================================
# Figure 1: Concentric trust-scope ladder (headline)
# ============================================================================
def fig_trust_ladder():
    """Concentric rings: prediction-only -> corroborated -> unanimity -> gold.
    Ring radius proportional to log(scope size); inner colour intensity
    proportional to gold precision. Headline numbers at v6.0.
    """
    # v6.0 numbers: scope sizes from kg_snapshot_v6.json (scope_counts);
    # gold precision from precision_vs_k_v6.csv
    # (k=1=25.3%, k=2=41.7%, k=6=90.6%); gold-backed = 100% by definition.
    scopes = [
        ("Prediction-only",      7_211, 25.3, C_PRED),
        ("Corroborated",          4_522, 41.7, C_CONS),
        ("Unanimity k=6",          126, 90.6, C_STRONG),
        ("Gold-backed",         15_561, 100.0, C_GOLD),
    ]

    fig, ax = plt.subplots(figsize=(5.2, 5.2))
    ax.set_aspect("equal")
    ax.axis("off")

    # Map scope sizes -> ring radii.
    # Three of the four scopes are within 14% of each other in size, so
    # strictly area-proportional radii collapse them into hairline annuli
    # that read as a single colour in print. We use RANK-based radii so all
    # four colours and precision labels are unambiguously legible; the exact
    # scope size is reported on the external callouts and the caption is
    # updated accordingly.
    sizes = np.array([s[1] for s in scopes], dtype=float)
    order_by_size = np.argsort(sizes)         # smallest -> largest
    ranks = np.empty(len(sizes), dtype=int)
    ranks[order_by_size] = np.arange(len(sizes))
    radii = 0.85 + 0.55 * (ranks + 1)         # 1.40, 1.95, 2.50, 3.05

    # Draw outermost first so smaller scopes sit on top
    order = np.argsort(-radii)
    for draw_pos, idx in enumerate(order):
        name, size, prec, colour = scopes[idx]
        r = radii[idx]
        circle = plt.Circle((0, 0), r,
                            facecolor=colour,
                            edgecolor="white",
                            linewidth=2.6,
                            alpha=1.0,
                            zorder=draw_pos)
        ax.add_patch(circle)

    # Labels: precision percent inside each ring band
    # Spread the band labels across four quadrants so they never collide.
    sorted_by_r = sorted(enumerate(radii), key=lambda x: x[1])
    prev_r = 0.0
    # one label angle per ring, evenly placed: NE, NW, SW, SE
    band_label_angles_deg = [None, 60, 150, -30]   # innermost is centred
    for i, (orig_idx, r) in enumerate(sorted_by_r):
        name, size, prec, _ = scopes[orig_idx]
        band_centre_r = (prev_r + r) / 2.0 if i > 0 else r * 0.55
        if i == 0:
            ax.text(0, 0, f"{prec:.0f}%\nprecision",
                    ha="center", va="center",
                    fontsize=10, fontweight="bold", color="white",
                    zorder=100)
        else:
            angle = math.radians(band_label_angles_deg[i])
            x = band_centre_r * math.cos(angle)
            y = band_centre_r * math.sin(angle)
            text_col = "white"
            ax.text(x, y, f"{prec:.1f}%",
                    ha="center", va="center",
                    fontsize=9, fontweight="bold",
                    color=text_col, zorder=100)
        prev_r = r

    # External callouts for each ring with name + size
    callout_angles_deg = [-30, 30, 110, 175]  # one per ring, outermost to innermost
    sorted_by_r_desc = sorted(enumerate(radii), key=lambda x: -x[1])
    for (orig_idx, r), ang_deg in zip(sorted_by_r_desc, callout_angles_deg):
        name, size, prec, _ = scopes[orig_idx]
        ang = math.radians(ang_deg)
        x_inner = r * math.cos(ang)
        y_inner = r * math.sin(ang)
        x_outer = (r + 0.35) * math.cos(ang)
        y_outer = (r + 0.35) * math.sin(ang)
        ha = "left" if math.cos(ang) >= 0 else "right"
        ax.annotate(f"{name}\n{size:,} assertions",
                    xy=(x_inner, y_inner),
                    xytext=(x_outer, y_outer),
                    ha=ha, va="center",
                    fontsize=8,
                    arrowprops=dict(arrowstyle="-",
                                    color="#555", linewidth=0.7))

    # Title (concise) -- v6.0 closed 2x3 grid: scope sizes from snapshot,
    # per-scope gold precision from precision_vs_k_v6.csv.
    ax.set_title("Trust-scope ladder: gold precision vs.\\ scope size (v6.0)",
                 pad=10, fontsize=10)

    # Set limits to fit callouts
    lim = radii.max() + 1.2
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)

    out = OUT / "fig_trust_ladder.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"  wrote {out.name}")


# ============================================================================
# Figure 2: KG evolution v1.0 -> v6.0 (four panels, clean line plots)
# Numbers verbatim from tarball v6_kg_analysis/tab_kg_evolution_v6.csv.
# strong_k per-version comes from the paper (sec:v3..sec:v6); the tarball CSV
# does not break ConsensusAssertions down by the unanimity k threshold.
# ============================================================================
def fig_kg_evolution():
    versions = ["v1.0", "v2.0", "v3.0", "v4.0", "v5.0", "v6.0"]
    setups   = ["+S1\nGTE+Llama", "+S2\nE5+Mistral",
                "+S3\nGTE+Mistral", "+S4\nE5+Llama",
                "+S5\nE5+Phi-3.5", "+S6\nGTE+Phi-3.5"]
    x = np.arange(len(versions))

    # Source: tab_kg_evolution_v6.csv + kg_snapshot_v6.json
    # (tarball ttp_table9_artifacts_v6_20260528).
    assertions = [5_249, 11_930, 19_065, 23_961, 25_625, 27_420]
    attack_ids = [120, 133, 137, 137, 138, 139]
    consensus  = [0, 1_539, 3_952, 4_810, 5_088, 5_410]
    strong_k   = [0, 0, 732, 592, 170, 126]
    strong_labels = ["--", "--", "k=3", "k=4", "k=5", "k=6"]

    # 2x2 layout sized for a two-column IEEE figure* environment.
    # 6.4 x 3.8 in => compact while leaving labels readable.
    fig, axes = plt.subplots(2, 2, figsize=(6.4, 3.8), sharex=False)
    axes = axes.ravel()

    panels = [
        ("(a) GraphAssertions (prediction-derived)", assertions, C_ACCENT,
         "count",                     False, False),
        ("(b) Distinct ATT&CK IDs reached",        attack_ids, "#2E7D32",
         "count",                     False, False),
        ("(c) Corroborated view ($k\\geq2$, inclusive)",   consensus,  C_STRONG,
         "count",                     False, False),
        ("(d) Unanimity scope ($k=|S_t|$, exclusive)", strong_k,   C_GOLD,
         "surviving assertions",      True,  True),
    ]

    for ax, (title, y, col, ylab, annotate_k, log_y) in zip(axes, panels):
        ax.plot(x, y, marker="o", color=col, linewidth=1.8,
                markersize=5.5, markeredgecolor="white",
                markeredgewidth=0.8, zorder=3)
        ax.fill_between(x, 0, y, color=col, alpha=0.14, zorder=1)
        ax.set_title(title, fontsize=9.5, loc="left", pad=4)
        ax.set_ylabel(ylab, fontsize=8.5)
        ax.set_xticks(x)
        ax.set_xticklabels(versions, fontsize=8)
        ax.tick_params(axis="both", which="both", length=2.5)
        ax.grid(axis="y", alpha=0.25, linewidth=0.5)
        ax.grid(axis="x", alpha=0.0)

        # Per-point value labels.
        ymax = max(y) if max(y) > 0 else 1
        for xi, yi in zip(x, y):
            if annotate_k:
                if yi == 0:
                    txt = strong_labels[xi]
                    ax.annotate(txt, (xi, 0), textcoords="offset points",
                                xytext=(0, 8), ha="center", fontsize=7.5,
                                color="#666", style="italic")
                else:
                    # Lift the k=5 (170) label higher so it clears the
                    # descending segment and stays readable.
                    dy = 18 if yi == 170 else 7
                    ax.annotate(f"{yi:,}\n({strong_labels[xi]})",
                                (xi, yi), textcoords="offset points",
                                xytext=(0, dy), ha="center", fontsize=7.5,
                                color="#222")
            else:
                ax.annotate(f"{yi:,}", (xi, yi),
                            textcoords="offset points",
                            xytext=(0, 7), ha="center", fontsize=7.5,
                            color="#222")
        ax.set_ylim(bottom=0, top=ymax * 1.28 + 1)

    # Mark the v3.0 threshold where the unanimity scope first becomes defined.
    for ax in axes:
        ax.axvline(2, color="#999", linestyle=":", linewidth=0.7, zorder=0)

    fig.tight_layout(h_pad=1.2, w_pad=1.4)
    out = OUT / "fig_kg_evolution.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"  wrote {out.name}")


# ============================================================================
# Figure 3: Precision-vs-k sweep (clean step curve, v6.0)
# ============================================================================
def fig_precision_vs_k():
    # v6.0 sweep recomputed end-to-end from kg_csv/nodes_graph_assertion.csv
    # against the doc-level gold (gold_assertions.csv); see
    # scripts/compute_precision_vs_k_v6.py.
    k = np.array([1, 2, 3, 4, 5, 6])
    precision = np.array([25.3, 41.7, 59.9, 71.3, 83.9, 90.6])
    recall    = np.array([88.2, 76.9, 58.0, 45.5, 29.2, 16.3])
    view_size = np.array([27_420, 15_120, 8_862, 5_808, 2_956, 1_236])

    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    ax2 = ax.twinx()

    ax.plot(k, precision, marker="o", color=C_ACCENT, linewidth=1.8,
            label="Gold precision (%)")
    ax.plot(k, recall,    marker="s", color=C_RED, linewidth=1.8,
            linestyle="--", label="Gold recall (%)")

    # Scope size as faint bars on secondary axis
    ax2.bar(k, view_size, color=C_BAR, alpha=0.55, width=0.55, zorder=0,
            label="View size (right axis)")
    ax2.set_ylabel("View size (assertions)", color="#555")
    ax2.tick_params(axis="y", labelcolor="#555")
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)

    ax.set_zorder(ax2.get_zorder() + 1)
    ax.patch.set_visible(False)

    ax.set_xticks(k)
    ax.set_xlabel("Agreement threshold $k$")
    ax.set_ylabel("Gold precision / recall (%)")
    ax.set_ylim(0, 105)

    # Value annotations
    for ki, p, r in zip(k, precision, recall):
        ax.annotate(f"{p:.1f}", (ki, p), textcoords="offset points",
                    xytext=(0, 7), ha="center", fontsize=7, color=C_ACCENT)
        ax.annotate(f"{r:.1f}", (ki, r), textcoords="offset points",
                    xytext=(0, -12), ha="center", fontsize=7, color=C_RED)

    lines_l, labels_l = ax.get_legend_handles_labels()
    lines_r, labels_r = ax2.get_legend_handles_labels()
    leg = ax.legend(lines_l + lines_r, labels_l + labels_r,
                    loc="lower center", bbox_to_anchor=(0.5, -0.42),
                    ncol=3, frameon=True, fancybox=False,
                    framealpha=0.95, edgecolor="#cccccc", fontsize=7,
                    handlelength=2.2, columnspacing=1.2)
    leg.get_frame().set_linewidth(0.5)

    out = OUT / "fig_precision_vs_k.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"  wrote {out.name}")


# ============================================================================
# Figure 4: Within vs cross family Jaccard (v6.0 closed grid, +11.4pp)
# ============================================================================
def fig_within_vs_cross():
    # Numbers verbatim from main_ieee_v6.tex (sec:within-cross-family and
    # tab:within_cross_retr). Closed 2x3 grid at v6.0.
    labels = ["LLM family", "Retriever family"]
    within    = [0.3184, 0.4218]
    cross     = [0.4326, 0.4017]
    within_sd = [0.1127, 0.0718]
    cross_sd  = [0.0734, 0.1060]

    x = np.arange(len(labels))
    w = 0.32

    fig, ax = plt.subplots(figsize=(3.5, 2.5))
    ax.bar(x - w/2, within, w, yerr=within_sd, capsize=3,
           color="#a3c4f3", edgecolor="#1f6feb",
           error_kw=dict(ecolor="#1f6feb", lw=0.8),
           label="Within-family")
    ax.bar(x + w/2, cross, w, yerr=cross_sd, capsize=3,
           color="#f3a3a3", edgecolor=C_RED,
           error_kw=dict(ecolor=C_RED, lw=0.8),
           label="Cross-family")

    # delta annotations (cross - within), in percentage points
    deltas = [(c - w_) * 100 for c, w_ in zip(cross, within)]
    for xi, w_, c, d in zip(x, within, cross, deltas):
        y = max(w_, c) + 0.08
        sign = "+" if d >= 0 else ""
        ax.text(xi, y, f"$\\Delta = {sign}{d:.1f}$pp",
                ha="center", fontsize=7, color="#1a1a1a")

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Mean Jaccard distance")
    ax.set_ylim(0, 0.75)
    ax.set_title("Witness independence by axis (v6.0, closed $2{\\times}3$)",
                 fontsize=9, pad=4)
    ax.legend(frameon=False, loc="upper right", fontsize=7)

    out = OUT / "fig_within_vs_cross.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"  wrote {out.name}")


# ============================================================================
# Figure 5: Precision per consensus scope (aesthetic horizontal ladder)
# Numbers: scope sizes from kg_snapshot_v6.json (scope_counts); per-scope
# gold precision/recall and distinct ATT&CK IDs from precision_vs_k_v6.csv
# (k=1 -> prediction-only, k=2 -> corroborated, k=6 -> unanimity);
# gold-backed precision = 100% by construction.
# ============================================================================
def fig_precision_by_scope():
    import matplotlib.patches as mpatches

    # scope, k-label, size, distinct ATT&CK IDs, precision %, recall %, colour
    # Ordered from the broadest (outer ring) to the strictest (inner core).
    nodes = [
        ("Prediction-only",     "$k\\geq1$",  7_211, 139, 25.3, 88.2, C_PRED),
        ("Corroborated",        "$k\\geq2$",  4_522, 124, 41.7, 76.9, C_CONS),
        ("Unanimity",           "$k=6$",        126,  50, 90.6, 16.3, C_STRONG),
    ]
    names     = [n[0] for n in nodes]
    klabels   = [n[1] for n in nodes]
    sizes     = [n[2] for n in nodes]
    ids       = [n[3] for n in nodes]
    precision = [n[4] for n in nodes]
    recall    = [n[5] for n in nodes]
    colours   = [n[6] for n in nodes]

    n = len(nodes)
    # Concentric radii: outer scope largest, strictest core smallest.
    radii = np.linspace(1.0, 0.40, n)

    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    ax.set_aspect("equal")

    # ---- concentric discs (outer -> inner) ---------------------------------
    for r, col in zip(radii, colours):
        ax.add_patch(mpatches.Circle((0, 0), r, facecolor=col,
                                     edgecolor="white", linewidth=2.2,
                                     alpha=0.92, zorder=2))

    # ---- precision label sitting in each ring band -------------------------
    # Each band centre is between its radius and the next-inner radius.
    edges = list(radii) + [0.0]
    for i in range(n):
        band_mid = (edges[i] + edges[i + 1]) / 2
        col = colours[i]
        is_core = (i == n - 1)
        ty = 0.0 if is_core else band_mid
        ax.annotate(f"{precision[i]:.1f}%", xy=(0, ty + 0.045),
                    ha="center", va="center", fontsize=13,
                    fontweight="bold", color="white", zorder=5)
        ax.annotate("precision", xy=(0, ty - 0.055), ha="center",
                    va="center", fontsize=7, color="white",
                    alpha=0.92, zorder=5)

    # ---- right-side legend with scope name, threshold, size, recall --------
    lx = 1.12
    ly = np.linspace(0.42, -0.42, n)
    for yi, col, name, kl, sz, nid, p, rc in zip(
            ly, colours, names, klabels, sizes, ids, precision, recall):
        ax.add_patch(mpatches.Circle((lx, yi), 0.07, facecolor=col,
                                     edgecolor="white", linewidth=1.2,
                                     zorder=4))
        ax.annotate(f"{name}  ({kl})", xy=(lx + 0.13, yi + 0.055),
                    ha="left", va="center", fontsize=9.5,
                    fontweight="bold", color=col, zorder=5)
        ax.annotate(f"{sz:,} assertions  $\\cdot$  {nid} ATT&CK IDs",
                    xy=(lx + 0.13, yi - 0.045), ha="left", va="center",
                    fontsize=7.2, color="#555", zorder=5)
        ax.annotate(f"precision {p:.1f}%   $\\cdot$   recall {rc:.0f}%",
                    xy=(lx + 0.13, yi - 0.135), ha="left", va="center",
                    fontsize=7.2, color="#777", zorder=5)

    ax.set_title("Corroboration across LLMs lifts extraction precision (v6.0)",
                 fontsize=11, pad=10, loc="center", fontweight="bold")

    ax.set_xlim(-1.12, 3.10)
    ax.set_ylim(-1.18, 1.18)
    ax.axis("off")

    fig.tight_layout()
    out = OUT / "fig_precision_by_scope.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"  wrote {out.name}")


# ============================================================================
# Figure 6: Precision vs. accumulated ExtractionSetups / LLM families
# The major claim: holding the trust view at unanimity (agreement among all
# setups present), gold precision rises monotonically as
# each version adds one ExtractionSetup; the two largest jumps coincide with
# the introduction of a *new LLM family* (Mistral at v2.0, Phi-3.5 at v5.0).
# Numbers verbatim from scripts/compute_precision_vs_version_v6.py ->
# deliverables/v6_kg_analysis/precision_vs_version_v6.csv.
# ============================================================================
def fig_precision_vs_setups():
    v          = np.array([1, 2, 3, 4, 5, 6])
    prec_mean  = np.array([38.0, 65.2, 69.6, 75.3, 88.2, 90.6])
    prec_tram  = np.array([38.7, 70.7, 73.8, 77.0, 87.5, 90.2])
    prec_anno  = np.array([37.2, 59.7, 65.4, 73.6, 88.9, 90.9])
    recall     = np.array([71.1, 49.2, 46.2, 37.3, 22.0, 16.3])
    fam_cum    = [1, 2, 2, 2, 3, 3]
    added      = ["GTE$\\times$Llama", "E5$\\times$Mistral", "GTE$\\times$Mistral",
                  "E5$\\times$Llama", "E5$\\times$Phi-3.5", "GTE$\\times$Phi-3.5"]
    new_family = [False, True, False, False, True, False]  # Mistral@v2, Phi@v5

    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    ax2 = ax.twinx()

    # Per-dataset precision (thin, muted), then aggregate mean (bold).
    ax.plot(v, prec_tram, marker="^", markersize=4.5, color=C_CONS,
            linewidth=1.0, linestyle="--", alpha=0.7,
            markeredgecolor="white", markeredgewidth=0.6,
            label="Precision, TRAM v2")
    ax.plot(v, prec_anno, marker="v", markersize=4.5, color=C_PRED,
            linewidth=1.0, linestyle="--", alpha=0.7,
            markeredgecolor="white", markeredgewidth=0.6,
            label="Precision, AnnoCTR")
    ax.plot(v, prec_mean, marker="o", markersize=7.5, color=C_STRONG,
            linewidth=2.8, zorder=6,
            markeredgecolor="white", markeredgewidth=1.0,
            label="Precision, mean")

    # Recall on secondary axis.
    ax2.plot(v, recall, marker="s", markersize=4.5, color=C_RED,
             linewidth=1.4, linestyle=":", alpha=0.9,
             markeredgecolor="white", markeredgewidth=0.6,
             label="Recall, mean")
    ax2.set_ylabel("Gold recall (%)", color=C_RED)
    ax2.tick_params(axis="y", labelcolor=C_RED, length=2.5)
    ax2.set_ylim(0, 100)
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color("#bbbbbb")
    ax2.spines["right"].set_linewidth(0.7)
    ax2.spines["top"].set_visible(False)

    ax.set_zorder(ax2.get_zorder() + 1)
    ax.patch.set_visible(False)

    # Delta-precision annotations between consecutive versions; emphasise the
    # two new-family jumps.
    for i in range(1, len(v)):
        d = prec_mean[i] - prec_mean[i - 1]
        xm = (v[i] + v[i - 1]) / 2
        ym = (prec_mean[i] + prec_mean[i - 1]) / 2
        big = new_family[i]
        dy = (12 if big else 9) if ym < 84 else -15
        ax.annotate(f"$+{d:.1f}$", (xm, ym), textcoords="offset points",
                    xytext=(0, dy), ha="center",
                    fontsize=8.5 if big else 7,
                    fontweight="bold" if big else "normal",
                    color="#1a1a1a" if big else "#999999")

    # Mean-precision value labels.
    for vi, p in zip(v, prec_mean):
        ax.annotate(f"{p:.1f}", (vi, p), textcoords="offset points",
                    xytext=(0, -14), ha="center", fontsize=7.5,
                    color=C_STRONG, fontweight="bold")

    # "New LLM family" callouts: plain black text, no box.
    for vi, nf, gen in zip(v, new_family, ["", "Mistral", "", "", "Phi-3.5", ""]):
        if nf:
            ax.annotate(f"new LLM family\n({gen})", xy=(vi, 99),
                        ha="center", va="top", fontsize=7.5,
                        color="black", fontweight="bold")

    ax.set_xticks(v)
    ax.set_xticklabels([f"v{vi}.0 $\\cdot$ {a}\n({f} LLM fam.)"
                        for vi, a, f in zip(v, added, fam_cum)], fontsize=7)
    ax.set_xlabel("GraphVersion $=$ accumulated ExtractionSetups (Retriever $\\times$ Generator)")
    ax.set_ylabel("Gold precision (%)", color=C_STRONG)
    ax.tick_params(axis="y", labelcolor=C_STRONG, length=2.5)
    ax.set_ylim(0, 100)
    ax.set_xlim(0.4, 6.6)
    ax.grid(axis="y", alpha=0.22, linewidth=0.5)
    ax.grid(axis="x", alpha=0.0)

    lines_l, labels_l = ax.get_legend_handles_labels()
    lines_r, labels_r = ax2.get_legend_handles_labels()
    ax.legend(lines_l + lines_r, labels_l + labels_r,
              loc="lower left", bbox_to_anchor=(0.015, 0.04),
              ncol=1, frameon=False, fontsize=7, handlelength=2.4,
              labelspacing=0.35)

    fig.tight_layout()
    out = OUT / "fig_precision_vs_setups.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"  wrote {out.name}")


# ============================================================================
if __name__ == "__main__":
    print("Generating figures...")
    fig_trust_ladder()
    fig_kg_evolution()
    fig_precision_vs_k()
    fig_within_vs_cross()
    fig_precision_by_scope()
    fig_precision_vs_setups()
    print("Done.")

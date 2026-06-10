"""
viz_v2.py — Figuras profesionales específicas de la solución mejorada.

Reutiliza el estilo de visualization y añade:
  - Convergencia de 3 tuners (MC, GA, Bayes) en el mismo eje de presupuesto.
  - Composición de los 5 pesos (incluye w5 de balanceo de carga).
  - Comparación Base vs Mejorada del makespan (la figura "titular").
  - Mejora pareada en test de cada tuner respecto a neutros.
  - Gap de optimalidad del JV frente al MILP exacto.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from simulacion.visualization import _apply_style, _boxplot_compat

TERM_LABELS_5 = ["w1\nEnergía", "w2\nBatería", "w3\nCapacidad",
                 "w4\nEspera", "w5\nCarga"]

C_BASE = "#e74c3c"
C_IMPROVED = "#2ecc71"
C_MC = "#3498db"
C_GA = "#f39c12"
C_BAYES = "#9b59b6"
_TUNER_COLORS = {"Monte Carlo": C_MC, "Genético": C_GA, "Bayesiano": C_BAYES}


def plot_convergence_multi(curves: dict, objective_label: str,
                           output_path, title=None) -> None:
    """curves: {nombre: (eval_curve, conv_curve)}."""
    _apply_style()
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.axhline(1.0, color="#7f8c8d", linestyle=":", linewidth=1.5,
               label="Pesos neutros (referencia)")
    for name, (evals, conv) in curves.items():
        color = _TUNER_COLORS.get(name, None)
        ax.plot(evals, conv, linewidth=2.2, label=name, color=color)
        if conv:
            ax.scatter([evals[-1]], [conv[-1]], s=55, zorder=5,
                       edgecolors="white", linewidth=1.2, color=color)
    ax.set_xlabel("Nº de evaluaciones de la simulación (presupuesto)")
    ax.set_ylabel(f"Mejor objetivo normalizado ({objective_label})")
    ax.set_title(title or "Convergencia de los tres métodos de tuning",
                 fontsize=14, fontweight="bold")
    ax.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)


def plot_weights5(weights_by_method: dict, output_path, title=None) -> None:
    """weights_by_method: {nombre: [w1..w5]}."""
    _apply_style()
    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    methods = list(weights_by_method.keys())
    n = len(methods)
    x = np.arange(5)
    width = 0.8 / max(n, 1)
    palette = ["#95a5a6", C_MC, C_GA, C_BAYES, "#1abc9c"]
    for idx, m in enumerate(methods):
        vals = weights_by_method[m]
        off = (idx - (n - 1) / 2) * width
        bars = ax.bar(x + off, vals, width, label=m,
                      color=palette[idx % len(palette)], edgecolor="white", alpha=0.9)
        for b, v in zip(bars, vals):
            ax.annotate(f"{v:.2f}", xy=(b.get_x() + b.get_width() / 2, v),
                        ha="center", va="bottom", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(TERM_LABELS_5)
    ax.set_ylabel("Peso normalizado (suma = 1)")
    ax.set_title(title or "Composición de los 5 pesos por método",
                 fontsize=14, fontweight="bold")
    ax.legend(loc="upper right", fontsize=9)
    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)


def plot_base_vs_improved(stages: list, times_by_stage: list,
                          output_path, title=None) -> None:
    """
    Barras del makespan medio en test para cada etapa de mejora.
    stages: lista de nombres; times_by_stage: lista de arrays por escenario.
    Anota la mejora acumulada respecto a la primera etapa (base).
    """
    _apply_style()
    fig, ax = plt.subplots(figsize=(10, 5.8))
    means = [float(np.mean(t)) for t in times_by_stage]
    stds = [float(np.std(t)) for t in times_by_stage]
    palette = [C_BASE, "#e67e22", "#f1c40f", C_IMPROVED, "#16a085"]
    bars = ax.bar(stages, means, yerr=stds, capsize=5,
                  color=[palette[i % len(palette)] for i in range(len(stages))],
                  edgecolor="white", linewidth=1.2, alpha=0.92)
    base = means[0]
    for i, (b, m) in enumerate(zip(bars, means)):
        txt = "baseline" if i == 0 else f"{(base - m) / base * 100:+.1f}%"
        ax.annotate(txt, xy=(b.get_x() + b.get_width() / 2, m),
                    ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_ylabel("Makespan medio en test (s)")
    ax.set_title(title or "Makespan: solución base vs. mejoras acumuladas",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)


def plot_test_improvement(method_names, base_arr, methods_arrs,
                          output_path, ylabel, title=None) -> None:
    """Boxplots de mejora pareada (%) de cada método respecto al baseline."""
    _apply_style()
    fig, ax = plt.subplots(figsize=(9, 5.5))
    base = np.asarray(base_arr, dtype=float)
    improvements = []
    for arr in methods_arrs:
        arr = np.asarray(arr, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            improvements.append(np.where(base > 0, (base - arr) / base * 100, 0.0))
    bp = _boxplot_compat(ax, improvements, method_names, patch_artist=True,
                         widths=0.55, showmeans=True,
                         meanprops=dict(marker="D", markerfacecolor="white",
                                        markeredgecolor="black", markersize=6))
    palette = [C_MC, C_GA, C_BAYES]
    for i, box in enumerate(bp["boxes"]):
        box.set_facecolor(palette[i % len(palette)])
        box.set_alpha(0.75)
    ax.axhline(0.0, color="#2c3e50", linestyle="--", linewidth=1.5)
    for i, impr in enumerate(improvements):
        ax.annotate(f"media {np.mean(impr):+.2f}%", xy=(i + 1, np.mean(impr)),
                    xytext=(0, 14), textcoords="offset points", ha="center",
                    fontsize=9, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.set_title(title or "Mejora pareada respecto a neutros (test)",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)


def plot_milp_gap(milp_makespan, jv_makespan, output_path, title=None) -> None:
    """Barras: makespan óptimo (MILP) vs JV, anotando el gap."""
    _apply_style()
    fig, ax = plt.subplots(figsize=(7, 5.5))
    vals = [milp_makespan, jv_makespan]
    bars = ax.bar(["MILP\n(óptimo exacto)", "JV\n(heurístico)"], vals,
                  color=[C_IMPROVED, C_MC], edgecolor="white", linewidth=1.2, alpha=0.9)
    gap = (jv_makespan - milp_makespan) / milp_makespan * 100 if milp_makespan > 0 else 0
    ax.annotate("óptimo", xy=(0, milp_makespan), ha="center", va="bottom",
                fontsize=10, fontweight="bold")
    ax.annotate(f"gap {gap:+.1f}%", xy=(1, jv_makespan), ha="center", va="bottom",
                fontsize=11, fontweight="bold", color=C_BASE)
    ax.set_ylabel("Makespan en un ciclo de carga (s)")
    ax.set_title(title or "Gap de optimalidad del heurístico JV",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)

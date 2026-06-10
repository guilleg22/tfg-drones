"""
visualization.py — Gráficas de resultados para el TFG.

Genera las visualizaciones más relevantes para contrastar resultados:
  1. Barras comparativas Greedy vs JV (energía, tiempo, entregas)
  2. Box plots de distribución sobre N escenarios
  3. Curvas de convergencia (Monte Carlo y GA)
  4. Frente de Pareto (NSGA-II)
  5. Heatmap de la matriz de costes
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")  # Backend sin GUI para generar PNGs
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from simulacion.metrics import ComparisonMetrics


# ── Estilo global ────────────────────────────────────────────────────────────

def _apply_style():
    """Aplica estilo profesional para publicación (con fallback robusto)."""
    for style in ("seaborn-v0_8-whitegrid", "seaborn-whitegrid", "ggplot"):
        if style in plt.style.available:
            plt.style.use(style)
            break
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 12,
        "axes.edgecolor": "#444444",
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "legend.frameon": True,
        "legend.framealpha": 0.9,
    })


def _boxplot_compat(ax, data, tick_labels, **kwargs):
    """boxplot compatible con matplotlib viejo (labels) y nuevo (tick_labels)."""
    import inspect
    params = inspect.signature(ax.boxplot).parameters
    key = "tick_labels" if "tick_labels" in params else "labels"
    return ax.boxplot(data, **{key: tick_labels}, **kwargs)


# Colores consistentes
COLOR_GREEDY = "#e74c3c"    # rojo
COLOR_JV = "#2ecc71"        # verde
COLOR_MC = "#3498db"        # azul
COLOR_GA = "#f39c12"        # naranja
COLOR_PARETO = "#9b59b6"    # morado


# ── 1. Barras comparativas ──────────────────────────────────────────────────

def plot_comparison_bars(
    metrics: ComparisonMetrics,
    output_path: str | Path,
) -> None:
    """
    Gráfica de barras agrupadas: Greedy vs JV.

    Muestra energía total, tiempo total y pedidos entregados.
    """
    _apply_style()

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))

    # ── Energía ──
    ax = axes[0]
    bars = ax.bar(
        ["Greedy", "JV (Costes)"],
        [metrics.avg_greedy_energy, metrics.avg_jv_energy],
        color=[COLOR_GREEDY, COLOR_JV],
        edgecolor="white",
        linewidth=1.5,
    )
    ax.set_title("Energía Total Promedio")
    ax.set_ylabel("Energía (Wh)")
    # Anotar mejora
    if metrics.energy_saving_pct != 0:
        ax.annotate(
            f"{metrics.energy_saving_pct:+.1f}%",
            xy=(1, metrics.avg_jv_energy),
            ha="center", va="bottom",
            fontsize=12, fontweight="bold",
            color=COLOR_JV if metrics.energy_saving_pct > 0 else COLOR_GREEDY,
        )
    sig = "(p<0.05)" if metrics.significant_energy else ""
    ax.set_xlabel(f"p = {metrics.p_value_energy:.4f} {sig}")

    # ── Tiempo ──
    ax = axes[1]
    ax.bar(
        ["Greedy", "JV (Costes)"],
        [metrics.avg_greedy_time, metrics.avg_jv_time],
        color=[COLOR_GREEDY, COLOR_JV],
        edgecolor="white",
        linewidth=1.5,
    )
    ax.set_title("Tiempo Total Promedio (Makespan)")
    ax.set_ylabel("Tiempo (s)")
    if metrics.time_saving_pct != 0:
        ax.annotate(
            f"{metrics.time_saving_pct:+.1f}%",
            xy=(1, metrics.avg_jv_time),
            ha="center", va="bottom",
            fontsize=12, fontweight="bold",
            color=COLOR_JV if metrics.time_saving_pct > 0 else COLOR_GREEDY,
        )
    sig = "(p<0.05)" if metrics.significant_time else ""
    ax.set_xlabel(f"p = {metrics.p_value_time:.4f} {sig}")

    # ── Entregas ──
    ax = axes[2]
    ax.bar(
        ["Greedy", "JV (Costes)"],
        [metrics.avg_greedy_delivered, metrics.avg_jv_delivered],
        color=[COLOR_GREEDY, COLOR_JV],
        edgecolor="white",
        linewidth=1.5,
    )
    ax.set_title("Pedidos Entregados Promedio")
    ax.set_ylabel("Nº Pedidos")

    fig.suptitle(
        f"Comparación Greedy vs. Jonker-Volgenant (N={metrics.n_scenarios} escenarios)",
        fontsize=14, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)


# ── 2. Box plots ────────────────────────────────────────────────────────────

def plot_comparison_boxplots(
    metrics: ComparisonMetrics,
    output_path: str | Path,
) -> None:
    """
    Box plots de distribución de energía y tiempo sobre N escenarios.
    Muestra la dispersión y permite ver outliers.
    """
    _apply_style()

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # ── Energía ──
    ax = axes[0]
    bp = _boxplot_compat(
        ax,
        [metrics.greedy_energies, metrics.jv_energies],
        ["Greedy", "JV (Costes)"],
        patch_artist=True,
        widths=0.5,
    )
    bp["boxes"][0].set_facecolor(COLOR_GREEDY)
    bp["boxes"][1].set_facecolor(COLOR_JV)
    for box in bp["boxes"]:
        box.set_alpha(0.7)
    ax.set_title("Distribución de Energía Total")
    ax.set_ylabel("Energía (Wh)")

    # ── Tiempo ──
    ax = axes[1]
    bp = _boxplot_compat(
        ax,
        [metrics.greedy_times, metrics.jv_times],
        ["Greedy", "JV (Costes)"],
        patch_artist=True,
        widths=0.5,
    )
    bp["boxes"][0].set_facecolor(COLOR_GREEDY)
    bp["boxes"][1].set_facecolor(COLOR_JV)
    for box in bp["boxes"]:
        box.set_alpha(0.7)
    ax.set_title("Distribución de Tiempo Total")
    ax.set_ylabel("Tiempo (s)")

    fig.suptitle(
        f"Distribución sobre {metrics.n_scenarios} escenarios",
        fontsize=14, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)


# ── 3. Convergencia MC y GA ─────────────────────────────────────────────────

def plot_convergence(
    mc_curve: list[float] | None = None,
    ga_curve: list[float] | None = None,
    ga_avg_curve: list[float] | None = None,
    output_path: str | Path = "convergence.png",
) -> None:
    """
    Curvas de convergencia de Monte Carlo y/o Algoritmo Genético.
    """
    _apply_style()

    n_subplots = sum([mc_curve is not None, ga_curve is not None])
    if n_subplots == 0:
        return

    fig, axes = plt.subplots(1, n_subplots, figsize=(7 * n_subplots, 5))
    if n_subplots == 1:
        axes = [axes]

    idx = 0

    if mc_curve is not None:
        ax = axes[idx]
        ax.plot(range(1, len(mc_curve) + 1), mc_curve, color=COLOR_MC, linewidth=1.5)
        ax.set_title("Convergencia Monte Carlo")
        ax.set_xlabel("Nº Trial")
        ax.set_ylabel("Mejor Objetivo")
        ax.set_xlim(1, len(mc_curve))
        idx += 1

    if ga_curve is not None:
        ax = axes[idx]
        gens = range(1, len(ga_curve) + 1)
        ax.plot(gens, ga_curve, color=COLOR_GA, linewidth=2, label="Mejor")
        if ga_avg_curve is not None:
            ax.plot(gens, ga_avg_curve, color=COLOR_GA, linewidth=1,
                    alpha=0.5, linestyle="--", label="Promedio")
            ax.legend()
        ax.set_title("Convergencia Algoritmo Genético")
        ax.set_xlabel("Generación")
        ax.set_ylabel("Fitness (objetivo)")
        ax.set_xlim(1, len(ga_curve))

    fig.suptitle("Convergencia de Optimizadores", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)


# ── 4. Frente de Pareto ─────────────────────────────────────────────────────

def plot_pareto_front(
    pareto_front: np.ndarray,
    output_path: str | Path,
    highlight_idx: int | None = None,
) -> None:
    """
    Gráfica del frente de Pareto (energía vs. tiempo) de NSGA-II.

    Parameters
    ----------
    pareto_front : np.ndarray
        Nx2 array con columnas [energía, tiempo].
    output_path : str or Path
        Ruta del fichero PNG.
    highlight_idx : int or None
        Índice de la solución a resaltar (ej. la más equilibrada).
    """
    _apply_style()

    fig, ax = plt.subplots(figsize=(8, 6))

    # Ordenar por energía para línea conectada
    sorted_idx = np.argsort(pareto_front[:, 0])
    sorted_front = pareto_front[sorted_idx]

    ax.plot(
        sorted_front[:, 0], sorted_front[:, 1],
        color=COLOR_PARETO, linewidth=1.5, alpha=0.5, linestyle="--",
    )
    ax.scatter(
        pareto_front[:, 0], pareto_front[:, 1],
        color=COLOR_PARETO, s=60, zorder=5, edgecolors="white", linewidth=1,
    )

    if highlight_idx is not None and 0 <= highlight_idx < len(pareto_front):
        ax.scatter(
            [pareto_front[highlight_idx, 0]],
            [pareto_front[highlight_idx, 1]],
            color="#e74c3c", s=220, zorder=10, marker="*",
            edgecolors="white", linewidth=1.5,
        )
        ax.annotate(
            "  Mejor equilibrio",
            xy=(pareto_front[highlight_idx, 0], pareto_front[highlight_idx, 1]),
            fontsize=10, fontweight="bold",
        )

    ax.set_xlabel("Energía Total Promedio (Wh)")
    ax.set_ylabel("Tiempo Total Promedio (s)")
    ax.set_title(
        f"Frente de Pareto — NSGA-II ({len(pareto_front)} soluciones)",
        fontsize=14, fontweight="bold",
    )

    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)


# ── 5. Heatmap de matriz de costes ──────────────────────────────────────────

def plot_cost_heatmap(
    cost_matrix: np.ndarray,
    drone_labels: list[str],
    order_labels: list[str],
    output_path: str | Path,
) -> None:
    """
    Heatmap de la matriz de costes C[drones × pedidos].

    Las celdas con coste ≥ 1e17 (infactibles) se muestran en gris.
    """
    _apply_style()

    # Reemplazar inf/1e18 por NaN para el heatmap
    display_matrix = cost_matrix.copy()
    display_matrix[display_matrix >= 1e17] = np.nan

    fig, ax = plt.subplots(figsize=(max(8, len(order_labels) * 0.5), max(4, len(drone_labels) * 0.8)))

    im = ax.imshow(display_matrix, cmap="YlOrRd", aspect="auto")

    # Marcar infactibles
    mask = np.isnan(display_matrix)
    for i in range(len(drone_labels)):
        for j in range(len(order_labels)):
            if mask[i, j]:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=True,
                                           facecolor="#cccccc", edgecolor="white"))
                ax.text(j, i, "∞", ha="center", va="center", fontsize=8, color="#666")
            else:
                val = display_matrix[i, j]
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7)

    ax.set_xticks(range(len(order_labels)))
    ax.set_xticklabels(order_labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(drone_labels)))
    ax.set_yticklabels(drone_labels, fontsize=9)
    ax.set_xlabel("Pedidos")
    ax.set_ylabel("Drones")
    ax.set_title("Matriz de Costes C(i,j)", fontsize=14, fontweight="bold")

    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("Coste")

    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)


# ── 6. Comparación de convergencia MC vs GA (presupuesto compartido) ─────────

# Etiquetas de los 4 términos de la función de costes
TERM_LABELS = [
    "w1\nEnergía",
    "w2\nBatería",
    "w3\nCapacidad",
    "w4\nEspera",
]


def plot_optimizer_comparison(
    mc_eval_curve: list[int],
    mc_conv: list[float],
    ga_eval_curve: list[int],
    ga_conv: list[float],
    objective_label: str,
    output_path: str | Path,
    title: str | None = None,
) -> None:
    """
    Convergencia de Monte Carlo vs Algoritmo Genético en el MISMO eje de
    presupuesto (nº de evaluaciones de la simulación).

    El objetivo está normalizado contra los pesos neutros: el valor 1.0
    (línea discontinua) equivale al rendimiento de los pesos neutros, de modo
    que valores < 1.0 indican mejora. Esto permite comparar de forma justa
    qué método encuentra mejores pesos con el mismo coste de cómputo.
    """
    _apply_style()
    fig, ax = plt.subplots(figsize=(9, 5.5))

    ax.axhline(1.0, color="#7f8c8d", linestyle=":", linewidth=1.5,
               label="Pesos neutros (referencia)", zorder=1)

    ax.plot(mc_eval_curve, mc_conv, color=COLOR_MC, linewidth=2.2,
            label="Monte Carlo", zorder=3)
    ax.plot(ga_eval_curve, ga_conv, color=COLOR_GA, linewidth=2.2,
            label="Algoritmo Genético", zorder=3)

    # Marcar el mejor valor final de cada método
    if mc_conv:
        ax.scatter([mc_eval_curve[-1]], [mc_conv[-1]], color=COLOR_MC,
                   s=60, zorder=5, edgecolors="white", linewidth=1.2)
    if ga_conv:
        ax.scatter([ga_eval_curve[-1]], [ga_conv[-1]], color=COLOR_GA,
                   s=60, zorder=5, edgecolors="white", linewidth=1.2)

    ax.set_xlabel("Nº de evaluaciones de la simulación (presupuesto)")
    ax.set_ylabel(f"Mejor objetivo normalizado ({objective_label})")
    ax.set_title(title or "Convergencia: Monte Carlo vs. Algoritmo Genético",
                 fontsize=14, fontweight="bold")
    ax.legend(loc="upper right")

    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)


# ── 7. Composición de pesos por método ──────────────────────────────────────

def plot_weights_comparison(
    weights_by_method: dict[str, list[float]],
    output_path: str | Path,
    title: str | None = None,
) -> None:
    """
    Barras agrupadas con la composición de pesos (w1..w4) que encuentra cada
    método. Permite ver de un vistazo en qué término concentra el peso cada
    estrategia de optimización.

    Parameters
    ----------
    weights_by_method : dict
        {"Neutros": [w1,w2,w3,w4], "Monte Carlo": [...], "GA": [...]}
    """
    _apply_style()
    fig, ax = plt.subplots(figsize=(9, 5.5))

    methods = list(weights_by_method.keys())
    n_methods = len(methods)
    n_terms = 4
    x = np.arange(n_terms)
    width = 0.8 / max(n_methods, 1)

    palette = [COLOR_GREEDY, COLOR_MC, COLOR_GA, COLOR_PARETO, "#1abc9c"]

    for idx, method in enumerate(methods):
        vals = weights_by_method[method]
        offset = (idx - (n_methods - 1) / 2) * width
        bars = ax.bar(x + offset, vals, width, label=method,
                      color=palette[idx % len(palette)], edgecolor="white",
                      linewidth=1.0, alpha=0.9)
        for b, v in zip(bars, vals):
            ax.annotate(f"{v:.2f}", xy=(b.get_x() + b.get_width() / 2, v),
                        ha="center", va="bottom", fontsize=7.5)

    ax.set_xticks(x)
    ax.set_xticklabels(TERM_LABELS)
    ax.set_ylabel("Peso normalizado (suma = 1)")
    ax.set_title(title or "Composición de pesos por método",
                 fontsize=14, fontweight="bold")
    ax.legend(loc="upper right")
    ax.set_ylim(0, max(0.6, max(max(v) for v in weights_by_method.values()) * 1.25))

    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)


# ── 8. Comparación en el conjunto de test (Neutros vs MC vs GA) ──────────────

def plot_method_test_comparison(
    method_names: list[str],
    times_by_method: list[list[float]],
    energies_by_method: list[list[float]],
    output_path: str | Path,
    title: str | None = None,
) -> None:
    """
    Compara el rendimiento en el conjunto de test (held-out) de cada conjunto
    de pesos.

    La comparación es PAREADA: cada escenario se evalúa con los tres juegos de
    pesos. Por eso, en lugar de barras absolutas (cuya enorme varianza entre
    escenarios oculta el efecto real), se muestra la **mejora porcentual por
    escenario** de cada método respecto al baseline neutro. La caja resume la
    distribución de esa mejora; la línea en 0 % es "igual que neutros".

    Convención: ``method_names[0]`` debe ser el baseline neutro.
    """
    _apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    base_t = np.asarray(times_by_method[0], dtype=float)
    base_e = np.asarray(energies_by_method[0], dtype=float)
    opt_names = method_names[1:]
    palette = [COLOR_MC, COLOR_GA, COLOR_PARETO]

    def _improvements(base, data_list):
        out = []
        for d in data_list:
            d = np.asarray(d, dtype=float)
            with np.errstate(divide="ignore", invalid="ignore"):
                impr = np.where(base > 0, (base - d) / base * 100.0, 0.0)
            out.append(impr)
        return out

    def _panel(ax, base, opt_data, ylabel, title_p):
        improvements = _improvements(base, opt_data)
        bp = _boxplot_compat(ax, improvements, opt_names,
                             patch_artist=True, widths=0.55, showmeans=True,
                             meanprops=dict(marker="D", markerfacecolor="white",
                                            markeredgecolor="black", markersize=6))
        for i, box in enumerate(bp["boxes"]):
            box.set_facecolor(palette[i % len(palette)])
            box.set_alpha(0.75)
        ax.axhline(0.0, color="#2c3e50", linestyle="--", linewidth=1.5)
        # Anotar la media de cada método
        for i, impr in enumerate(improvements):
            ax.annotate(f"media {np.mean(impr):+.2f}%",
                        xy=(i + 1, np.mean(impr)),
                        xytext=(0, 14), textcoords="offset points",
                        ha="center", fontsize=9, fontweight="bold")
        ax.set_ylabel(ylabel)
        ax.set_title(title_p)

    _panel(axes[0], base_t, times_by_method[1:],
           "Mejora del makespan vs neutros (%)", "Tiempo total (makespan)")
    _panel(axes[1], base_e, energies_by_method[1:],
           "Mejora de energía vs neutros (%)", "Energía total")

    fig.suptitle(title or "Mejora pareada respecto a los pesos neutros (test)",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)


# ── 9. Sensibilidad de la función de costes a cada término ───────────────────

def plot_weight_sensitivity(
    term_labels: list[str],
    times: list[float],
    energies: list[float],
    baseline_time: float,
    baseline_energy: float,
    output_path: str | Path,
    title: str | None = None,
) -> None:
    """
    Análisis de sensibilidad: efecto de concentrar todo el peso en un único
    término (p.ej. [1,0,0,0]) sobre el makespan y la energía, comparado con
    los pesos neutros (línea de referencia).

    Muestra qué término de la función de costes gobierna realmente cada métrica
    — justificación directa del diseño de la función de costes.
    """
    _apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    # ── Makespan ──
    ax = axes[0]
    colors = ["#3498db" if t <= baseline_time else "#e67e22" for t in times]
    bars = ax.bar(term_labels, times, color=colors, edgecolor="white",
                  linewidth=1.2, alpha=0.9)
    ax.axhline(baseline_time, color="#2c3e50", linestyle="--", linewidth=1.6,
               label="Pesos neutros")
    for b, t in zip(bars, times):
        impr = (baseline_time - t) / baseline_time * 100 if baseline_time > 0 else 0.0
        ax.annotate(f"{impr:+.1f}%", xy=(b.get_x() + b.get_width() / 2, t),
                    ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_ylabel("Makespan (s)")
    ax.set_title("Sensibilidad del tiempo a cada término")
    ax.legend(loc="best")
    lo = min(times + [baseline_time]) * 0.97
    hi = max(times + [baseline_time]) * 1.03
    ax.set_ylim(lo, hi)

    # ── Energía ──
    ax = axes[1]
    colors = ["#2ecc71" if e <= baseline_energy else "#e67e22" for e in energies]
    bars = ax.bar(term_labels, energies, color=colors, edgecolor="white",
                  linewidth=1.2, alpha=0.9)
    ax.axhline(baseline_energy, color="#2c3e50", linestyle="--", linewidth=1.6,
               label="Pesos neutros")
    for b, e in zip(bars, energies):
        impr = (baseline_energy - e) / baseline_energy * 100 if baseline_energy > 0 else 0.0
        ax.annotate(f"{impr:+.1f}%", xy=(b.get_x() + b.get_width() / 2, e),
                    ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_ylabel("Energía (Wh)")
    ax.set_title("Sensibilidad de la energía a cada término")
    ax.legend(loc="best")
    lo = min(energies + [baseline_energy]) * 0.99
    hi = max(energies + [baseline_energy]) * 1.01
    ax.set_ylim(lo, hi)

    fig.suptitle(title or "Análisis de sensibilidad de la función de costes",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(str(output_path))
    plt.close(fig)

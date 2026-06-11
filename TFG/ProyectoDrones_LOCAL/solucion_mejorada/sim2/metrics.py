"""
metrics.py — Cálculo de métricas comparativas y tests estadísticos.

Compara resultados de Greedy vs Jonker-Volgenant con:
  - Mejoras porcentuales (energía, tiempo)
  - Test t pareado para significancia estadística
  - Exportación a tablas LaTeX para la memoria del TFG
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from sim2.simulator import SimulationResult


@dataclass
class ComparisonMetrics:
    """Métricas comparativas Greedy vs JV sobre N escenarios."""

    # Datos por escenario
    n_scenarios: int
    greedy_energies: list[float]
    jv_energies: list[float]
    greedy_times: list[float]
    jv_times: list[float]
    greedy_delivered: list[int]
    jv_delivered: list[int]

    # Medias
    avg_greedy_energy: float
    avg_jv_energy: float
    avg_greedy_time: float
    avg_jv_time: float
    avg_greedy_delivered: float
    avg_jv_delivered: float

    # Mejoras porcentuales (positivo = JV es mejor)
    energy_saving_pct: float
    time_saving_pct: float

    # Tests estadísticos (t-test pareado)
    p_value_energy: float
    p_value_time: float
    significant_energy: bool  # p < 0.05
    significant_time: bool


def compute_comparison(
    greedy_results: list[SimulationResult],
    jv_results: list[SimulationResult],
) -> ComparisonMetrics:
    """
    Calcula métricas comparativas con significancia estadística.

    Usa t-test pareado (cada escenario se ejecuta con ambos algoritmos)
    para determinar si las diferencias son estadísticamente significativas.

    Parameters
    ----------
    greedy_results : list[SimulationResult]
        Resultados del greedy para cada escenario.
    jv_results : list[SimulationResult]
        Resultados de JV para los mismos escenarios.

    Returns
    -------
    ComparisonMetrics
    """
    n = len(greedy_results)
    assert n == len(jv_results), "Deben tener el mismo número de escenarios"
    assert n >= 2, "Se necesitan al menos 2 escenarios para test estadístico"

    g_energies = [r.total_energy_wh for r in greedy_results]
    j_energies = [r.total_energy_wh for r in jv_results]
    g_times = [r.total_time_s for r in greedy_results]
    j_times = [r.total_time_s for r in jv_results]
    g_delivered = [r.n_delivered for r in greedy_results]
    j_delivered = [r.n_delivered for r in jv_results]

    avg_g_e = np.mean(g_energies)
    avg_j_e = np.mean(j_energies)
    avg_g_t = np.mean(g_times)
    avg_j_t = np.mean(j_times)

    # Mejoras porcentuales (positivo = JV consume/tarda menos)
    energy_saving = ((avg_g_e - avg_j_e) / avg_g_e * 100) if avg_g_e > 0 else 0.0
    time_saving = ((avg_g_t - avg_j_t) / avg_g_t * 100) if avg_g_t > 0 else 0.0

    # T-test pareado
    if n >= 2:
        t_stat_e, p_energy = stats.ttest_rel(g_energies, j_energies)
        t_stat_t, p_time = stats.ttest_rel(g_times, j_times)
    else:
        p_energy = 1.0
        p_time = 1.0

    return ComparisonMetrics(
        n_scenarios=n,
        greedy_energies=g_energies,
        jv_energies=j_energies,
        greedy_times=g_times,
        jv_times=j_times,
        greedy_delivered=g_delivered,
        jv_delivered=j_delivered,
        avg_greedy_energy=float(avg_g_e),
        avg_jv_energy=float(avg_j_e),
        avg_greedy_time=float(avg_g_t),
        avg_jv_time=float(avg_j_t),
        avg_greedy_delivered=float(np.mean(g_delivered)),
        avg_jv_delivered=float(np.mean(j_delivered)),
        energy_saving_pct=energy_saving,
        time_saving_pct=time_saving,
        p_value_energy=float(p_energy),
        p_value_time=float(p_time),
        significant_energy=p_energy < 0.05,
        significant_time=p_time < 0.05,
    )


def to_latex_table(metrics: ComparisonMetrics) -> str:
    """
    Genera tabla LaTeX comparativa para la memoria del TFG.

    Returns
    -------
    str
        Código LaTeX de la tabla.
    """
    sig_e = "Sí" if metrics.significant_energy else "No"
    sig_t = "Sí" if metrics.significant_time else "No"

    latex = r"""
\begin{table}[htbp]
\centering
\caption{Comparación Greedy vs. Jonker-Volgenant (N=%d escenarios)}
\label{tab:comparison}
\begin{tabular}{lrrr}
\hline
\textbf{Métrica} & \textbf{Greedy} & \textbf{JV (Costes)} & \textbf{Mejora (\%%)} \\
\hline
Energía total (Wh) & %.2f & %.2f & %.2f \\
Tiempo total (s) & %.2f & %.2f & %.2f \\
Pedidos entregados & %.1f & %.1f & — \\
\hline
\multicolumn{4}{l}{\textit{Significancia estadística (p < 0.05):}} \\
Energía (p-value) & \multicolumn{2}{c}{%.4f} & %s \\
Tiempo (p-value) & \multicolumn{2}{c}{%.4f} & %s \\
\hline
\end{tabular}
\end{table}
""" % (
        metrics.n_scenarios,
        metrics.avg_greedy_energy, metrics.avg_jv_energy, metrics.energy_saving_pct,
        metrics.avg_greedy_time, metrics.avg_jv_time, metrics.time_saving_pct,
        metrics.avg_greedy_delivered, metrics.avg_jv_delivered,
        metrics.p_value_energy, sig_e,
        metrics.p_value_time, sig_t,
    )
    return latex.strip()


def results_summary_text(metrics: ComparisonMetrics) -> str:
    """Genera un resumen textual de los resultados."""
    lines = [
        "=" * 60,
        "RESULTADOS: Greedy vs. Jonker-Volgenant",
        "=" * 60,
        f"Escenarios evaluados: {metrics.n_scenarios}",
        "",
        "── Energía Total (Wh) ──",
        f"  Greedy:       {metrics.avg_greedy_energy:10.2f} Wh",
        f"  JV (Costes):  {metrics.avg_jv_energy:10.2f} Wh",
        f"  Ahorro:       {metrics.energy_saving_pct:+.2f}%",
        f"  p-value:      {metrics.p_value_energy:.4f} ({'SIGNIFICATIVO' if metrics.significant_energy else 'no significativo'})",
        "",
        "── Tiempo Total (s) ──",
        f"  Greedy:       {metrics.avg_greedy_time:10.2f} s",
        f"  JV (Costes):  {metrics.avg_jv_time:10.2f} s",
        f"  Ahorro:       {metrics.time_saving_pct:+.2f}%",
        f"  p-value:      {metrics.p_value_time:.4f} ({'SIGNIFICATIVO' if metrics.significant_time else 'no significativo'})",
        "",
        "── Pedidos Entregados ──",
        f"  Greedy:       {metrics.avg_greedy_delivered:.1f}",
        f"  JV (Costes):  {metrics.avg_jv_delivered:.1f}",
        "=" * 60,
    ]
    return "\n".join(lines)

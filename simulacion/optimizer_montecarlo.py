"""
optimizer_montecarlo.py — Monte Carlo Random Search para optimizar pesos w1-w4.

Muestrea aleatoriamente el espacio de pesos usando Latin Hypercube Sampling
y evalúa cada combinación ejecutando simulaciones JV
(scipy.optimize.linear_sum_assignment) sobre un lote de escenarios.

La función objetivo está centralizada en ``simulacion.objective`` y normalizada
contra los pesos neutros, de forma que sus resultados son directamente
comparables con los del Algoritmo Genético bajo el mismo presupuesto de
evaluaciones.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from simulacion.cost_function import CostWeights
from simulacion.objective import Baseline, ObjectiveEvaluator, improvement_pct
from simulacion.scenario_generator import Scenario
from simulacion.simulator import Simulator


@dataclass
class MCResult:
    """Resultado de la optimización Monte Carlo."""
    best_weights: CostWeights
    best_energy: float
    best_time: float
    best_objective: float
    n_trials: int
    all_trials: list[dict]             # [{weights, energy, time, objective}]
    convergence_curve: list[float]     # mejor objetivo en cada trial
    objective_type: str                # "energy", "time", "combined"
    # ── Campos nuevos para comparación rigurosa ──
    n_evaluations: int = 0             # nº de simulaciones-lote ejecutadas
    eval_curve: list[int] = field(default_factory=list)  # nº evals acumuladas por trial
    baseline_energy: float = 0.0       # energía con pesos neutros (Wh)
    baseline_time: float = 0.0         # tiempo con pesos neutros (s)
    energy_improvement_pct: float = 0.0  # mejora de energía vs neutros (%)
    time_improvement_pct: float = 0.0    # mejora de tiempo vs neutros (%)


def _latin_hypercube_sample(n_samples: int, n_dims: int, rng: np.random.Generator) -> np.ndarray:
    """
    Genera muestras usando Latin Hypercube Sampling.

    Cada dimensión se divide en n_samples intervalos iguales,
    y se toma una muestra aleatoria de cada intervalo.

    Returns
    -------
    np.ndarray
        Matriz (n_samples, n_dims) con valores en [0, 1].
    """
    samples = np.zeros((n_samples, n_dims))
    for dim in range(n_dims):
        intervals = np.arange(n_samples) / n_samples
        points = intervals + rng.uniform(0, 1.0 / n_samples, n_samples)
        rng.shuffle(points)
        samples[:, dim] = points
    return samples


def optimize_montecarlo(
    scenarios: list[Scenario],
    n_trials: int = 5000,
    objective: str = "time",
    w_range: tuple[float, float] = (0.0, 10.0),
    seed: int = 42,
    charger_power_w: float = 180.0,
    verbose: bool = True,
    baseline: Baseline | None = None,
) -> MCResult:
    """
    Optimiza los pesos w1,w2,w3,w4 mediante Monte Carlo Random Search.

    Para cada trial:
      1. Muestrear 4 pesos con Latin Hypercube Sampling en [0, w_max]
      2. Normalizar para que sumen 1
      3. Evaluar el objetivo normalizado (simulación JV sobre los escenarios)
      4. Guardar si mejora el mejor conocido

    Parameters
    ----------
    scenarios : list[Scenario]
        Escenarios de evaluación (ejecutados con cada combinación de pesos).
    n_trials : int
        Número de combinaciones a probar.
    objective : str
        "energy" (minimizar energía), "time" (minimizar makespan),
        "combined" (0.5·energía_norm + 0.5·tiempo_norm).
        Por defecto "time": la energía total es casi invariante a los pesos en
        problemas de reparto saturados (todos los pedidos deben entregarse),
        mientras que el makespan sí responde al reparto de carga.
    w_range : tuple
        Rango de valores para los pesos antes de normalizar.
    seed : int
        Semilla para reproducibilidad.
    charger_power_w : float
        Potencia del cargador (W).
    verbose : bool
        Si True, imprime progreso cada 10% de trials.
    baseline : Baseline or None
        Baseline de pesos neutros. Si None se calcula automáticamente.

    Returns
    -------
    MCResult
    """
    rng = np.random.default_rng(seed)
    sim = Simulator(charger_power_w=charger_power_w)
    evaluator = ObjectiveEvaluator(sim, scenarios, objective, baseline=baseline)

    # Generar muestras con LHS y escalar al rango deseado (5 pesos: w1..w5)
    raw_samples = _latin_hypercube_sample(n_trials, 5, rng)
    samples = raw_samples * (w_range[1] - w_range[0]) + w_range[0]

    all_trials: list[dict] = []
    convergence: list[float] = []
    eval_curve: list[int] = []
    best_objective = float("inf")
    best_weights = CostWeights()
    best_energy = 0.0
    best_time = 0.0

    log_interval = max(1, n_trials // 10)

    for trial_idx in range(n_trials):
        # Crear pesos normalizados
        raw = samples[trial_idx]
        total = raw.sum()
        if total <= 0:
            normalized = np.array([0.25, 0.25, 0.25, 0.25])
        else:
            normalized = raw / total
        weights = CostWeights.from_array(normalized)

        obj, avg_energy, avg_time = evaluator.evaluate(weights)

        all_trials.append({
            "weights": [float(x) for x in normalized],
            "energy": float(avg_energy),
            "time": float(avg_time),
            "objective": float(obj),
        })

        if obj < best_objective:
            best_objective = obj
            best_weights = weights
            best_energy = float(avg_energy)
            best_time = float(avg_time)

        convergence.append(best_objective)
        eval_curve.append(evaluator.n_evals)

        if verbose and (trial_idx + 1) % log_interval == 0:
            pct = (trial_idx + 1) / n_trials * 100
            print(
                f"  MC [{pct:5.1f}%] Trial {trial_idx + 1}/{n_trials} | "
                f"Mejor obj: {best_objective:.4f} | "
                f"w=[{best_weights.w1:.3f}, {best_weights.w2:.3f}, "
                f"{best_weights.w3:.3f}, {best_weights.w4:.3f}]"
            )

    base = evaluator.baseline
    return MCResult(
        best_weights=best_weights,
        best_energy=best_energy,
        best_time=best_time,
        best_objective=best_objective,
        n_trials=n_trials,
        all_trials=all_trials,
        convergence_curve=convergence,
        objective_type=objective,
        n_evaluations=evaluator.n_evals,
        eval_curve=eval_curve,
        baseline_energy=base.energy,
        baseline_time=base.time,
        energy_improvement_pct=improvement_pct(base.energy, best_energy),
        time_improvement_pct=improvement_pct(base.time, best_time),
    )

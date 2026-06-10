"""
optimizer_bayes.py — Optimización Bayesiana de los pesos (scikit-optimize).

Tercer método de obtención de parámetros, añadido en la solución mejorada.
Frente a Monte Carlo (muestreo ciego) y al GA (evolución poblacional), la
optimización bayesiana construye un **modelo sustituto** (proceso gaussiano) de
la función objetivo y usa una función de adquisición (Expected Improvement)
para decidir el siguiente punto a evaluar. Es el enfoque más eficiente en
número de evaluaciones para espacios continuos de baja dimensión como este
(5 pesos), y es el estado del arte en configuración automática de algoritmos
(misma familia que SMAC).

Optimiza exactamente la misma función objetivo normalizada (objective),
por lo que es directamente comparable con MC y GA.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np

from simulacion.cost_function import CostWeights
from simulacion.objective import Baseline, ObjectiveEvaluator, improvement_pct
from simulacion.scenario_generator import Scenario
from simulacion.simulator import Simulator


@dataclass
class BayesResult:
    """Resultado de la optimización bayesiana."""
    best_weights: CostWeights
    best_objective: float
    best_energy: float
    best_time: float
    n_calls: int
    convergence_curve: list[float]
    objective_type: str
    n_evaluations: int = 0
    eval_curve: list[int] = field(default_factory=list)
    baseline_energy: float = 0.0
    baseline_time: float = 0.0
    energy_improvement_pct: float = 0.0
    time_improvement_pct: float = 0.0


def optimize_bayes(
    scenarios: list[Scenario],
    n_calls: int = 80,
    n_initial_points: int = 16,
    objective: str = "time",
    seed: int = 42,
    charger_power_w: float = 180.0,
    verbose: bool = True,
    baseline: Baseline | None = None,
) -> BayesResult:
    """
    Optimiza los 5 pesos w1..w5 con optimización bayesiana (gp_minimize).

    Las variables son los pesos sin normalizar en [0,1]; se normalizan dentro
    del objetivo (suman 1), igual que en MC y GA.
    """
    from skopt import gp_minimize
    from skopt.space import Real

    sim = Simulator(charger_power_w=charger_power_w)
    evaluator = ObjectiveEvaluator(sim, scenarios, objective, baseline=baseline)

    best_obj = [float("inf")]
    best_w = [CostWeights(0.2, 0.2, 0.2, 0.2, 0.2)]
    best_em = [0.0, 0.0]
    convergence: list[float] = []
    eval_curve: list[int] = []

    def f(x):
        raw = np.asarray(x, dtype=float)
        total = raw.sum()
        norm = raw / total if total > 0 else np.full(5, 0.2)
        w = CostWeights.from_array(norm)
        obj, energy, time = evaluator.evaluate(w)
        if obj < best_obj[0]:
            best_obj[0] = obj
            best_w[0] = w
            best_em[0], best_em[1] = energy, time
        convergence.append(best_obj[0])
        eval_curve.append(evaluator.n_evals)
        return obj

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gp_minimize(
            f,
            [Real(0.0, 1.0)] * 5,
            n_calls=n_calls,
            n_initial_points=n_initial_points,
            acq_func="EI",
            random_state=seed,
        )

    if verbose:
        w = best_w[0]
        print(f"  Bayes: obj={best_obj[0]:.4f} evals={evaluator.n_evals} "
              f"w=[{w.w1:.3f},{w.w2:.3f},{w.w3:.3f},{w.w4:.3f},{w.w5:.3f}]")

    base = evaluator.baseline
    return BayesResult(
        best_weights=best_w[0],
        best_objective=best_obj[0],
        best_energy=best_em[0],
        best_time=best_em[1],
        n_calls=n_calls,
        convergence_curve=convergence,
        objective_type=objective,
        n_evaluations=evaluator.n_evals,
        eval_curve=eval_curve,
        baseline_energy=base.energy,
        baseline_time=base.time,
        energy_improvement_pct=improvement_pct(base.energy, best_em[0]),
        time_improvement_pct=improvement_pct(base.time, best_em[1]),
    )

"""
optimizer_nsga2.py — Optimización multi-objetivo NSGA-II con pymoo.

Busca el frente de Pareto para dos objetivos simultáneos:
  - Minimizar energía total promedio (Wh)
  - Minimizar makespan promedio (s)

Variables de decisión: w1, w2, w3, w4 ∈ [0, 10]
Cada individuo define una configuración de pesos para la función de costes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from simulacion.cost_function import CostWeights
from simulacion.scenario_generator import Scenario
from simulacion.simulator import Simulator


@dataclass
class NSGA2Result:
    """Resultado de la optimización NSGA-II."""
    pareto_front: np.ndarray            # Nx2 (energía, tiempo)
    pareto_weights: list[CostWeights]   # pesos correspondientes
    n_solutions: int
    n_generations: int


def optimize_nsga2(
    scenarios: list[Scenario],
    pop_size: int = 50,
    n_generations: int = 100,
    seed: int = 42,
    charger_power_w: float = 180.0,
    verbose: bool = True,
) -> NSGA2Result:
    """
    Optimiza pesos con NSGA-II para encontrar el frente de Pareto
    energía vs. tiempo.

    Parameters
    ----------
    scenarios : list[Scenario]
        Escenarios de evaluación.
    pop_size : int
        Tamaño de la población.
    n_generations : int
        Número de generaciones.
    seed : int
        Semilla para reproducibilidad.
    charger_power_w : float
        Potencia del cargador (W).
    verbose : bool
        Si True, imprime progreso.

    Returns
    -------
    NSGA2Result
    """
    try:
        from pymoo.algorithms.moo.nsga2 import NSGA2
        from pymoo.core.problem import ElementwiseProblem
        from pymoo.operators.crossover.sbx import SBX
        from pymoo.operators.mutation.pm import PM
        from pymoo.operators.sampling.rnd import FloatRandomSampling
        from pymoo.optimize import minimize
        from pymoo.termination import get_termination
    except ImportError:
        raise ImportError(
            "pymoo no está instalado. Ejecuta: pip install pymoo>=0.6\n"
            "Se necesita para la optimización multi-objetivo NSGA-II."
        )

    sim = Simulator(charger_power_w=charger_power_w)

    class CostWeightsProblem(ElementwiseProblem):
        """
        Problema bi-objetivo:
          - f1: minimizar energía total promedio
          - f2: minimizar makespan promedio

        4 variables: w1, w2, w3, w4 ∈ [0, 10]
        """

        def __init__(self):
            super().__init__(
                n_var=4,
                n_obj=2,
                xl=np.array([0.0, 0.0, 0.0, 0.0]),
                xu=np.array([10.0, 10.0, 10.0, 10.0]),
            )

        def _evaluate(self, x, out, *args, **kwargs):
            # Normalizar pesos
            total = x.sum()
            if total > 0:
                normalized = x / total
            else:
                normalized = np.array([0.25, 0.25, 0.25, 0.25])

            weights = CostWeights.from_array(normalized)
            results = sim.run_batch(scenarios, "cost_matrix", weights)

            avg_energy = np.mean([r.total_energy_wh for r in results])
            avg_time = np.mean([r.total_time_s for r in results])

            out["F"] = [avg_energy, avg_time]

    problem = CostWeightsProblem()

    algorithm = NSGA2(
        pop_size=pop_size,
        sampling=FloatRandomSampling(),
        crossover=SBX(prob=0.9, eta=15),
        mutation=PM(eta=20),
        eliminate_duplicates=True,
    )

    termination = get_termination("n_gen", n_generations)

    if verbose:
        print(f"  NSGA-II: {pop_size} individuos × {n_generations} generaciones")
        print(f"  Evaluando sobre {len(scenarios)} escenarios...")

    res = minimize(
        problem,
        algorithm,
        termination,
        seed=seed,
        verbose=verbose,
    )

    # Extraer frente de Pareto
    pareto_F = res.F  # Nx2 (energía, tiempo)
    pareto_X = res.X  # Nx4 (pesos brutos)

    # Normalizar pesos de las soluciones del frente
    pareto_weights_list = []
    for x in pareto_X:
        total = x.sum()
        if total > 0:
            normalized = x / total
        else:
            normalized = np.array([0.25, 0.25, 0.25, 0.25])
        pareto_weights_list.append(CostWeights.from_array(normalized))

    if verbose:
        print(f"  NSGA-II completado: {len(pareto_F)} soluciones en el frente de Pareto")

    return NSGA2Result(
        pareto_front=pareto_F,
        pareto_weights=pareto_weights_list,
        n_solutions=len(pareto_F),
        n_generations=n_generations,
    )

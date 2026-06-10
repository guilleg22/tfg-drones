"""
optimizer_genetic.py — Algoritmo Genético mono-objetivo.

Evoluciona una población de vectores de pesos [w1, w2, w3, w4] para minimizar
una métrica normalizada (energía, tiempo o combinada) sobre un lote de
escenarios, usando el asignador JV (scipy.optimize.linear_sum_assignment).

La función objetivo es la MISMA que usa Monte Carlo (simulacion.objective),
normalizada contra los pesos neutros, de modo que ambos métodos son
directamente comparables.

Operadores:
  - Selección: Torneo (k=3)
  - Cruce: BLX-α (α=0.5)
  - Mutación: Gaussiana (σ=0.5, indpb=0.3)
  - Elitismo: top 5%

Nota sobre eficiencia: la evaluación es determinista (mismos escenarios), por
lo que la élite re-insertada no se vuelve a simular: el evaluador cachea los
resultados por vector de pesos. Esto hace que el presupuesto real de
simulaciones sea comparable con el de Monte Carlo.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np

from simulacion.cost_function import CostWeights
from simulacion.objective import Baseline, ObjectiveEvaluator, improvement_pct
from simulacion.scenario_generator import Scenario
from simulacion.simulator import Simulator


@dataclass
class GAResult:
    """Resultado de la optimización con Algoritmo Genético."""
    best_weights: CostWeights
    best_objective: float
    best_energy: float
    best_time: float
    n_generations: int
    convergence_curve: list[float]     # mejor fitness por generación
    avg_fitness_curve: list[float]     # fitness promedio por generación
    objective_type: str
    # ── Campos nuevos para comparación rigurosa ──
    n_evaluations: int = 0             # nº de simulaciones-lote (sin contar caché)
    eval_curve: list[int] = field(default_factory=list)  # nº evals acumuladas por generación
    baseline_energy: float = 0.0
    baseline_time: float = 0.0
    energy_improvement_pct: float = 0.0
    time_improvement_pct: float = 0.0


def _blx_alpha_crossover(ind1: list, ind2: list, alpha: float = 0.5) -> tuple[list, list]:
    """
    Blend Crossover (BLX-α) para variables continuas.

    Para cada gen i:
      d = |ind1[i] - ind2[i]|
      child[i] ~ Uniform(min - α·d, max + α·d)
    """
    child1, child2 = list(ind1), list(ind2)
    for i in range(len(ind1)):
        lo = min(ind1[i], ind2[i])
        hi = max(ind1[i], ind2[i])
        d = hi - lo
        new_lo = max(0.0, lo - alpha * d)
        new_hi = hi + alpha * d
        child1[i] = random.uniform(new_lo, new_hi)
        child2[i] = random.uniform(new_lo, new_hi)
    return child1, child2


def _normalize(vec: list[float]) -> list[float]:
    total = sum(vec)
    if total > 0:
        return [x / total for x in vec]
    return [0.25, 0.25, 0.25, 0.25]


def optimize_genetic(
    scenarios: list[Scenario],
    pop_size: int = 50,
    n_generations: int = 100,
    cx_prob: float = 0.7,
    mut_prob: float = 0.2,
    mut_sigma: float = 0.5,
    mut_indpb: float = 0.3,
    objective: str = "time",
    elite_pct: float = 0.05,
    seed: int = 42,
    charger_power_w: float = 180.0,
    verbose: bool = True,
    baseline: Baseline | None = None,
) -> GAResult:
    """
    Optimiza pesos w1-w4 con Algoritmo Genético.

    Individuo: [w1, w2, w3, w4] normalizados (suman 1)
    Fitness: minimizar objetivo normalizado sobre escenarios (JV)

    Parameters
    ----------
    scenarios : list[Scenario]
        Escenarios de evaluación.
    pop_size, n_generations : int
        Tamaño de población y nº de generaciones.
    cx_prob, mut_prob, mut_sigma, mut_indpb : float
        Parámetros de los operadores genéticos.
    objective : str
        "energy", "time" (por defecto) o "combined". Ver nota en
        optimizer_montecarlo sobre por qué "time" es el objetivo informativo.
    elite_pct : float
        Fracción de élite preservada (0.05 = 5%).
    seed : int
        Semilla para reproducibilidad.
    charger_power_w : float
        Potencia del cargador (W).
    verbose : bool
        Si True, imprime progreso por generación.
    baseline : Baseline or None
        Baseline de pesos neutros. Si None se calcula automáticamente.

    Returns
    -------
    GAResult
    """
    rng = random.Random(seed)
    sim = Simulator(charger_power_w=charger_power_w)
    evaluator = ObjectiveEvaluator(sim, scenarios, objective, baseline=baseline)

    n_elite = max(1, int(pop_size * elite_pct))

    # ── Inicializar población ──
    population: list[list[float]] = []
    for _ in range(pop_size):
        raw = [rng.uniform(0.0, 10.0) for _ in range(5)]  # 5 pesos: w1..w5
        population.append(_normalize(raw))

    def evaluate(individual: list[float]) -> float:
        obj, _, _ = evaluator.evaluate(CostWeights.from_array(individual))
        return obj

    # ── Evaluar población inicial ──
    fitnesses = [evaluate(ind) for ind in population]

    convergence: list[float] = []
    avg_fitness_curve: list[float] = []
    eval_curve: list[int] = []

    for gen in range(n_generations):
        # ── Ordenar por fitness (menor = mejor) ──
        paired = sorted(zip(fitnesses, population), key=lambda x: x[0])
        fitnesses = [p[0] for p in paired]
        population = [p[1] for p in paired]

        best_fit = fitnesses[0]
        avg_fit = float(np.mean(fitnesses))
        convergence.append(best_fit)
        avg_fitness_curve.append(avg_fit)
        eval_curve.append(evaluator.n_evals)

        if verbose and (gen + 1) % max(1, n_generations // 10) == 0:
            best_w = population[0]
            print(
                f"  GA Gen {gen + 1:3d}/{n_generations} | "
                f"Mejor: {best_fit:.4f} | Prom: {avg_fit:.4f} | "
                f"w=[{best_w[0]:.3f}, {best_w[1]:.3f}, {best_w[2]:.3f}, {best_w[3]:.3f}]"
            )

        # ── Elitismo: preservar los mejores ──
        new_population = [list(ind) for ind in population[:n_elite]]

        # ── Generar descendencia ──
        while len(new_population) < pop_size:
            # Selección por torneo (k=3)
            cand = rng.sample(range(len(population)), min(3, len(population)))
            parent1_idx = min(cand, key=lambda i: fitnesses[i])
            cand = rng.sample(range(len(population)), min(3, len(population)))
            parent2_idx = min(cand, key=lambda i: fitnesses[i])

            child1 = list(population[parent1_idx])
            child2 = list(population[parent2_idx])

            # Cruce
            if rng.random() < cx_prob:
                child1, child2 = _blx_alpha_crossover(child1, child2, alpha=0.5)

            # Mutación gaussiana
            for child in (child1, child2):
                if rng.random() < mut_prob:
                    for i in range(len(child)):
                        if rng.random() < mut_indpb:
                            child[i] += rng.gauss(0, mut_sigma)
                            child[i] = max(0.0, child[i])

            # Normalizar y añadir
            for child in (child1, child2):
                norm = _normalize(child)
                if len(new_population) < pop_size:
                    new_population.append(norm)

        population = new_population
        fitnesses = [evaluate(ind) for ind in population]

    # ── Resultado final ──
    best_idx = int(np.argmin(fitnesses))
    best_individual = population[best_idx]
    best_weights = CostWeights.from_array(best_individual)

    # Métricas del mejor (desde la caché del evaluador)
    best_obj, best_energy, best_time = evaluator.evaluate(best_weights)

    base = evaluator.baseline
    return GAResult(
        best_weights=best_weights,
        best_objective=best_obj,
        best_energy=best_energy,
        best_time=best_time,
        n_generations=n_generations,
        convergence_curve=convergence,
        avg_fitness_curve=avg_fitness_curve,
        objective_type=objective,
        n_evaluations=evaluator.n_evals,
        eval_curve=eval_curve,
        baseline_energy=base.energy,
        baseline_time=base.time,
        energy_improvement_pct=improvement_pct(base.energy, best_energy),
        time_improvement_pct=improvement_pct(base.time, best_time),
    )

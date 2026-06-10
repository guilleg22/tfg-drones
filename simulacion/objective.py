"""
objective.py — Definición única y compartida de la función objetivo.

Tanto el optimizador Monte Carlo como el Algoritmo Genético deben optimizar
EXACTAMENTE la misma función para que su comparación sea justa. Este módulo
centraliza esa definición y resuelve dos problemas de la versión anterior:

  1. Normalización inconsistente del objetivo "combined": antes cada optimizador
     usaba su *primer trial aleatorio* como referencia, de modo que sus valores
     no eran comparables entre sí. Ahora ambos normalizan contra un **baseline
     fijo** (los pesos neutros w=[1,1,1,1]), calculado una sola vez.

  2. Falta de un punto de comparación interpretable. Al normalizar contra el
     baseline, un objetivo < 1.0 significa "mejor que los pesos neutros" y
     1.0 significa "igual que neutros". Esto permite reportar la mejora (%)
     directamente.

El asignador subyacente sigue siendo Jonker-Volgenant vía
``scipy.optimize.linear_sum_assignment`` (no se toca): este módulo solo decide
QUÉ valor escalar se minimiza al buscar los pesos.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from simulacion.cost_function import CostWeights
from simulacion.scenario_generator import Scenario
from simulacion.simulator import Simulator

# Objetivos soportados
VALID_OBJECTIVES = ("energy", "time", "combined")

# Pesos neutros usados como baseline de referencia
NEUTRAL_WEIGHTS = CostWeights(1.0, 1.0, 1.0, 1.0)


@dataclass(frozen=True)
class Baseline:
    """Métricas de referencia obtenidas con los pesos neutros."""

    energy: float   # energía total promedio con w=[1,1,1,1] (Wh)
    time: float     # makespan promedio con w=[1,1,1,1] (s)
    delivered: float  # pedidos entregados promedio

    @property
    def energy_ref(self) -> float:
        return max(self.energy, 1e-9)

    @property
    def time_ref(self) -> float:
        return max(self.time, 1e-9)


def compute_baseline(
    sim: Simulator,
    scenarios: list[Scenario],
) -> Baseline:
    """
    Evalúa los pesos neutros sobre los escenarios y devuelve las métricas
    de referencia. Se llama una sola vez al inicio de cada optimización.
    """
    results = sim.run_batch(scenarios, "cost_matrix", NEUTRAL_WEIGHTS)
    energy = float(np.mean([r.total_energy_wh for r in results]))
    time = float(np.mean([r.total_time_s for r in results]))
    delivered = float(np.mean([r.n_delivered for r in results]))
    return Baseline(energy=energy, time=time, delivered=delivered)


class ObjectiveEvaluator:
    """
    Evalúa un vector de pesos y devuelve (objetivo, energía, tiempo).

    El objetivo está siempre normalizado contra el baseline neutro:

      - "energy"   → energía_media / baseline.energy
      - "time"     → tiempo_media  / baseline.time
      - "combined" → 0.5·(energía/base_E) + 0.5·(tiempo/base_T)

    Lleva la cuenta del número de evaluaciones (cada evaluación = una
    simulación JV sobre TODO el lote de escenarios), lo que permite comparar
    Monte Carlo y GA bajo un mismo presupuesto de cómputo.
    """

    def __init__(
        self,
        sim: Simulator,
        scenarios: list[Scenario],
        objective: str,
        baseline: Baseline | None = None,
        w_energy: float = 0.5,
        w_time: float = 0.5,
    ):
        if objective not in VALID_OBJECTIVES:
            raise ValueError(
                f"Objetivo desconocido: {objective!r}. "
                f"Válidos: {VALID_OBJECTIVES}"
            )
        self.sim = sim
        self.scenarios = scenarios
        self.objective = objective
        self.baseline = baseline if baseline is not None else compute_baseline(sim, scenarios)
        self.w_energy = w_energy
        self.w_time = w_time
        self.n_evals = 0
        # Caché: pesos deterministas → resultado. Evita re-evaluar la élite
        # del GA y acelera ambos métodos sin alterar el resultado.
        self._cache: dict[tuple, tuple[float, float, float]] = {}

    def _scalarize(self, energy: float, time: float) -> float:
        be = self.baseline.energy_ref
        bt = self.baseline.time_ref
        if self.objective == "energy":
            return energy / be
        if self.objective == "time":
            return time / bt
        # combined
        return self.w_energy * (energy / be) + self.w_time * (time / bt)

    def evaluate(self, weights: CostWeights) -> tuple[float, float, float]:
        """
        Devuelve (objetivo_normalizado, energía_media_Wh, tiempo_media_s).
        """
        key = (round(weights.w1, 6), round(weights.w2, 6),
               round(weights.w3, 6), round(weights.w4, 6))
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        self.n_evals += 1
        results = self.sim.run_batch(self.scenarios, "cost_matrix", weights)
        energy = float(np.mean([r.total_energy_wh for r in results]))
        time = float(np.mean([r.total_time_s for r in results]))
        obj = self._scalarize(energy, time)

        out = (obj, energy, time)
        self._cache[key] = out
        return out


def improvement_pct(baseline_value: float, optimized_value: float) -> float:
    """
    Mejora porcentual (positivo = el optimizado es mejor = menor).

    Útil para reportar cuánto reduce el optimizador la energía o el tiempo
    respecto a los pesos neutros.
    """
    if baseline_value <= 0:
        return 0.0
    return (baseline_value - optimized_value) / baseline_value * 100.0

"""
objective.py — Función objetivo compartida (versión mejorada).

Además de los objetivos de la solución base (energy, time, combined,
normalizados contra los pesos neutros), añade objetivos **sensibles al riesgo**:

  - "time_p90"  → percentil 90 del makespan entre escenarios.
  - "time_cvar" → CVaR_90 (media del 10 % peor de los escenarios).

Motivación: en este problema las ganancias de la optimización vienen de
escenarios "patológicos" raros (los que cruzan una ronda extra de recarga).
Optimizar la MEDIA apenas los toca; optimizar el percentil 90 / la cola ataca
directamente esos casos, que son los que importan operativamente.

Todos los objetivos comparten el mismo evaluador y la misma normalización
(baseline = pesos neutros), de modo que Monte Carlo, Genético y Bayesiano
optimizan exactamente la misma función y son comparables.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from simulacion.cost_function import CostWeights
from simulacion.scenario_generator import Scenario
from simulacion.simulator import Simulator

VALID_OBJECTIVES = ("energy", "time", "combined", "time_p90", "time_cvar")

# Pesos neutros de referencia (5 términos; w5=1 incluye balanceo de carga).
NEUTRAL_WEIGHTS = CostWeights(1.0, 1.0, 1.0, 1.0, 1.0)

# Nivel para P90 / CVaR
_RISK_LEVEL = 90.0


def _cvar(values: np.ndarray, level: float = _RISK_LEVEL) -> float:
    """CVaR: media de los valores por encima del percentil `level`."""
    if len(values) == 0:
        return 0.0
    thr = np.percentile(values, level)
    tail = values[values >= thr]
    return float(tail.mean()) if len(tail) else float(values.max())


@dataclass(frozen=True)
class Baseline:
    """Métricas de referencia con los pesos neutros."""

    energy: float        # energía total media (Wh)
    time: float          # makespan medio (s)
    time_p90: float      # percentil 90 del makespan (s)
    time_cvar: float     # CVaR_90 del makespan (s)
    delivered: float

    @property
    def energy_ref(self) -> float:
        return max(self.energy, 1e-9)

    @property
    def time_ref(self) -> float:
        return max(self.time, 1e-9)

    @property
    def time_p90_ref(self) -> float:
        return max(self.time_p90, 1e-9)

    @property
    def time_cvar_ref(self) -> float:
        return max(self.time_cvar, 1e-9)


def compute_baseline(sim: Simulator, scenarios: list[Scenario]) -> Baseline:
    """Evalúa los pesos neutros y devuelve las métricas de referencia."""
    results = sim.run_batch(scenarios, "cost_matrix", NEUTRAL_WEIGHTS)
    energies = np.array([r.total_energy_wh for r in results])
    times = np.array([r.total_time_s for r in results])
    delivered = float(np.mean([r.n_delivered for r in results]))
    return Baseline(
        energy=float(energies.mean()),
        time=float(times.mean()),
        time_p90=float(np.percentile(times, _RISK_LEVEL)),
        time_cvar=_cvar(times),
        delivered=delivered,
    )


class ObjectiveEvaluator:
    """
    Evalúa un vector de pesos y devuelve (objetivo_normalizado, energía, tiempo).

    El objetivo se normaliza contra el baseline neutro (valor < 1.0 = mejor que
    neutros). Cuenta el número de evaluaciones para comparar tuners bajo el
    mismo presupuesto.
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
            raise ValueError(f"Objetivo desconocido: {objective!r}. Válidos: {VALID_OBJECTIVES}")
        self.sim = sim
        self.scenarios = scenarios
        self.objective = objective
        self.baseline = baseline if baseline is not None else compute_baseline(sim, scenarios)
        self.w_energy = w_energy
        self.w_time = w_time
        self.n_evals = 0
        self._cache: dict[tuple, tuple[float, float, float]] = {}

    def _scalarize(self, energies: np.ndarray, times: np.ndarray) -> float:
        b = self.baseline
        if self.objective == "energy":
            return float(energies.mean()) / b.energy_ref
        if self.objective == "time":
            return float(times.mean()) / b.time_ref
        if self.objective == "time_p90":
            return float(np.percentile(times, _RISK_LEVEL)) / b.time_p90_ref
        if self.objective == "time_cvar":
            return _cvar(times) / b.time_cvar_ref
        # combined
        return (self.w_energy * float(energies.mean()) / b.energy_ref
                + self.w_time * float(times.mean()) / b.time_ref)

    def evaluate(self, weights: CostWeights) -> tuple[float, float, float]:
        """Devuelve (objetivo_normalizado, energía_media_Wh, tiempo_medio_s)."""
        key = (round(weights.w1, 6), round(weights.w2, 6), round(weights.w3, 6),
               round(weights.w4, 6), round(weights.w5, 6))
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        self.n_evals += 1
        results = self.sim.run_batch(self.scenarios, "cost_matrix", weights)
        energies = np.array([r.total_energy_wh for r in results])
        times = np.array([r.total_time_s for r in results])
        obj = self._scalarize(energies, times)

        out = (obj, float(energies.mean()), float(times.mean()))
        self._cache[key] = out
        return out


def improvement_pct(baseline_value: float, optimized_value: float) -> float:
    """Mejora porcentual (positivo = el optimizado es menor)."""
    if baseline_value <= 0:
        return 0.0
    return (baseline_value - optimized_value) / baseline_value * 100.0

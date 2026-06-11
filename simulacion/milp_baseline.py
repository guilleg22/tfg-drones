"""
milp_baseline.py — Baseline exacto (MILP) para medir el gap de optimalidad.

El asignador JV (linear_sum_assignment) minimiza el COSTE de asignación por
ronda, que es un *proxy* del makespan. Para saber cuán lejos queda del óptimo
real de makespan, resolvemos de forma EXACTA una versión tratable del problema
con programación lineal entera (PuLP/CBC):

  Asignación makespan-óptima en un único ciclo de carga
  -----------------------------------------------------
  Variables:  x[i,j] ∈ {0,1}  (dron i sirve el pedido j)
  Objetivo:   minimizar T (makespan)
  Sujeto a:
     - cada pedido se sirve una vez:      Σ_i x[i,j] = 1
     - capacidad de batería por dron:     Σ_j x[i,j]·e_trip(i,j) ≤ batería_util_i
     - definición de makespan:            T ≥ Σ_j x[i,j]·t_trip(i,j)   ∀i
     - factibilidad de carga útil:        x[i,j] = 0 si peso_j > payload_i

Es exacto para instancias pequeñas que caben en un ciclo de carga. Comparando
su makespan óptimo con el que obtiene el JV sobre la misma instancia se
cuantifica el gap del heurístico.
"""

from __future__ import annotations

from dataclasses import dataclass

from simulacion.energy_model import estimate_trip_energy_wh, estimate_duration_s
from simulacion.scenario_generator import Scenario


@dataclass
class MILPResult:
    feasible: bool
    optimal_makespan_s: float
    assignment: dict           # order_id -> drone_id
    status: str


def solve_min_makespan_single_cycle(scenario: Scenario, safety_margin: float = 0.2) -> MILPResult:
    """
    Resuelve el makespan óptimo en un ciclo de carga con PuLP (CBC).

    Devuelve feasible=False si la instancia no cabe en un solo ciclo.
    """
    import pulp

    drones = scenario.drones
    orders = scenario.orders
    n, m = len(drones), len(orders)

    # Energía y tiempo de cada par (i,j); factibilidad por carga útil.
    e = {}
    t = {}
    feasible_pairs = []
    for i, d in enumerate(drones):
        for j, o in enumerate(orders):
            if o.weight_kg <= d.spec.max_payload_kg:
                e[(i, j)] = estimate_trip_energy_wh(d.spec, o.distance_km, o.weight_kg)
                t[(i, j)] = estimate_duration_s(o.distance_km, d.spec.cruise_speed_mps)
                feasible_pairs.append((i, j))

    prob = pulp.LpProblem("min_makespan_single_cycle", pulp.LpMinimize)
    x = {(i, j): pulp.LpVariable(f"x_{i}_{j}", cat="Binary") for (i, j) in feasible_pairs}
    T = pulp.LpVariable("T", lowBound=0)

    prob += T  # objetivo

    # Cada pedido se sirve exactamente una vez
    for j in range(m):
        vars_j = [x[(i, j)] for i in range(n) if (i, j) in x]
        if not vars_j:
            # Pedido que ningún dron puede servir → instancia infactible
            return MILPResult(False, 0.0, {}, "infeasible_payload")
        prob += pulp.lpSum(vars_j) == 1

    # Capacidad de batería por dron (un ciclo) y definición de makespan
    for i, d in enumerate(drones):
        usable = d.battery_wh * (1.0 - safety_margin)
        prob += pulp.lpSum(e[(i, j)] * x[(i, j)] for j in range(m) if (i, j) in x) <= usable
        prob += T >= pulp.lpSum(t[(i, j)] * x[(i, j)] for j in range(m) if (i, j) in x)

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    status_str = pulp.LpStatus[status]

    if status_str != "Optimal":
        return MILPResult(False, 0.0, {}, status_str)

    assignment = {}
    for (i, j), var in x.items():
        if var.value() is not None and var.value() > 0.5:
            assignment[orders[j].order_id] = drones[i].spec.drone_id

    return MILPResult(True, float(pulp.value(T)), assignment, "Optimal")

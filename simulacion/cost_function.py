"""
cost_function.py — Función de costes C(i,j) para asignación dron↔pedido.

Implementa la función de costes del TFG con 4 términos normalizados a [0,1]:

    C(i,j) = w1·E_viaje_norm + w2·PenalBatería_norm + w3·ExcesoCapacidad_norm + w4·T_espera_norm

Hard constraints (retorna inf):
  - peso > max_payload del dron
  - E_viaje > batería_disponible × 0.8 (no hay 20% de reserva)

Referencia: Investigación modulos y algoritmo.pdf, sección "FUNCION DE COSTES"
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from simulacion.energy_model import (
    DroneSpec,
    estimate_charge_time_s,
    estimate_trip_energy_wh,
)


@dataclass
class CostWeights:
    """Pesos de la función de costes (4 términos)."""

    w1: float = 1.0  # energía de viaje
    w2: float = 1.0  # equilibrio de batería
    w3: float = 1.0  # exceso de capacidad
    w4: float = 1.0  # tiempo de espera por recarga

    def as_array(self) -> np.ndarray:
        """Convierte a array numpy [w1, w2, w3, w4]."""
        return np.array([self.w1, self.w2, self.w3, self.w4], dtype=np.float64)

    @classmethod
    def from_array(cls, arr) -> CostWeights:
        """Crea CostWeights desde un array/lista de 4 valores."""
        return cls(w1=float(arr[0]), w2=float(arr[1]), w3=float(arr[2]), w4=float(arr[3]))

    def normalized(self) -> CostWeights:
        """Retorna una copia con pesos normalizados para que sumen 1."""
        total = self.w1 + self.w2 + self.w3 + self.w4
        if total <= 0:
            return CostWeights(0.25, 0.25, 0.25, 0.25)
        return CostWeights(
            w1=self.w1 / total,
            w2=self.w2 / total,
            w3=self.w3 / total,
            w4=self.w4 / total,
        )


# ── Constantes ───────────────────────────────────────────────────────────────

SAFETY_MARGIN = 0.2       # 20% de reserva obligatoria
BATTERY_LOW_THRESHOLD = 0.2  # umbral para penalización de batería baja

# Referencia para normalización de T_espera: recarga completa de dron pesado
_MAX_CHARGE_TIME_REF_S = estimate_charge_time_s(360.0, 180.0)  # ~7200 s


# ── Función de costes ────────────────────────────────────────────────────────


def compute_cost(
    drone_spec: DroneSpec,
    drone_battery_wh: float,
    order_weight_kg: float,
    distance_km: float,
    weights: CostWeights,
    charger_power_w: float = 180.0,
) -> float:
    """
    Calcula el coste C(i,j) de asignar el dron i al pedido j.

    Retorna math.inf si hay hard constraint violada (infactible).

    Parameters
    ----------
    drone_spec : DroneSpec
        Especificaciones del dron.
    drone_battery_wh : float
        Batería actual del dron (Wh).
    order_weight_kg : float
        Peso del pedido (kg).
    distance_km : float
        Distancia de ida parking→cliente (km).
    weights : CostWeights
        Pesos w1, w2, w3, w4.
    charger_power_w : float
        Potencia del cargador (W), para calcular T_espera.

    Returns
    -------
    float
        Coste escalar (≥ 0), o math.inf si infactible.
    """
    # ── Hard constraint 1: peso excede capacidad ──
    if order_weight_kg > drone_spec.max_payload_kg:
        return math.inf

    # ── Calcular energía del viaje ──
    e_trip = estimate_trip_energy_wh(drone_spec, distance_km, order_weight_kg)
    usable_battery = drone_battery_wh * (1.0 - SAFETY_MARGIN)

    # ── Hard constraint 2: energía excede batería disponible ──
    if e_trip > usable_battery:
        return math.inf

    # ── Término 1: Energía de viaje normalizada [0,1] ──
    # Fracción de la batería total consumida por este viaje
    t1 = e_trip / drone_spec.battery_capacity_wh if drone_spec.battery_capacity_wh > 0 else 0.0

    # ── Término 2: Penalización por batería baja [0,1] ──
    # E_sobrante_pct = fracción de batería que queda tras el viaje
    e_sobrante_wh = drone_battery_wh - e_trip
    e_sobrante_pct = e_sobrante_wh / drone_spec.battery_capacity_wh if drone_spec.battery_capacity_wh > 0 else 0.0
    # Si queda por debajo del umbral (20%), penalizar proporcionalmente
    if e_sobrante_pct < BATTERY_LOW_THRESHOLD:
        t2 = (BATTERY_LOW_THRESHOLD - e_sobrante_pct) / BATTERY_LOW_THRESHOLD
    else:
        t2 = 0.0

    # ── Término 3: Exceso de capacidad [0,1] ──
    # Penaliza usar drones grandes para paquetes pequeños
    t3 = (drone_spec.max_payload_kg - order_weight_kg) / drone_spec.max_payload_kg if drone_spec.max_payload_kg > 0 else 0.0

    # ── Término 4: Tiempo de espera por recarga [0,1] ──
    # Si el dron necesita recargarse antes de poder hacer este viaje, penalizar
    # Nota: este término aplica cuando la batería actual NO alcanza y habría
    # que recargar primero. Pero la hard constraint ya cubre el caso absoluto.
    # Aquí penalizamos si la batería restante tras el viaje es tan baja que
    # el dron necesitará recarga antes de la siguiente misión.
    energy_deficit_for_next = drone_spec.battery_capacity_wh * SAFETY_MARGIN - e_sobrante_wh
    if energy_deficit_for_next > 0:
        t_charge = estimate_charge_time_s(energy_deficit_for_next, charger_power_w)
        t4 = min(t_charge / _MAX_CHARGE_TIME_REF_S, 1.0)
    else:
        t4 = 0.0

    # ── Coste ponderado ──
    return weights.w1 * t1 + weights.w2 * t2 + weights.w3 * t3 + weights.w4 * t4


def compute_cost_components(
    drone_spec: DroneSpec,
    drone_battery_wh: float,
    order_weight_kg: float,
    distance_km: float,
    charger_power_w: float = 180.0,
) -> dict[str, float] | None:
    """
    Calcula los 4 componentes de coste individuales (sin ponderar).

    Retorna None si hay hard constraint violada.

    Returns
    -------
    dict con claves 't1_energy', 't2_battery', 't3_capacity', 't4_charge'
    o None si infactible.
    """
    if order_weight_kg > drone_spec.max_payload_kg:
        return None

    e_trip = estimate_trip_energy_wh(drone_spec, distance_km, order_weight_kg)
    usable_battery = drone_battery_wh * (1.0 - SAFETY_MARGIN)

    if e_trip > usable_battery:
        return None

    t1 = e_trip / drone_spec.battery_capacity_wh if drone_spec.battery_capacity_wh > 0 else 0.0

    e_sobrante_wh = drone_battery_wh - e_trip
    e_sobrante_pct = e_sobrante_wh / drone_spec.battery_capacity_wh if drone_spec.battery_capacity_wh > 0 else 0.0
    t2 = max(0.0, (BATTERY_LOW_THRESHOLD - e_sobrante_pct) / BATTERY_LOW_THRESHOLD) if BATTERY_LOW_THRESHOLD > 0 else 0.0

    t3 = (drone_spec.max_payload_kg - order_weight_kg) / drone_spec.max_payload_kg if drone_spec.max_payload_kg > 0 else 0.0

    energy_deficit = drone_spec.battery_capacity_wh * SAFETY_MARGIN - e_sobrante_wh
    if energy_deficit > 0:
        t_charge = estimate_charge_time_s(energy_deficit, charger_power_w)
        t4 = min(t_charge / _MAX_CHARGE_TIME_REF_S, 1.0)
    else:
        t4 = 0.0

    return {"t1_energy": t1, "t2_battery": t2, "t3_capacity": t3, "t4_charge": t4}


def build_cost_matrix(
    drone_specs: list[DroneSpec],
    drone_batteries_wh: list[float],
    order_weights_kg: list[float],
    distances_km: list[list[float]],
    weights: CostWeights,
    charger_power_w: float = 180.0,
) -> np.ndarray:
    """
    Construye la matriz de costes N_drones × M_pedidos.

    Parameters
    ----------
    drone_specs : list[DroneSpec]
        Especificaciones de cada dron (longitud N).
    drone_batteries_wh : list[float]
        Batería actual de cada dron (longitud N).
    order_weights_kg : list[float]
        Peso de cada pedido (longitud M).
    distances_km : list[list[float]]
        Matriz N×M de distancias drone→pedido en km.
    weights : CostWeights
        Pesos de la función de costes.
    charger_power_w : float
        Potencia del cargador (W).

    Returns
    -------
    np.ndarray
        Matriz N×M con costes. Entradas infactibles = 1e18 (no inf para scipy).
    """
    n_drones = len(drone_specs)
    m_orders = len(order_weights_kg)
    matrix = np.full((n_drones, m_orders), 1e18, dtype=np.float64)

    for i in range(n_drones):
        for j in range(m_orders):
            c = compute_cost(
                drone_specs[i],
                drone_batteries_wh[i],
                order_weights_kg[j],
                distances_km[i][j],
                weights,
                charger_power_w,
            )
            matrix[i, j] = c if not math.isinf(c) else 1e18

    return matrix

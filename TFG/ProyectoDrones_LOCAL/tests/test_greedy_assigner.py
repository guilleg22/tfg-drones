"""
Tests unitarios para greedy_assigner.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from simulacion.cost_function import CostWeights
from simulacion.energy_model import DroneSpec, DRONE_CATEGORIES
from simulacion.greedy_assigner import DroneState, Order, greedy_assign

DEFAULT_WEIGHTS = CostWeights(w1=1.0, w2=1.0, w3=1.0, w4=1.0)


def test_greedy_simple_case():
    """Un dron, un pedido, caso trivial."""
    drones = [DroneState(spec=DRONE_CATEGORIES["medio"], battery_wh=222.0)]
    orders = [Order(order_id=1, weight_kg=1.0, distance_km=1.0)]

    result = greedy_assign(drones, orders, DEFAULT_WEIGHTS)

    assert result.n_delivered == 1
    assert result.n_unassigned == 0
    assert len(result.assignments) == 1
    assert result.assignments[0].order_id == 1


def test_greedy_infeasible_weight():
    """El pedido es muy pesado para el dron, no se asigna."""
    drones = [DroneState(spec=DRONE_CATEGORIES["ligero"], battery_wh=148.0)]
    orders = [Order(order_id=1, weight_kg=3.0, distance_km=1.0)]

    result = greedy_assign(drones, orders, DEFAULT_WEIGHTS)

    assert result.n_delivered == 0
    assert result.n_unassigned == 1
    assert result.unassigned_orders == [1]


def test_greedy_fifo_order():
    """Verifica que procesa en orden de llegada (FIFO)."""
    # Dos pedidos pesados, solo hay un dron pesado.
    # El primero debe llevarse el dron pesado. El segundo debe quedar sin asignar.
    drones = [
        DroneState(spec=DRONE_CATEGORIES["ligero"], battery_wh=148.0),
        DroneState(spec=DRONE_CATEGORIES["pesado"], battery_wh=40.0),
    ]
    orders = [
        Order(order_id=1, weight_kg=3.5, distance_km=1.0),
        Order(order_id=2, weight_kg=3.5, distance_km=1.0),
    ]

    result = greedy_assign(drones, orders, DEFAULT_WEIGHTS)

    assert result.n_delivered == 1
    assert result.assignments[0].order_id == 1  # El primero se lo lleva
    assert result.assignments[0].drone_id == drones[1].spec.drone_id
    assert result.n_unassigned == 1
    assert result.unassigned_orders == [2]


def test_greedy_updates_battery():
    """Verifica que un dron agota su batería y no puede coger más."""
    # Dron ligero con poca batería. Debería poder hacer el primer pedido,
    # pero no el segundo.
    drones = [DroneState(spec=DRONE_CATEGORIES["ligero"], battery_wh=20.0)]
    orders = [
        Order(order_id=1, weight_kg=0.5, distance_km=1.0),
        Order(order_id=2, weight_kg=0.5, distance_km=1.0),
    ]

    result = greedy_assign(drones, orders, DEFAULT_WEIGHTS)

    assert result.n_delivered == 1
    assert result.assignments[0].order_id == 1
    assert result.n_unassigned == 1
    assert result.unassigned_orders == [2]

    # Verify battery in returned result vs drone state
    # Actually greedy_assign copies battery values and doesn't mutate input DroneState,
    # let's assert based on the result.
    assert result.total_energy_wh > 0

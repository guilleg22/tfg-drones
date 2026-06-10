"""
Tests unitarios para simulator.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from simulacion.cost_function import CostWeights
from simulacion.energy_model import DRONE_CATEGORIES
from simulacion.scenario_generator import DroneState, Order, Scenario
from simulacion.simulator import Simulator

DEFAULT_WEIGHTS = CostWeights(w1=1.0, w2=1.0, w3=1.0, w4=1.0)


def test_simulator_basic_run():
    """Test básico del simulador con ambos algoritmos."""
    drones = [
        DroneState(spec=DRONE_CATEGORIES["medio"], battery_wh=222.0),
        DroneState(spec=DRONE_CATEGORIES["ligero"], battery_wh=148.0),
    ]
    orders = [
        Order(order_id=1, weight_kg=1.0, client_lat=0, client_lon=0, destination_name="", distance_km=1.0),
        Order(order_id=2, weight_kg=0.5, client_lat=0, client_lon=0, destination_name="", distance_km=1.0),
    ]
    scenario = Scenario(scenario_id=1, drones=drones, orders=orders)

    sim = Simulator()

    # Probar greedy
    res_greedy = sim.run(scenario, "greedy", DEFAULT_WEIGHTS)
    assert res_greedy.n_delivered == 2
    assert res_greedy.n_unassigned == 0
    assert res_greedy.total_energy_wh > 0
    assert res_greedy.total_time_s > 0

    # Probar JV
    res_jv = sim.run(scenario, "cost_matrix", DEFAULT_WEIGHTS)
    assert res_jv.n_delivered == 2
    assert res_jv.n_unassigned == 0


def test_simulator_recharge():
    """El simulador debe recargar el dron si no puede hacer más pedidos."""
    # Dron ligero con muy poca batería. Deberá recargar para hacer el pedido.
    drones = [DroneState(spec=DRONE_CATEGORIES["ligero"], battery_wh=2.0)]
    orders = [Order(order_id=1, weight_kg=0.5, client_lat=0, client_lon=0, destination_name="", distance_km=1.0)]
    scenario = Scenario(scenario_id=1, drones=drones, orders=orders, charger_power_w=180.0)

    sim = Simulator()
    res = sim.run(scenario, "greedy", DEFAULT_WEIGHTS)

    assert res.n_delivered == 1
    assert res.total_charge_time_s > 0
    # La recarga suma al makespan
    assert res.total_time_s > res.total_charge_time_s

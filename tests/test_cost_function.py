"""
Tests unitarios para cost_function.py.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import numpy as np

from simulacion.cost_function import (
    CostWeights,
    compute_cost,
    compute_cost_components,
    build_cost_matrix,
)
from simulacion.energy_model import DroneSpec, DRONE_CATEGORIES


LIGERO = DRONE_CATEGORIES["ligero"]   # 1kg, 148Wh
MEDIO = DRONE_CATEGORIES["medio"]     # 2kg, 222Wh
PESADO = DRONE_CATEGORIES["pesado"]   # 4kg, 360Wh

DEFAULT_WEIGHTS = CostWeights(w1=1.0, w2=1.0, w3=1.0, w4=1.0)


class TestHardConstraints:
    """Tests de hard constraints (deben retornar inf)."""

    def test_weight_exceeds_payload(self):
        # Dron ligero (1kg max) con pedido de 2kg
        c = compute_cost(LIGERO, 148.0, 2.0, 1.0, DEFAULT_WEIGHTS)
        assert math.isinf(c)

    def test_energy_exceeds_battery(self):
        # Batería casi vacía, viaje largo
        c = compute_cost(MEDIO, 5.0, 3.0, 1.0, DEFAULT_WEIGHTS)
        assert math.isinf(c)

    def test_exact_payload_is_feasible(self):
        # Peso exacto = max_payload → debe ser factible
        c = compute_cost(LIGERO, 148.0, 1.0, 0.5, DEFAULT_WEIGHTS)
        assert not math.isinf(c)


class TestCostComponents:
    """Tests de los componentes individuales de coste."""

    def test_all_components_in_0_1(self):
        components = compute_cost_components(MEDIO, 222.0, 1.0, 1.0)
        assert components is not None
        for key, val in components.items():
            assert 0.0 <= val <= 1.0, f"{key}={val} fuera de [0,1]"

    def test_infeasible_returns_none(self):
        components = compute_cost_components(LIGERO, 148.0, 5.0, 1.0)
        assert components is None

    def test_t3_increases_with_excess_capacity(self):
        """Más exceso de capacidad → mayor t3."""
        c1 = compute_cost_components(PESADO, 360.0, 3.5, 1.0)  # casi lleno
        c2 = compute_cost_components(PESADO, 360.0, 0.5, 1.0)  # mucho exceso
        assert c1 is not None and c2 is not None
        assert c2["t3_capacity"] > c1["t3_capacity"]


class TestCostFunction:
    """Tests de compute_cost."""

    def test_cost_is_finite_for_feasible(self):
        c = compute_cost(MEDIO, 222.0, 1.0, 1.0, DEFAULT_WEIGHTS)
        assert not math.isinf(c)
        assert c >= 0

    def test_cost_increases_with_distance(self):
        c1 = compute_cost(MEDIO, 222.0, 1.0, 0.5, DEFAULT_WEIGHTS)
        c2 = compute_cost(MEDIO, 222.0, 1.0, 2.0, DEFAULT_WEIGHTS)
        assert c2 > c1

    def test_weights_affect_cost(self):
        """Pesos distintos dan costes distintos."""
        w1 = CostWeights(w1=10.0, w2=0.0, w3=0.0, w4=0.0)
        w3 = CostWeights(w1=0.0, w2=0.0, w3=10.0, w4=0.0)
        c1 = compute_cost(MEDIO, 222.0, 1.0, 1.0, w1)
        c3 = compute_cost(MEDIO, 222.0, 1.0, 1.0, w3)
        assert c1 != c3


class TestCostWeights:
    """Tests de la dataclass CostWeights."""

    def test_normalized(self):
        w = CostWeights(2.0, 3.0, 4.0, 1.0)
        n = w.normalized()
        assert abs(n.w1 + n.w2 + n.w3 + n.w4 - 1.0) < 1e-9

    def test_from_array(self):
        w = CostWeights.from_array([0.1, 0.2, 0.3, 0.4])
        assert w.w1 == 0.1
        assert w.w4 == 0.4

    def test_as_array(self):
        w = CostWeights(1.0, 2.0, 3.0, 4.0)
        arr = w.as_array()
        assert len(arr) == 5
        assert arr[0] == 1.0


class TestCostMatrix:
    """Tests de build_cost_matrix."""

    def test_matrix_shape(self):
        specs = [LIGERO, MEDIO]
        batteries = [148.0, 222.0]
        weights_kg = [0.5, 1.0, 2.0]
        distances = [[1.0, 1.0, 1.0], [1.0, 1.0, 1.0]]
        mat = build_cost_matrix(specs, batteries, weights_kg, distances, DEFAULT_WEIGHTS)
        assert mat.shape == (2, 3)

    def test_infeasible_cells_are_large(self):
        specs = [LIGERO]  # max 1kg
        batteries = [148.0]
        weights_kg = [5.0]  # demasiado pesado
        distances = [[1.0]]
        mat = build_cost_matrix(specs, batteries, weights_kg, distances, DEFAULT_WEIGHTS)
        assert mat[0, 0] >= 1e17

    def test_feasible_cells_are_finite(self):
        specs = [MEDIO]
        batteries = [222.0]
        weights_kg = [1.0]
        distances = [[0.5]]
        mat = build_cost_matrix(specs, batteries, weights_kg, distances, DEFAULT_WEIGHTS)
        assert mat[0, 0] < 1e17

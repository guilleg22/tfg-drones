"""
Tests unitarios para energy_model.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from simulacion.energy_model import (
    DroneSpec,
    DRONE_CATEGORIES,
    estimate_energy_wh,
    estimate_trip_energy_wh,
    estimate_duration_s,
    is_feasible,
    estimate_charge_time_s,
)


# ── Spec de prueba (dron medio) ──────────────────────────────────────────────

MEDIO = DRONE_CATEGORIES["medio"]
# base_consumption_w=180, payload_factor=22, speed=7, battery=222, payload_max=2


class TestEstimateEnergy:
    """Tests de estimate_energy_wh."""

    def test_zero_distance_gives_zero(self):
        assert estimate_energy_wh(MEDIO, 0.0, 1.0) == 0.0

    def test_positive_distance_gives_positive(self):
        e = estimate_energy_wh(MEDIO, 1.0, 0.5)
        assert e > 0

    def test_energy_increases_with_distance(self):
        e1 = estimate_energy_wh(MEDIO, 1.0, 1.0)
        e2 = estimate_energy_wh(MEDIO, 2.0, 1.0)
        assert e2 > e1

    def test_energy_increases_with_weight(self):
        e1 = estimate_energy_wh(MEDIO, 1.0, 0.5)
        e2 = estimate_energy_wh(MEDIO, 1.0, 2.0)
        assert e2 > e1

    def test_no_weight_uses_base_only(self):
        e = estimate_energy_wh(MEDIO, 1.0, 0.0)
        # E = P_base × t = 180 × (1000/7/3600) = 180 × 0.03968 = 7.143 Wh
        expected = 180.0 * (1000.0 / 7.0 / 3600.0)
        assert abs(e - expected) < 0.01

    def test_known_value(self):
        """Caso calculado a mano: 1km, 1kg, dron medio."""
        # P = 180 + 22*1 = 202 W
        # t = 1000/7/3600 = 0.03968 h
        # E = 202 * 0.03968 = 8.016 Wh
        e = estimate_energy_wh(MEDIO, 1.0, 1.0)
        assert abs(e - 8.016) < 0.1


class TestTripEnergy:
    """Tests de estimate_trip_energy_wh."""

    def test_trip_greater_than_one_way(self):
        e_one = estimate_energy_wh(MEDIO, 1.0, 1.0)
        e_trip = estimate_trip_energy_wh(MEDIO, 1.0, 1.0)
        assert e_trip > e_one

    def test_trip_equals_ida_plus_vuelta(self):
        e_ida = estimate_energy_wh(MEDIO, 2.0, 1.5)
        e_vuelta = estimate_energy_wh(MEDIO, 2.0, 0.0)
        e_trip = estimate_trip_energy_wh(MEDIO, 2.0, 1.5)
        assert abs(e_trip - (e_ida + e_vuelta)) < 0.001

    def test_vuelta_less_than_ida(self):
        """La vuelta sin carga consume menos que la ida con carga."""
        e_ida = estimate_energy_wh(MEDIO, 1.0, 2.0)
        e_vuelta = estimate_energy_wh(MEDIO, 1.0, 0.0)
        assert e_vuelta < e_ida


class TestDuration:
    """Tests de estimate_duration_s."""

    def test_zero_distance(self):
        assert estimate_duration_s(0.0, 7.0) == 0.0

    def test_known_value(self):
        # 1km ida+vuelta = 2000m / 7 m/s = 285.71 s
        t = estimate_duration_s(1.0, 7.0)
        assert abs(t - 285.71) < 1.0

    def test_duration_increases_with_distance(self):
        t1 = estimate_duration_s(1.0, 7.0)
        t2 = estimate_duration_s(3.0, 7.0)
        assert t2 > t1


class TestFeasibility:
    """Tests de is_feasible."""

    def test_feasible_case(self):
        # Batería al 100% = 222 Wh, viaje corto
        assert is_feasible(MEDIO, 222.0, 0.5, 0.5) is True

    def test_infeasible_weight(self):
        # Peso excede capacidad
        assert is_feasible(MEDIO, 222.0, 0.5, 3.0) is False

    def test_infeasible_energy(self):
        # Viaje muy largo con batería baja
        assert is_feasible(MEDIO, 10.0, 5.0, 1.0) is False

    def test_safety_margin(self):
        # Con 20% de margen, solo puede usar 80% de la batería
        e_trip = estimate_trip_energy_wh(MEDIO, 1.0, 1.0)
        # Batería justo al límite: e_trip / 0.8
        limit_battery = e_trip / 0.8
        assert is_feasible(MEDIO, limit_battery, 1.0, 1.0) is True
        assert is_feasible(MEDIO, limit_battery * 0.99, 1.0, 1.0) is False


class TestChargeTime:
    """Tests de estimate_charge_time_s."""

    def test_no_deficit(self):
        assert estimate_charge_time_s(0.0, 180.0) == 0.0

    def test_known_value(self):
        # 100 Wh a 180W = 100/180 h = 0.5556 h = 2000 s
        t = estimate_charge_time_s(100.0, 180.0)
        assert abs(t - 2000.0) < 1.0

    def test_full_charge(self):
        # 222 Wh a 180W = 1.2333 h = 4440 s
        t = estimate_charge_time_s(222.0, 180.0)
        assert abs(t - 4440.0) < 1.0

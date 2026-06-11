"""
run_parameter_study.py — Estudio comparativo de optimización de parámetros.

Para cada ARQUETIPO de escenario (urbano pequeño, día operativo, operación
masiva, perfil e-commerce y perfil industrial) ejecuta:

  1. Baseline con pesos neutros w=[1,1,1,1] sobre un conjunto de test held-out.
  2. Optimización Monte Carlo (LHS) de los pesos.
  3. Optimización con Algoritmo Genético de los pesos.
     → Ambos optimizan la MISMA función objetivo normalizada (simulacion.objective)
       y comparten el baseline, por lo que son directamente comparables.
  4. Evaluación de los tres conjuntos de pesos (Neutros, MC, GA) sobre el test,
     con tests estadísticos t pareados frente al baseline.
  5. Comparación Greedy vs Jonker-Volgenant con los pesos del GA.
  6. Análisis de sensibilidad de la función de costes (efecto de cada término).
  7. Figuras profesionales + un JSON con todos los resultados para el informe.

El asignador de la matriz de costes sigue siendo
scipy.optimize.linear_sum_assignment (Jonker-Volgenant), intacto.

Uso:
  python scripts/run_parameter_study.py            # ejecución completa
  python scripts/run_parameter_study.py --quick    # presupuestos reducidos
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy import stats

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from simulacion.cost_function import CostWeights, build_cost_matrix
from simulacion.objective import compute_baseline, NEUTRAL_WEIGHTS
from simulacion.optimizer_montecarlo import optimize_montecarlo
from simulacion.optimizer_genetic import optimize_genetic
from simulacion.scenario_generator import generate_batch
from simulacion.simulator import Simulator
from simulacion.metrics import compute_comparison
from simulacion.visualization import (
    plot_optimizer_comparison,
    plot_weights_comparison,
    plot_method_test_comparison,
    plot_weight_sensitivity,
    plot_comparison_bars,
    plot_comparison_boxplots,
    plot_cost_heatmap,
    TERM_LABELS,
)


# ── Definición de arquetipos ─────────────────────────────────────────────────

def build_archetypes(quick: bool) -> list[dict]:
    """
    Devuelve la lista de arquetipos. `quick` reduce los presupuestos para
    una ejecución rápida de prueba.
    """
    # Presupuestos de optimización (trials MC / pop×gen GA)
    if quick:
        small = dict(mc_trials=120, ga_pop=16, ga_gen=12)
        big = dict(mc_trials=60, ga_pop=12, ga_gen=8)
    else:
        small = dict(mc_trials=400, ga_pop=30, ga_gen=25)
        big = dict(mc_trials=150, ga_pop=20, ga_gen=15)

    return [
        {
            "key": "urban_small",
            "name": "Urbano pequeño (base Castelldefels)",
            "description": (
                "Flota base de 5 drones (2 ligeros, 2 medios, 1 pesado) atendiendo "
                "30 pedidos repartidos sobre los destinos reales de Castelldefels. "
                "Es el escenario canónico del proyecto."
            ),
            "n_drones": 5, "n_orders": 30, "charger_w": 180.0,
            "weight_min": 0.3, "weight_max": 4.0,
            "n_train": 8, "n_test": 30, "seed_train": 42, "seed_test": 100,
            "make_heatmap": True,
            **small,
        },
        {
            "key": "ecommerce_light",
            "name": "Perfil e-commerce (paquetería ligera)",
            "description": (
                "Mismo tamaño de flota pero pedidos ligeros (0.1–1.5 kg), típicos "
                "de comercio electrónico. Aquí muchos drones ligeros son viables, "
                "lo que da más libertad al optimizador."
            ),
            "n_drones": 5, "n_orders": 40, "charger_w": 180.0,
            "weight_min": 0.1, "weight_max": 1.5,
            "n_train": 8, "n_test": 30, "seed_train": 11, "seed_test": 111,
            "make_heatmap": False,
            **small,
        },
        {
            "key": "industrial_heavy",
            "name": "Perfil industrial (carga pesada)",
            "description": (
                "Pedidos pesados (1.5–4.0 kg) que solo pueden servir los drones "
                "medios y pesados. El problema está muy restringido por la carga "
                "útil, lo que reduce el margen de la optimización."
            ),
            "n_drones": 5, "n_orders": 40, "charger_w": 180.0,
            "weight_min": 1.5, "weight_max": 4.0,
            "n_train": 8, "n_test": 30, "seed_train": 22, "seed_test": 222,
            "make_heatmap": False,
            **small,
        },
        {
            "key": "operational_day",
            "name": "Día operativo (10 drones, 150 pedidos)",
            "description": (
                "Jornada completa con 10 drones y 150 pedidos (≈15 por dron). "
                "Aparecen múltiples rondas de recarga, donde el reparto de carga "
                "entre drones (y por tanto los pesos) influye en el makespan."
            ),
            "n_drones": 10, "n_orders": 150, "charger_w": 300.0,
            "weight_min": 0.3, "weight_max": 4.0,
            "n_train": 5, "n_test": 12, "seed_train": 200, "seed_test": 300,
            "make_heatmap": False,
            **big,
        },
        {
            "key": "massive_ops",
            "name": "Operación masiva (25 drones, 600 pedidos)",
            "description": (
                "Escenario de gran escala con 25 drones y 600 pedidos. Pone a "
                "prueba la robustez del método de optimización cuando el coste de "
                "cada evaluación es alto."
            ),
            "n_drones": 25, "n_orders": 600, "charger_w": 300.0,
            "weight_min": 0.3, "weight_max": 4.0,
            "n_train": 3, "n_test": 8, "seed_train": 500, "seed_test": 700,
            "make_heatmap": False,
            **big,
        },
    ]


# ── Utilidades de evaluación ─────────────────────────────────────────────────

def evaluate_weights_on_test(sim: Simulator, scenarios, weights: CostWeights):
    """Devuelve arrays por escenario de makespan y energía con JV."""
    results = sim.run_batch(scenarios, "cost_matrix", weights)
    times = [r.total_time_s for r in results]
    energies = [r.total_energy_wh for r in results]
    return np.array(times), np.array(energies)


def paired_pvalue(baseline_arr, method_arr):
    """t-test pareado; devuelve p-value (1.0 si no hay variación)."""
    diff = np.array(baseline_arr) - np.array(method_arr)
    if np.allclose(diff, 0):
        return 1.0
    try:
        _, p = stats.ttest_rel(baseline_arr, method_arr)
        return float(p)
    except Exception:
        return 1.0


def run_sensitivity(sim: Simulator, scenarios) -> dict:
    """Evalúa configuraciones de un solo término [1,0,0,0], [0,1,0,0]..."""
    times, energies = [], []
    single = [
        CostWeights(1, 0, 0, 0),
        CostWeights(0, 1, 0, 0),
        CostWeights(0, 0, 1, 0),
        CostWeights(0, 0, 0, 1),
    ]
    for w in single:
        t_arr, e_arr = evaluate_weights_on_test(sim, scenarios, w)
        times.append(float(np.mean(t_arr)))
        energies.append(float(np.mean(e_arr)))
    return {"labels": TERM_LABELS, "times": times, "energies": energies}


# ── Procesado de un arquetipo ────────────────────────────────────────────────

def process_archetype(arch: dict, objective: str, out_root: Path) -> dict:
    print("\n" + "=" * 70)
    print(f"ARQUETIPO: {arch['name']}")
    print("=" * 70)

    out_dir = out_root / arch["key"]
    out_dir.mkdir(parents=True, exist_ok=True)

    charger_w = arch["charger_w"]
    sim = Simulator(charger_power_w=charger_w)

    # 1. Escenarios train/test
    print(f"  Generando {arch['n_train']} escenarios de entrenamiento y "
          f"{arch['n_test']} de test...")
    train = generate_batch(
        arch["n_train"], arch["n_drones"], arch["n_orders"],
        seed=arch["seed_train"], charger_power_w=charger_w,
        weight_min_kg=arch["weight_min"], weight_max_kg=arch["weight_max"],
    )
    test = generate_batch(
        arch["n_test"], arch["n_drones"], arch["n_orders"],
        seed=arch["seed_test"], charger_power_w=charger_w,
        weight_min_kg=arch["weight_min"], weight_max_kg=arch["weight_max"],
    )

    # 2. Baseline (pesos neutros) sobre TRAIN — compartido por MC y GA
    baseline = compute_baseline(sim, train)
    print(f"  Baseline (neutros) train → tiempo={baseline.time:.1f}s, "
          f"energía={baseline.energy:.1f}Wh")

    # 3. Optimización Monte Carlo
    print(f"  Monte Carlo: {arch['mc_trials']} trials...")
    t0 = time.time()
    mc = optimize_montecarlo(
        train, n_trials=arch["mc_trials"], objective=objective, seed=42,
        charger_power_w=charger_w, verbose=False, baseline=baseline,
    )
    t_mc = time.time() - t0
    print(f"    ✓ {t_mc:.1f}s | obj={mc.best_objective:.4f} | "
          f"evals={mc.n_evaluations} | Δt={mc.time_improvement_pct:+.2f}%")

    # 4. Optimización Genética
    print(f"  Algoritmo Genético: pop={arch['ga_pop']} × gen={arch['ga_gen']}...")
    t0 = time.time()
    ga = optimize_genetic(
        train, pop_size=arch["ga_pop"], n_generations=arch["ga_gen"],
        objective=objective, seed=42, charger_power_w=charger_w,
        verbose=False, baseline=baseline,
    )
    t_ga = time.time() - t0
    print(f"    ✓ {t_ga:.1f}s | obj={ga.best_objective:.4f} | "
          f"evals={ga.n_evaluations} | Δt={ga.time_improvement_pct:+.2f}%")

    winner = "GA" if ga.best_objective <= mc.best_objective else "MC"
    print(f"  → Mejor en entrenamiento: {winner}")

    # 5. Evaluación en TEST de los tres conjuntos de pesos
    methods = {
        "Neutros": NEUTRAL_WEIGHTS,
        "Monte Carlo": mc.best_weights,
        "Genético": ga.best_weights,
    }
    test_times, test_energies = {}, {}
    for name, w in methods.items():
        t_arr, e_arr = evaluate_weights_on_test(sim, test, w)
        test_times[name] = t_arr
        test_energies[name] = e_arr

    base_t = test_times["Neutros"]
    base_e = test_energies["Neutros"]
    test_block = {
        "methods": list(methods.keys()),
        "weights": {n: [w.w1, w.w2, w.w3, w.w4] for n, w in methods.items()},
        "time_mean": {n: float(np.mean(v)) for n, v in test_times.items()},
        "time_std": {n: float(np.std(v)) for n, v in test_times.items()},
        "energy_mean": {n: float(np.mean(v)) for n, v in test_energies.items()},
        "energy_std": {n: float(np.std(v)) for n, v in test_energies.items()},
        "time_impr_pct": {
            n: float((np.mean(base_t) - np.mean(v)) / np.mean(base_t) * 100)
            for n, v in test_times.items()
        },
        "energy_impr_pct": {
            n: float((np.mean(base_e) - np.mean(v)) / np.mean(base_e) * 100)
            for n, v in test_energies.items()
        },
        "p_value_time": {
            n: paired_pvalue(base_t, v) for n, v in test_times.items()
        },
    }
    print(f"  TEST  makespan: Neutros={test_block['time_mean']['Neutros']:.1f}s | "
          f"MC={test_block['time_impr_pct']['Monte Carlo']:+.2f}% | "
          f"GA={test_block['time_impr_pct']['Genético']:+.2f}% "
          f"(p_GA={test_block['p_value_time']['Genético']:.4f})")

    # 6. Greedy vs JV con los pesos del GA (punto de operación elegido)
    op_weights = ga.best_weights
    greedy_results = sim.run_batch(test, "greedy", op_weights)
    jv_results = sim.run_batch(test, "cost_matrix", op_weights)
    gvj = compute_comparison(greedy_results, jv_results)

    # 7. Sensibilidad sobre el test
    sens = run_sensitivity(sim, test)

    # ── Figuras ──
    print("  Generando figuras...")
    figs = {}

    plot_optimizer_comparison(
        mc.eval_curve, mc.convergence_curve,
        ga.eval_curve, ga.convergence_curve,
        objective_label=objective,
        output_path=out_dir / "convergence_mc_vs_ga.png",
        title=f"Convergencia MC vs GA — {arch['name']}",
    )
    figs["convergence"] = str((out_dir / "convergence_mc_vs_ga.png").relative_to(_ROOT))

    plot_weights_comparison(
        {n: [w.w1, w.w2, w.w3, w.w4] for n, w in methods.items()},
        output_path=out_dir / "weights_comparison.png",
        title=f"Pesos hallados — {arch['name']}",
    )
    figs["weights"] = str((out_dir / "weights_comparison.png").relative_to(_ROOT))

    plot_method_test_comparison(
        list(methods.keys()),
        [test_times[n] for n in methods],
        [test_energies[n] for n in methods],
        output_path=out_dir / "test_comparison.png",
        title=f"Rendimiento en test — {arch['name']}",
    )
    figs["test_comparison"] = str((out_dir / "test_comparison.png").relative_to(_ROOT))

    plot_weight_sensitivity(
        sens["labels"], sens["times"], sens["energies"],
        baseline_time=test_block["time_mean"]["Neutros"],
        baseline_energy=test_block["energy_mean"]["Neutros"],
        output_path=out_dir / "sensitivity.png",
        title=f"Sensibilidad de la función de costes — {arch['name']}",
    )
    figs["sensitivity"] = str((out_dir / "sensitivity.png").relative_to(_ROOT))

    plot_comparison_bars(gvj, out_dir / "greedy_vs_jv_bars.png")
    figs["greedy_vs_jv_bars"] = str((out_dir / "greedy_vs_jv_bars.png").relative_to(_ROOT))

    plot_comparison_boxplots(gvj, out_dir / "greedy_vs_jv_boxplots.png")
    figs["greedy_vs_jv_boxplots"] = str((out_dir / "greedy_vs_jv_boxplots.png").relative_to(_ROOT))

    if arch.get("make_heatmap"):
        sc = test[0]
        specs = [d.spec for d in sc.drones]
        bats = [d.battery_wh for d in sc.drones]
        ow = [o.weight_kg for o in sc.orders[:10]]
        dist = [[o.distance_km for o in sc.orders[:10]] for _ in specs]
        cm = build_cost_matrix(specs, bats, ow, dist, op_weights, charger_w)
        dlabels = [f"{d.spec.drone_id}\n({d.spec.max_payload_kg}kg)" for d in sc.drones]
        olabels = [f"P{o.order_id}\n{o.weight_kg}kg" for o in sc.orders[:10]]
        plot_cost_heatmap(cm, dlabels, olabels, out_dir / "cost_heatmap.png")
        figs["cost_heatmap"] = str((out_dir / "cost_heatmap.png").relative_to(_ROOT))

    # ── Resultado del arquetipo ──
    return {
        "key": arch["key"],
        "name": arch["name"],
        "description": arch["description"],
        "config": {
            "n_drones": arch["n_drones"], "n_orders": arch["n_orders"],
            "charger_w": charger_w,
            "weight_min": arch["weight_min"], "weight_max": arch["weight_max"],
            "n_train": arch["n_train"], "n_test": arch["n_test"],
            "mc_trials": arch["mc_trials"],
            "ga_pop": arch["ga_pop"], "ga_gen": arch["ga_gen"],
        },
        "baseline": {"time": baseline.time, "energy": baseline.energy,
                     "delivered": baseline.delivered},
        "mc": {
            "weights": [mc.best_weights.w1, mc.best_weights.w2,
                        mc.best_weights.w3, mc.best_weights.w4],
            "best_objective": mc.best_objective,
            "n_evaluations": mc.n_evaluations,
            "time_improvement_pct": mc.time_improvement_pct,
            "energy_improvement_pct": mc.energy_improvement_pct,
            "elapsed_s": t_mc,
        },
        "ga": {
            "weights": [ga.best_weights.w1, ga.best_weights.w2,
                        ga.best_weights.w3, ga.best_weights.w4],
            "best_objective": ga.best_objective,
            "n_evaluations": ga.n_evaluations,
            "time_improvement_pct": ga.time_improvement_pct,
            "energy_improvement_pct": ga.energy_improvement_pct,
            "elapsed_s": t_ga,
        },
        "winner_train": winner,
        "test": test_block,
        "greedy_vs_jv": {
            "energy_saving_pct": gvj.energy_saving_pct,
            "time_saving_pct": gvj.time_saving_pct,
            "p_value_energy": gvj.p_value_energy,
            "p_value_time": gvj.p_value_time,
            "avg_greedy_time": gvj.avg_greedy_time,
            "avg_jv_time": gvj.avg_jv_time,
        },
        "sensitivity": sens,
        "figures": figs,
    }


def main():
    parser = argparse.ArgumentParser(description="Estudio de optimización de parámetros")
    parser.add_argument("--quick", action="store_true", help="Presupuestos reducidos")
    parser.add_argument("--objective", default="time",
                        choices=["time", "energy", "combined"])
    parser.add_argument("--only", default=None,
                        help="Procesar solo un arquetipo por su key")
    args = parser.parse_args()

    out_root = _ROOT / "results" / "parameter_study"
    out_root.mkdir(parents=True, exist_ok=True)

    archetypes = build_archetypes(args.quick)
    if args.only:
        archetypes = [a for a in archetypes if a["key"] == args.only]

    print("=" * 70)
    print("ESTUDIO DE OPTIMIZACIÓN DE PARÁMETROS DE LA FUNCIÓN DE COSTES")
    print(f"Objetivo: {args.objective} | Arquetipos: {len(archetypes)} | "
          f"{'QUICK' if args.quick else 'COMPLETO'}")
    print("=" * 70)

    t_start = time.time()
    results = []
    for arch in archetypes:
        results.append(process_archetype(arch, args.objective, out_root))

    summary = {
        "objective": args.objective,
        "quick": args.quick,
        "elapsed_s": time.time() - t_start,
        "archetypes": results,
    }
    (out_root / "study_results.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n" + "=" * 70)
    print(f"✅ Estudio completado en {summary['elapsed_s']:.1f}s")
    print(f"   Resultados: {out_root / 'study_results.json'}")
    print("=" * 70)


if __name__ == "__main__":
    main()

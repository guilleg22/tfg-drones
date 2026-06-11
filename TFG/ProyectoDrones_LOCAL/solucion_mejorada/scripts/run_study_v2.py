"""
run_study_v2.py — Estudio de la solución MEJORADA y comparación con la base.

Para cada arquetipo de escenario:
  1. Mide el makespan de la solución BASE (recarga al 100%, pesos neutros).
  2. Aplica las mejoras de forma acumulada y mide su efecto:
       a) recarga parcial adaptativa,
       b) + pesos optimizados (5 pesos, incluye w5 de balanceo de carga).
  3. Compara TRES métodos de tuning bajo el mismo presupuesto:
       Monte Carlo, Algoritmo Genético y Optimización Bayesiana.
  4. Mantiene scipy.optimize.linear_sum_assignment como asignador.
  5. Genera figuras profesionales + un JSON con todos los resultados.

Además, añade una comparación global frente a un baseline EXACTO (MILP/PuLP)
para cuantificar el gap de optimalidad del heurístico JV.

Uso:
  python scripts/run_study_v2.py            # completo
  python scripts/run_study_v2.py --quick    # presupuestos reducidos
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

_ROOT = Path(__file__).resolve().parent.parent      # solucion_mejorada/
sys.path.insert(0, str(_ROOT))

from sim2.cost_function import CostWeights
from sim2.objective import compute_baseline, NEUTRAL_WEIGHTS
from sim2.optimizer_montecarlo import optimize_montecarlo
from sim2.optimizer_genetic import optimize_genetic
from sim2.optimizer_bayes import optimize_bayes
from sim2.scenario_generator import generate_batch, generate_scenario
from sim2.simulator import Simulator
from sim2.metrics import compute_comparison
from sim2.milp_baseline import solve_min_makespan_single_cycle
from sim2.cost_matrix_assigner import cost_matrix_assign
from sim2.greedy_assigner import DroneState, Order
from sim2.visualization import plot_comparison_bars
from sim2 import viz_v2


def build_archetypes(quick: bool) -> list[dict]:
    if quick:
        s = dict(mc=100, ga_pop=14, ga_gen=8, bayes=40, bayes_init=12)
        b = dict(mc=50, ga_pop=10, ga_gen=6, bayes=25, bayes_init=10)
    else:
        s = dict(mc=200, ga_pop=24, ga_gen=16, bayes=70, bayes_init=16)
        b = dict(mc=90, ga_pop=16, ga_gen=10, bayes=40, bayes_init=12)
    return [
        dict(key="urban_small", name="Urbano pequeño (base Castelldefels)",
             description="Flota de 5 drones (2L+2M+1P) y 30 pedidos sobre los "
             "destinos reales de Castelldefels. Escenario canónico del proyecto.",
             n_drones=5, n_orders=30, charger_w=180.0, wmin=0.3, wmax=4.0,
             n_train=8, n_test=40, seed_train=42, seed_test=100, **s),
        dict(key="ecommerce_light", name="Perfil e-commerce (paquetería ligera)",
             description="Pedidos ligeros (0.1–1.5 kg); muchos drones ligeros son "
             "viables, lo que da más libertad al optimizador.",
             n_drones=5, n_orders=40, charger_w=180.0, wmin=0.1, wmax=1.5,
             n_train=8, n_test=40, seed_train=11, seed_test=111, **s),
        dict(key="industrial_heavy", name="Perfil industrial (carga pesada)",
             description="Pedidos pesados (1.5–4.0 kg) que solo sirven medios y "
             "pesados; problema muy restringido por carga útil.",
             n_drones=5, n_orders=40, charger_w=180.0, wmin=1.5, wmax=4.0,
             n_train=8, n_test=40, seed_train=22, seed_test=222, **s),
        dict(key="operational_day", name="Día operativo (10 drones, 150 pedidos)",
             description="Jornada con 10 drones y 150 pedidos (~15/dron); múltiples "
             "ciclos de recarga donde el reparto de carga influye en el makespan.",
             n_drones=10, n_orders=150, charger_w=300.0, wmin=0.3, wmax=4.0,
             n_train=5, n_test=14, seed_train=200, seed_test=300, **b),
        dict(key="massive_ops", name="Operación masiva (25 drones, 600 pedidos)",
             description="Gran escala: 25 drones y 600 pedidos. Prueba la robustez "
             "cuando cada evaluación es costosa.",
             n_drones=25, n_orders=600, charger_w=300.0, wmin=0.3, wmax=4.0,
             n_train=3, n_test=8, seed_train=500, seed_test=700, **b),
    ]


def eval_test(sim, scenarios, weights):
    res = sim.run_batch(scenarios, "cost_matrix", weights)
    return (np.array([r.total_time_s for r in res]),
            np.array([r.total_energy_wh for r in res]),
            np.array([r.n_delivered for r in res]))


def paired_p(a, b):
    d = np.asarray(a) - np.asarray(b)
    if np.allclose(d, 0):
        return 1.0
    try:
        return float(stats.ttest_rel(a, b)[1])
    except Exception:
        return 1.0


def process(arch, objective, out_root):
    print("\n" + "=" * 70)
    print(f"ARQUETIPO: {arch['name']}")
    print("=" * 70)
    out_dir = out_root / arch["key"]
    out_dir.mkdir(parents=True, exist_ok=True)
    cw = arch["charger_w"]

    base_sim = Simulator(cw, partial_recharge=False)   # solución base
    imp_sim = Simulator(cw, partial_recharge=True)     # solución mejorada

    train = generate_batch(arch["n_train"], arch["n_drones"], arch["n_orders"],
                           seed=arch["seed_train"], charger_power_w=cw,
                           weight_min_kg=arch["wmin"], weight_max_kg=arch["wmax"])
    test = generate_batch(arch["n_test"], arch["n_drones"], arch["n_orders"],
                          seed=arch["seed_test"], charger_power_w=cw,
                          weight_min_kg=arch["wmin"], weight_max_kg=arch["wmax"])

    baseline = compute_baseline(imp_sim, train)   # baseline mejorado (parcial)
    print(f"  Baseline parcial train → makespan={baseline.time:.0f}s "
          f"(P90={baseline.time_p90:.0f}s)")

    # ── 3 tuners (sobre simulador mejorado, mismo objetivo y baseline) ──
    print(f"  Tuning (obj={objective})...")
    t0 = time.time()
    mc = optimize_montecarlo(train, n_trials=arch["mc"], objective=objective,
                             seed=42, charger_power_w=cw, verbose=False, baseline=baseline)
    ga = optimize_genetic(train, pop_size=arch["ga_pop"], n_generations=arch["ga_gen"],
                          objective=objective, seed=42, charger_power_w=cw,
                          verbose=False, baseline=baseline)
    by = optimize_bayes(train, n_calls=arch["bayes"], n_initial_points=arch["bayes_init"],
                        objective=objective, seed=42, charger_power_w=cw,
                        verbose=False, baseline=baseline)
    print(f"    MC obj={mc.best_objective:.4f}(ev{mc.n_evaluations}) | "
          f"GA obj={ga.best_objective:.4f}(ev{ga.n_evaluations}) | "
          f"Bayes obj={by.best_objective:.4f}(ev{by.n_evaluations}) | {time.time()-t0:.1f}s")

    tuners = {"Monte Carlo": mc, "Genético": ga, "Bayesiano": by}
    best_name = min(tuners, key=lambda k: tuners[k].best_objective)
    best_w = tuners[best_name].best_weights
    print(f"    Mejor tuner (train): {best_name}")

    # ── Evaluación en test: etapas acumuladas ──
    t_base, e_base, d_base = eval_test(base_sim, test, CostWeights(1, 1, 1, 1, 0))     # base full+4w
    t_par, e_par, d_par = eval_test(imp_sim, test, NEUTRAL_WEIGHTS)                    # parcial+neutros
    t_best, e_best, d_best = eval_test(imp_sim, test, best_w)                          # parcial+tuned

    stages = ["Base\n(100%, neutros)", "Recarga parcial\n(neutros)",
              f"Parcial + pesos\n({best_name})"]
    times_stage = [t_base, t_par, t_best]
    viz_v2.plot_base_vs_improved(stages, times_stage,
                                 out_dir / "base_vs_improved.png",
                                 title=f"Makespan base vs mejoras — {arch['name']}")

    # Convergencia 3 tuners
    viz_v2.plot_convergence_multi(
        {"Monte Carlo": (mc.eval_curve, mc.convergence_curve),
         "Genético": (ga.eval_curve, ga.convergence_curve),
         "Bayesiano": (by.eval_curve, by.convergence_curve)},
        objective, out_dir / "convergence_3tuners.png",
        title=f"Convergencia de los 3 tuners — {arch['name']}")

    # Pesos (5) por método
    viz_v2.plot_weights5(
        {"Neutros": [0.2] * 5,
         "Monte Carlo": list(mc.best_weights.as_array()),
         "Genético": list(ga.best_weights.as_array()),
         "Bayesiano": list(by.best_weights.as_array())},
        out_dir / "weights5.png", title=f"Pesos hallados — {arch['name']}")

    # Mejora pareada en test de cada tuner vs neutros (sobre simulador mejorado)
    t_mc, _, _ = eval_test(imp_sim, test, mc.best_weights)
    t_ga, _, _ = eval_test(imp_sim, test, ga.best_weights)
    t_by, _, _ = eval_test(imp_sim, test, by.best_weights)
    viz_v2.plot_test_improvement(
        ["Monte Carlo", "Genético", "Bayesiano"], t_par, [t_mc, t_ga, t_by],
        out_dir / "test_improvement.png",
        ylabel="Mejora del makespan vs neutros (%)",
        title=f"Aporte del tuning sobre recarga parcial — {arch['name']}")

    # Greedy vs JV (simulador mejorado, mejores pesos)
    gvj = compute_comparison(imp_sim.run_batch(test, "greedy", best_w),
                             imp_sim.run_batch(test, "cost_matrix", best_w))
    plot_comparison_bars(gvj, out_dir / "greedy_vs_jv.png")

    def impr(a, b):
        return float((np.mean(a) - np.mean(b)) / np.mean(a) * 100)

    return {
        "key": arch["key"], "name": arch["name"], "description": arch["description"],
        "config": {k: arch[k] for k in ("n_drones", "n_orders", "charger_w", "wmin",
                                         "wmax", "n_train", "n_test", "mc", "ga_pop",
                                         "ga_gen", "bayes")},
        "objective": objective,
        "baseline_full_makespan": float(np.mean(t_base)),
        "baseline_partial_makespan": float(np.mean(t_par)),
        "best_tuner": best_name,
        "best_weights": list(best_w.as_array()),
        "stages": {
            "labels": ["Base (100%)", "Recarga parcial", f"Parcial + {best_name}"],
            "makespan_mean": [float(np.mean(t_base)), float(np.mean(t_par)), float(np.mean(t_best))],
            "delivered_mean": [float(np.mean(d_base)), float(np.mean(d_par)), float(np.mean(d_best))],
        },
        "improvement_recharge_pct": impr(t_base, t_par),
        "improvement_total_pct": impr(t_base, t_best),
        "improvement_tuning_pct": impr(t_par, t_best),
        "p_value_recharge": paired_p(t_base, t_par),
        "tuners": {
            name: {
                "weights": list(r.best_weights.as_array()),
                "best_objective": r.best_objective,
                "n_evaluations": r.n_evaluations,
                "time_improvement_pct": r.time_improvement_pct,
            } for name, r in tuners.items()
        },
        "greedy_vs_jv": {"time_saving_pct": gvj.time_saving_pct,
                         "p_value_time": gvj.p_value_time},
        "figures": {
            "base_vs_improved": str((out_dir / "base_vs_improved.png").relative_to(_ROOT)),
            "convergence": str((out_dir / "convergence_3tuners.png").relative_to(_ROOT)),
            "weights": str((out_dir / "weights5.png").relative_to(_ROOT)),
            "test_improvement": str((out_dir / "test_improvement.png").relative_to(_ROOT)),
            "greedy_vs_jv": str((out_dir / "greedy_vs_jv.png").relative_to(_ROOT)),
        },
    }


def global_milp_comparison(out_root):
    """Compara JV vs MILP exacto en una instancia pequeña de un ciclo."""
    print("\n" + "=" * 70)
    print("COMPARACIÓN GLOBAL: JV vs MILP exacto (un ciclo de carga)")
    print("=" * 70)
    sc = generate_scenario(n_drones=5, n_orders=10, seed=7,
                           battery_min_pct=1.0, battery_max_pct=1.0,
                           weight_min_kg=0.3, weight_max_kg=1.2)
    milp = solve_min_makespan_single_cycle(sc)
    drones = [DroneState(spec=d.spec, battery_wh=d.battery_wh) for d in sc.drones]
    orders = [Order(order_id=o.order_id, weight_kg=o.weight_kg, distance_km=o.distance_km)
              for o in sc.orders]
    res = cost_matrix_assign(drones, orders, CostWeights(1, 1, 1, 1, 0))
    times = {}
    for a in res.assignments:
        times[a.drone_id] = times.get(a.drone_id, 0.0) + a.duration_s
    jv_mk = max(times.values()) if times else 0.0
    gap = (jv_mk - milp.optimal_makespan_s) / milp.optimal_makespan_s * 100 if milp.optimal_makespan_s else 0
    print(f"  MILP óptimo={milp.optimal_makespan_s:.0f}s | JV={jv_mk:.0f}s | gap={gap:+.1f}%")
    viz_v2.plot_milp_gap(milp.optimal_makespan_s, jv_mk, out_root / "milp_gap.png")
    return {"milp_makespan": milp.optimal_makespan_s, "jv_makespan": jv_mk,
            "gap_pct": gap, "n_drones": 5, "n_orders": 10,
            "figure": str((out_root / "milp_gap.png").relative_to(_ROOT))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--objective", default="time",
                    choices=["time", "energy", "combined", "time_p90", "time_cvar"])
    ap.add_argument("--only", default=None)
    args = ap.parse_args()

    out_root = _ROOT / "results" / "study_v2"
    out_root.mkdir(parents=True, exist_ok=True)
    archs = build_archetypes(args.quick)
    if args.only:
        archs = [a for a in archs if a["key"] == args.only]

    print("=" * 70)
    print("ESTUDIO SOLUCIÓN MEJORADA (recarga parcial + w5 + 3 tuners + P90)")
    print(f"Objetivo: {args.objective} | Arquetipos: {len(archs)} | "
          f"{'QUICK' if args.quick else 'COMPLETO'}")
    print("=" * 70)

    t0 = time.time()
    results = [process(a, args.objective, out_root) for a in archs]
    milp = global_milp_comparison(out_root)

    summary = {"objective": args.objective, "quick": args.quick,
               "elapsed_s": time.time() - t0, "archetypes": results,
               "milp_comparison": milp}
    (out_root / "study_v2_results.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✅ Estudio v2 completado en {summary['elapsed_s']:.1f}s")
    print(f"   {out_root / 'study_v2_results.json'}")


if __name__ == "__main__":
    main()

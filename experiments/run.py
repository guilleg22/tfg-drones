"""
CLI de experimentos de simulación.

Reúne en un único punto de entrada las ejecuciones que antes vivían en scripts
sueltos. Cada subcomando escribe sus resultados bajo results/.

  python -m experiments.run compare    --n-scenarios 200
  python -m experiments.run genetic     --generations 100
  python -m experiments.run montecarlo  --n-trials 2000
  python -m experiments.run nsga2       --generations 60
  python -m experiments.run bayes       --n-calls 80      (requiere scikit-optimize)
  python -m experiments.run milp        --n-scenarios 20  (requiere PuLP)
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from simulacion.cost_function import CostWeights, build_cost_matrix
from simulacion.metrics import compute_comparison, results_summary_text, to_latex_table
from simulacion.scenario_generator import DEMANDING_PRESET, generate_batch
from simulacion.simulator import Simulator, dispatch_single_cycle
from simulacion.visualization import (
    plot_comparison_bars,
    plot_comparison_boxplots,
    plot_convergence,
    plot_cost_heatmap,
    plot_crossover,
    plot_pareto_front,
)

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def _scenario_args(p, n_scenarios=30, n_orders=30):
    p.add_argument("--n-scenarios", type=int, default=n_scenarios)
    p.add_argument("--n-drones", type=int, default=5)
    p.add_argument("--n-orders", type=int, default=n_orders)
    p.add_argument("--seed", type=int, default=42)


def _print_weights(w):
    print(f"  w1={w.w1:.4f}  w2={w.w2:.4f}  w3={w.w3:.4f}  w4={w.w4:.4f}  w5={w.w5:.4f}")


# ── compare ──────────────────────────────────────────────────────────────

def cmd_compare(args):
    out = RESULTS / "comparison"
    out.mkdir(parents=True, exist_ok=True)
    weights = CostWeights(w1=args.w1, w2=args.w2, w3=args.w3, w4=args.w4)

    # Escenario exigente: una oleada de despacho (ciclo único, sin recarga) con
    # baterías limitadas y paquetes pesados, donde la demanda supera la capacidad
    # y la asignación importa. Es el régimen que distingue greedy de JV.
    print(f"Comparación greedy vs matriz de costes — {args.n_scenarios} escenarios "
          f"({args.n_drones} drones, {args.n_orders} pedidos, ciclo único con escasez)")
    scenarios = generate_batch(
        n_scenarios=args.n_scenarios, n_drones=args.n_drones,
        n_orders=args.n_orders, seed=args.seed, charger_power_w=args.charger_power,
        weight_min_kg=args.weight_min, weight_max_kg=args.weight_max,
        battery_min_pct=args.battery_min, battery_max_pct=args.battery_max,
    )

    t0 = time.time()
    greedy = [dispatch_single_cycle(s, "greedy", weights) for s in scenarios]
    print(f"  greedy: {time.time() - t0:.2f}s")
    t0 = time.time()
    jv = [dispatch_single_cycle(s, "cost_matrix", weights) for s in scenarios]
    print(f"  cost_matrix: {time.time() - t0:.2f}s")

    metrics = compute_comparison(greedy, jv)
    summary = results_summary_text(metrics)
    print("\n" + summary)
    (out / "summary.txt").write_text(summary, encoding="utf-8")
    (out / "comparison.tex").write_text(to_latex_table(metrics), encoding="utf-8")

    plot_comparison_bars(metrics, out / "comparison_bars.png")
    plot_comparison_boxplots(metrics, out / "comparison_boxplots.png")

    # ── Curva de cruce: tasa de entrega según la demanda ──
    print("\nBarrido de demanda (curva de cruce)...")
    demands = list(range(args.n_drones, args.n_orders * 2 + 1, max(1, args.n_drones)))
    g_rates, j_rates = [], []
    for d in demands:
        batch = generate_batch(
            n_scenarios=max(20, args.n_scenarios // 4), n_drones=args.n_drones,
            n_orders=d, seed=args.seed, charger_power_w=args.charger_power,
            weight_min_kg=args.weight_min, weight_max_kg=args.weight_max,
            battery_min_pct=args.battery_min, battery_max_pct=args.battery_max,
        )
        gm = compute_comparison(
            [dispatch_single_cycle(s, "greedy", weights) for s in batch],
            [dispatch_single_cycle(s, "cost_matrix", weights) for s in batch],
        )
        g_rates.append(gm.avg_greedy_delivery_rate)
        j_rates.append(gm.avg_jv_delivery_rate)
    plot_crossover(demands, g_rates, j_rates, out / "crossover.png")

    # ── Heatmap de la matriz de costes de un escenario ──
    sc = scenarios[0]
    specs = [d.spec for d in sc.drones]
    batteries = [d.battery_wh for d in sc.drones]
    weights_kg = [o.weight_kg for o in sc.orders[:10]]
    distances = [[o.distance_km for o in sc.orders[:10]] for _ in specs]
    mat = build_cost_matrix(specs, batteries, weights_kg, distances, weights)
    drone_labels = [f"{d.spec.drone_id}\n({d.spec.max_payload_kg}kg)" for d in sc.drones]
    order_labels = [f"P{o.order_id}\n{o.weight_kg}kg" for o in sc.orders[:10]]
    plot_cost_heatmap(mat, drone_labels, order_labels, out / "cost_heatmap.png")

    print(f"\nResultados en {out}")


# ── genetic / montecarlo (mismo interfaz de resultado) ────────────────────

def _run_weight_optimizer(args, name, fn, fn_kwargs, mc_curve_attr, ga_curve, out_stem):
    out = RESULTS / "optimization"
    out.mkdir(parents=True, exist_ok=True)
    scenarios = generate_batch(args.n_scenarios, args.n_drones, args.n_orders, seed=args.seed)

    print(f"{name} — objetivo={args.objective}")
    t0 = time.time()
    result = fn(scenarios=scenarios, objective=args.objective, seed=args.seed,
                verbose=True, **fn_kwargs)
    elapsed = time.time() - t0

    w = result.best_weights
    print(f"\n{name} ({elapsed:.1f}s)  objetivo={result.best_objective:.4f}  "
          f"energía={result.best_energy:.2f}Wh  tiempo={result.best_time:.2f}s")
    _print_weights(w)

    summary = {
        "method": name, "objective": args.objective,
        "best_weights": {"w1": w.w1, "w2": w.w2, "w3": w.w3, "w4": w.w4, "w5": w.w5},
        "best_energy": result.best_energy, "best_time": result.best_time,
        "best_objective": result.best_objective, "elapsed_s": elapsed,
    }
    (out / f"{out_stem}_best_weights.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")

    plot_convergence(
        mc_curve=getattr(result, "convergence_curve") if mc_curve_attr else None,
        ga_curve=getattr(result, "convergence_curve") if ga_curve else None,
        ga_avg_curve=getattr(result, "avg_fitness_curve", None) if ga_curve else None,
        output_path=out / f"{out_stem}_convergence.png",
    )
    print(f"Resultados en {out}")


def cmd_genetic(args):
    from simulacion.optimizer_genetic import optimize_genetic
    _run_weight_optimizer(
        args, "Algoritmo Genético", optimize_genetic,
        {"pop_size": args.pop_size, "n_generations": args.generations},
        mc_curve_attr=False, ga_curve=True, out_stem="ga")


def cmd_montecarlo(args):
    from simulacion.optimizer_montecarlo import optimize_montecarlo
    _run_weight_optimizer(
        args, "Monte Carlo", optimize_montecarlo,
        {"n_trials": args.n_trials},
        mc_curve_attr=True, ga_curve=False, out_stem="mc")


# ── nsga2 ─────────────────────────────────────────────────────────────────

def cmd_nsga2(args):
    from simulacion.optimizer_nsga2 import optimize_nsga2
    out = RESULTS / "optimization"
    out.mkdir(parents=True, exist_ok=True)
    scenarios = generate_batch(args.n_scenarios, args.n_drones, args.n_orders, seed=args.seed)

    print(f"NSGA-II — {args.pop_size} × {args.generations}")
    t0 = time.time()
    result = optimize_nsga2(scenarios=scenarios, pop_size=args.pop_size,
                            n_generations=args.generations, seed=args.seed, verbose=True)
    elapsed = time.time() - t0
    print(f"\nFrente de Pareto: {result.n_solutions} soluciones ({elapsed:.1f}s)")

    best_idx = None
    if result.n_solutions > 0:
        front = result.pareto_front
        rng = front.max(axis=0) - front.min(axis=0)
        rng[rng == 0] = 1.0
        norm = (front - front.min(axis=0)) / rng
        best_idx = int((norm ** 2).sum(axis=1).argmin())
        w = result.pareto_weights[best_idx]
        print(f"Solución equilibrada (idx={best_idx}): "
              f"energía={front[best_idx, 0]:.2f}Wh tiempo={front[best_idx, 1]:.2f}s")
        _print_weights(w)

    pareto = [{"energy": float(f[0]), "time": float(f[1]),
               "weights": {"w1": w.w1, "w2": w.w2, "w3": w.w3, "w4": w.w4, "w5": w.w5}}
              for f, w in zip(result.pareto_front, result.pareto_weights)]
    (out / "nsga2_results.json").write_text(
        json.dumps({"n_solutions": result.n_solutions, "best_balanced_idx": best_idx,
                    "elapsed_s": elapsed, "pareto_front": pareto}, indent=2),
        encoding="utf-8")
    if result.n_solutions > 0:
        plot_pareto_front(result.pareto_front, out / "nsga2_pareto.png", highlight_idx=best_idx)
    print(f"Resultados en {out}")


# ── bayes (scikit-optimize) ───────────────────────────────────────────────

def cmd_bayes(args):
    from simulacion.optimizer_bayes import optimize_bayes
    out = RESULTS / "optimization"
    out.mkdir(parents=True, exist_ok=True)
    scenarios = generate_batch(args.n_scenarios, args.n_drones, args.n_orders, seed=args.seed)

    print(f"Optimización bayesiana — objetivo={args.objective}, n_calls={args.n_calls}")
    t0 = time.time()
    result = optimize_bayes(scenarios=scenarios, n_calls=args.n_calls,
                            objective=args.objective, seed=args.seed, verbose=True)
    elapsed = time.time() - t0
    w = result.best_weights
    print(f"\nBayes ({elapsed:.1f}s)  objetivo={result.best_objective:.4f}")
    _print_weights(w)
    (out / "bayes_best_weights.json").write_text(json.dumps({
        "objective": args.objective, "n_calls": args.n_calls,
        "best_weights": {"w1": w.w1, "w2": w.w2, "w3": w.w3, "w4": w.w4, "w5": w.w5},
        "best_objective": result.best_objective, "elapsed_s": elapsed,
    }, indent=2), encoding="utf-8")
    print(f"Resultados en {out}")


# ── milp (PuLP) ───────────────────────────────────────────────────────────

def cmd_milp(args):
    from simulacion.milp_baseline import solve_min_makespan_single_cycle
    scenarios = generate_batch(args.n_scenarios, args.n_drones, args.n_orders, seed=args.seed)
    print(f"MILP (makespan, ciclo único) — {args.n_scenarios} escenarios")
    feasible = 0
    makespans = []
    for sc in scenarios:
        res = solve_min_makespan_single_cycle(sc)
        if res.feasible:
            feasible += 1
            makespans.append(res.makespan_s)
    print(f"  factibles: {feasible}/{len(scenarios)}")
    if makespans:
        print(f"  makespan medio: {sum(makespans) / len(makespans):.2f}s")


def build_parser():
    parser = argparse.ArgumentParser(prog="experiments.run", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compare", help="greedy vs matriz de costes (ciclo con escasez)")
    _scenario_args(c, n_scenarios=200, n_orders=DEMANDING_PRESET["n_orders"])
    c.add_argument("--charger-power", type=float, default=180.0)
    c.add_argument("--weight-min", type=float, default=DEMANDING_PRESET["weight_min_kg"])
    c.add_argument("--weight-max", type=float, default=DEMANDING_PRESET["weight_max_kg"])
    c.add_argument("--battery-min", type=float, default=DEMANDING_PRESET["battery_min_pct"])
    c.add_argument("--battery-max", type=float, default=DEMANDING_PRESET["battery_max_pct"])
    c.add_argument("--w1", type=float, default=1.0)
    c.add_argument("--w2", type=float, default=1.0)
    c.add_argument("--w3", type=float, default=1.0)
    c.add_argument("--w4", type=float, default=1.0)
    c.set_defaults(func=cmd_compare)

    g = sub.add_parser("genetic", help="optimiza pesos con AG")
    _scenario_args(g, n_scenarios=10)
    g.add_argument("--pop-size", type=int, default=50)
    g.add_argument("--generations", type=int, default=100)
    g.add_argument("--objective", default="energy", choices=["energy", "time", "combined"])
    g.set_defaults(func=cmd_genetic)

    m = sub.add_parser("montecarlo", help="optimiza pesos con Monte Carlo")
    _scenario_args(m, n_scenarios=10)
    m.add_argument("--n-trials", type=int, default=2000)
    m.add_argument("--objective", default="energy", choices=["energy", "time", "combined"])
    m.set_defaults(func=cmd_montecarlo)

    n = sub.add_parser("nsga2", help="frente de Pareto energía/tiempo")
    _scenario_args(n, n_scenarios=10)
    n.add_argument("--pop-size", type=int, default=40)
    n.add_argument("--generations", type=int, default=60)
    n.set_defaults(func=cmd_nsga2)

    b = sub.add_parser("bayes", help="optimización bayesiana (scikit-optimize)")
    _scenario_args(b, n_scenarios=10)
    b.add_argument("--n-calls", type=int, default=80)
    b.add_argument("--objective", default="time", choices=["energy", "time", "combined"])
    b.set_defaults(func=cmd_bayes)

    p = sub.add_parser("milp", help="baseline MILP de makespan (PuLP)")
    _scenario_args(p, n_scenarios=20)
    p.set_defaults(func=cmd_milp)

    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

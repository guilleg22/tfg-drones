"""
run_nsga2.py — Optimiza pesos w1-w4 con NSGA-II (multi-objetivo).

Busca el frente de Pareto minimizando energía y tiempo simultáneamente.

Uso:
  python scripts/run_nsga2.py
  python scripts/run_nsga2.py --pop-size 50 --generations 100

Salida en results/optimization/:
  - nsga2_pareto.png
  - nsga2_results.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from simulacion.optimizer_nsga2 import optimize_nsga2
from simulacion.scenario_generator import generate_batch
from simulacion.visualization import plot_pareto_front


def main():
    parser = argparse.ArgumentParser(description="Optimización NSGA-II multi-objetivo")
    parser.add_argument("--pop-size", type=int, default=40, help="Tamaño de población")
    parser.add_argument("--generations", type=int, default=60, help="Nº generaciones")
    parser.add_argument("--n-scenarios", type=int, default=10, help="Escenarios de evaluación")
    parser.add_argument("--n-drones", type=int, default=5, help="Drones por escenario")
    parser.add_argument("--n-orders", type=int, default=30, help="Pedidos por escenario")
    parser.add_argument("--seed", type=int, default=42, help="Semilla")
    args = parser.parse_args()

    output_dir = _ROOT / "results" / "optimization"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("OPTIMIZACIÓN: NSGA-II Multi-Objetivo")
    print("=" * 60)
    print(f"Población:  {args.pop_size}")
    print(f"Generaciones: {args.generations}")
    print(f"Objetivos:  Minimizar energía + Minimizar tiempo")
    print(f"Escenarios: {args.n_scenarios} × {args.n_drones}D/{args.n_orders}P")
    print()

    # Generar escenarios
    print("Generando escenarios de evaluación...")
    scenarios = generate_batch(args.n_scenarios, args.n_drones, args.n_orders, seed=args.seed)

    # Ejecutar
    print(f"\nEjecutando NSGA-II ({args.pop_size} × {args.generations})...")
    t0 = time.time()
    result = optimize_nsga2(
        scenarios=scenarios,
        pop_size=args.pop_size,
        n_generations=args.generations,
        seed=args.seed,
        verbose=True,
    )
    elapsed = time.time() - t0

    # Resultados
    print(f"\n{'=' * 60}")
    print(f"RESULTADO NSGA-II ({elapsed:.1f}s)")
    print(f"{'=' * 60}")
    print(f"Soluciones en el frente de Pareto: {result.n_solutions}")
    print(f"\nSoluciones del frente:")
    print(f"{'Energía (Wh)':>14} {'Tiempo (s)':>12}  w1     w2     w3     w4")
    print("-" * 70)
    for i, (f, w) in enumerate(zip(result.pareto_front, result.pareto_weights)):
        print(
            f"  {f[0]:10.2f}   {f[1]:10.2f}  "
            f"{w.w1:.3f}  {w.w2:.3f}  {w.w3:.3f}  {w.w4:.3f}"
        )

    # Encontrar solución más equilibrada (más cercana a la utopía normalizada)
    if result.n_solutions > 0:
        front = result.pareto_front
        f_min = front.min(axis=0)
        f_max = front.max(axis=0)
        f_range = f_max - f_min
        f_range[f_range == 0] = 1.0
        normalized = (front - f_min) / f_range
        distances = (normalized ** 2).sum(axis=1)
        best_balanced_idx = int(distances.argmin())
        w_best = result.pareto_weights[best_balanced_idx]
        print(f"\n★ Solución más equilibrada (idx={best_balanced_idx}):")
        print(f"  Energía: {front[best_balanced_idx, 0]:.2f} Wh")
        print(f"  Tiempo:  {front[best_balanced_idx, 1]:.2f} s")
        print(f"  Pesos: w1={w_best.w1:.4f}, w2={w_best.w2:.4f}, "
              f"w3={w_best.w3:.4f}, w4={w_best.w4:.4f}")
    else:
        best_balanced_idx = None

    # Guardar JSON
    pareto_data = []
    for f, w in zip(result.pareto_front, result.pareto_weights):
        pareto_data.append({
            "energy": float(f[0]),
            "time": float(f[1]),
            "weights": {"w1": w.w1, "w2": w.w2, "w3": w.w3, "w4": w.w4},
        })
    summary = {
        "n_solutions": result.n_solutions,
        "n_generations": result.n_generations,
        "elapsed_s": elapsed,
        "best_balanced_idx": best_balanced_idx,
        "pareto_front": pareto_data,
    }
    (output_dir / "nsga2_results.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"\nResultados guardados en: {output_dir / 'nsga2_results.json'}")

    # Gráfica del frente de Pareto
    if result.n_solutions > 0:
        plot_pareto_front(
            result.pareto_front,
            output_dir / "nsga2_pareto.png",
            highlight_idx=best_balanced_idx,
        )
        print(f"Frente de Pareto guardado en: {output_dir / 'nsga2_pareto.png'}")

    print(f"\n✅ Completado")


if __name__ == "__main__":
    main()

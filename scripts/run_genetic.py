"""
run_genetic.py — Optimiza pesos w1-w4 con Algoritmo Genético.

Uso:
  python scripts/run_genetic.py
  python scripts/run_genetic.py --pop-size 50 --generations 100 --objective energy

Salida en results/optimization/:
  - ga_convergence.png
  - ga_best_weights.json
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

from simulacion.optimizer_genetic import optimize_genetic
from simulacion.scenario_generator import generate_batch
from simulacion.visualization import plot_convergence


def main():
    parser = argparse.ArgumentParser(description="Optimización con Algoritmo Genético")
    parser.add_argument("--pop-size", type=int, default=50, help="Tamaño de población")
    parser.add_argument("--generations", type=int, default=100, help="Nº generaciones")
    parser.add_argument("--n-scenarios", type=int, default=10, help="Escenarios de evaluación")
    parser.add_argument("--n-drones", type=int, default=5, help="Drones por escenario")
    parser.add_argument("--n-orders", type=int, default=30, help="Pedidos por escenario")
    parser.add_argument("--objective", type=str, default="energy",
                        choices=["energy", "time", "combined"], help="Métrica a optimizar")
    parser.add_argument("--seed", type=int, default=42, help="Semilla")
    args = parser.parse_args()

    output_dir = _ROOT / "results" / "optimization"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("OPTIMIZACIÓN: Algoritmo Genético")
    print("=" * 60)
    print(f"Población:  {args.pop_size}")
    print(f"Generaciones: {args.generations}")
    print(f"Objetivo:   {args.objective}")
    print(f"Escenarios: {args.n_scenarios} × {args.n_drones}D/{args.n_orders}P")
    print()

    # Generar escenarios
    print("Generando escenarios de evaluación...")
    scenarios = generate_batch(args.n_scenarios, args.n_drones, args.n_orders, seed=args.seed)

    # Ejecutar optimización
    print(f"\nEjecutando GA ({args.pop_size} × {args.generations})...")
    t0 = time.time()
    result = optimize_genetic(
        scenarios=scenarios,
        pop_size=args.pop_size,
        n_generations=args.generations,
        objective=args.objective,
        seed=args.seed,
        verbose=True,
    )
    elapsed = time.time() - t0

    # Resultados
    w = result.best_weights
    print(f"\n{'=' * 60}")
    print(f"RESULTADO Algoritmo Genético ({elapsed:.1f}s)")
    print(f"{'=' * 60}")
    print(f"Mejor objetivo ({args.objective}): {result.best_objective:.4f}")
    print(f"Energía promedio:  {result.best_energy:.2f} Wh")
    print(f"Tiempo promedio:   {result.best_time:.2f} s")
    print(f"Mejores pesos:")
    print(f"  w1 (energía):    {w.w1:.4f}")
    print(f"  w2 (batería):    {w.w2:.4f}")
    print(f"  w3 (capacidad):  {w.w3:.4f}")
    print(f"  w4 (espera):     {w.w4:.4f}")

    # Guardar
    summary = {
        "objective": args.objective,
        "pop_size": args.pop_size,
        "generations": args.generations,
        "best_weights": {"w1": w.w1, "w2": w.w2, "w3": w.w3, "w4": w.w4},
        "best_energy": result.best_energy,
        "best_time": result.best_time,
        "best_objective": result.best_objective,
        "elapsed_s": elapsed,
    }
    (output_dir / "ga_best_weights.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"\nPesos guardados en: {output_dir / 'ga_best_weights.json'}")

    # Gráfica de convergencia
    plot_convergence(
        mc_curve=None,
        ga_curve=result.convergence_curve,
        ga_avg_curve=result.avg_fitness_curve,
        output_path=output_dir / "ga_convergence.png",
    )
    print(f"Convergencia guardada en: {output_dir / 'ga_convergence.png'}")
    print(f"\n✅ Completado")


if __name__ == "__main__":
    main()

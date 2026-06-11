"""
run_montecarlo.py — Optimiza pesos w1-w4 con Monte Carlo Random Search.

Uso:
  python scripts/run_montecarlo.py
  python scripts/run_montecarlo.py --n-trials 5000 --objective energy

Salida en results/optimization/:
  - mc_convergence.png
  - mc_best_weights.txt
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

from simulacion.optimizer_montecarlo import optimize_montecarlo
from simulacion.scenario_generator import generate_batch
from simulacion.visualization import plot_convergence


def main():
    parser = argparse.ArgumentParser(description="Optimización Monte Carlo de pesos")
    parser.add_argument("--n-trials", type=int, default=2000, help="Número de trials")
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
    print("OPTIMIZACIÓN: Monte Carlo Random Search")
    print("=" * 60)
    print(f"Trials:     {args.n_trials}")
    print(f"Objetivo:   {args.objective}")
    print(f"Escenarios: {args.n_scenarios} × {args.n_drones}D/{args.n_orders}P")
    print()

    # Generar escenarios de evaluación
    print("Generando escenarios de evaluación...")
    scenarios = generate_batch(args.n_scenarios, args.n_drones, args.n_orders, seed=args.seed)

    # Ejecutar optimización
    print(f"\nEjecutando Monte Carlo ({args.n_trials} trials)...")
    t0 = time.time()
    result = optimize_montecarlo(
        scenarios=scenarios,
        n_trials=args.n_trials,
        objective=args.objective,
        seed=args.seed,
        verbose=True,
    )
    elapsed = time.time() - t0

    # Resultados
    w = result.best_weights
    print(f"\n{'=' * 60}")
    print(f"RESULTADO Monte Carlo ({elapsed:.1f}s)")
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
        "n_trials": args.n_trials,
        "best_weights": {"w1": w.w1, "w2": w.w2, "w3": w.w3, "w4": w.w4},
        "best_energy": result.best_energy,
        "best_time": result.best_time,
        "best_objective": result.best_objective,
        "elapsed_s": elapsed,
    }
    (output_dir / "mc_best_weights.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"\nPesos guardados en: {output_dir / 'mc_best_weights.json'}")

    # Gráfica de convergencia
    plot_convergence(
        mc_curve=result.convergence_curve,
        ga_curve=None,
        output_path=output_dir / "mc_convergence.png",
    )
    print(f"Convergencia guardada en: {output_dir / 'mc_convergence.png'}")
    print(f"\n✅ Completado")


if __name__ == "__main__":
    main()

"""
run_comparison.py — Compara Greedy vs. Jonker-Volgenant sobre N escenarios.

Uso:
  python scripts/run_comparison.py
  python scripts/run_comparison.py --n-scenarios 50 --n-orders 30 --n-drones 5

Salida en results/comparison/:
  - comparison_bars.png
  - comparison_boxplots.png
  - cost_heatmap.png
  - summary.txt
  - comparison.tex
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Fix encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Añadir raíz del proyecto al path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from simulacion.cost_function import CostWeights, build_cost_matrix
from simulacion.metrics import compute_comparison, results_summary_text, to_latex_table
from simulacion.scenario_generator import generate_batch
from simulacion.simulator import Simulator
from simulacion.visualization import (
    plot_comparison_bars,
    plot_comparison_boxplots,
    plot_cost_heatmap,
)


def main():
    parser = argparse.ArgumentParser(description="Comparación Greedy vs Jonker-Volgenant")
    parser.add_argument("--n-scenarios", type=int, default=30, help="Número de escenarios")
    parser.add_argument("--n-drones", type=int, default=5, help="Drones por escenario")
    parser.add_argument("--n-orders", type=int, default=30, help="Pedidos por escenario")
    parser.add_argument("--seed", type=int, default=42, help="Semilla base")
    parser.add_argument("--charger-power", type=float, default=180.0, help="Potencia cargador (W)")
    parser.add_argument("--w1", type=float, default=1.0, help="Peso w1 (energía)")
    parser.add_argument("--w2", type=float, default=1.0, help="Peso w2 (batería)")
    parser.add_argument("--w3", type=float, default=1.0, help="Peso w3 (capacidad)")
    parser.add_argument("--w4", type=float, default=1.0, help="Peso w4 (espera)")
    args = parser.parse_args()

    # Crear directorio de resultados
    output_dir = _ROOT / "results" / "comparison"
    output_dir.mkdir(parents=True, exist_ok=True)

    weights = CostWeights(w1=args.w1, w2=args.w2, w3=args.w3, w4=args.w4)

    print("=" * 60)
    print("COMPARACIÓN: Greedy vs. Jonker-Volgenant")
    print("=" * 60)
    print(f"Escenarios:  {args.n_scenarios}")
    print(f"Drones:      {args.n_drones}")
    print(f"Pedidos:     {args.n_orders}")
    print(f"Pesos:       w1={weights.w1}, w2={weights.w2}, w3={weights.w3}, w4={weights.w4}")
    print(f"Cargador:    {args.charger_power} W")
    print()

    # Generar escenarios
    print("Generando escenarios...")
    t0 = time.time()
    scenarios = generate_batch(
        n_scenarios=args.n_scenarios,
        n_drones=args.n_drones,
        n_orders=args.n_orders,
        seed=args.seed,
        charger_power_w=args.charger_power,
    )
    print(f"  {len(scenarios)} escenarios generados en {time.time() - t0:.2f}s")

    # Ejecutar simulaciones
    sim = Simulator(charger_power_w=args.charger_power)

    print("\nEjecutando Greedy...")
    t0 = time.time()
    greedy_results = sim.run_batch(scenarios, "greedy", weights)
    t_greedy = time.time() - t0
    print(f"  Completado en {t_greedy:.2f}s")

    print("Ejecutando Jonker-Volgenant...")
    t0 = time.time()
    jv_results = sim.run_batch(scenarios, "cost_matrix", weights)
    t_jv = time.time() - t0
    print(f"  Completado en {t_jv:.2f}s")

    # Calcular métricas
    print("\nCalculando métricas...")
    metrics = compute_comparison(greedy_results, jv_results)

    # Imprimir resumen
    summary = results_summary_text(metrics)
    print("\n" + summary)

    # Guardar resumen
    (output_dir / "summary.txt").write_text(summary, encoding="utf-8")
    print(f"\nResumen guardado en: {output_dir / 'summary.txt'}")

    # Guardar LaTeX
    latex = to_latex_table(metrics)
    (output_dir / "comparison.tex").write_text(latex, encoding="utf-8")
    print(f"Tabla LaTeX guardada en: {output_dir / 'comparison.tex'}")

    # Generar gráficas
    print("\nGenerando gráficas...")

    plot_comparison_bars(metrics, output_dir / "comparison_bars.png")
    print(f"  ✓ {output_dir / 'comparison_bars.png'}")

    plot_comparison_boxplots(metrics, output_dir / "comparison_boxplots.png")
    print(f"  ✓ {output_dir / 'comparison_boxplots.png'}")

    # Heatmap del primer escenario como ejemplo
    scenario = scenarios[0]
    drone_specs = [d.spec for d in scenario.drones]
    drone_batteries = [d.battery_wh for d in scenario.drones]
    order_weights_kg = [o.weight_kg for o in scenario.orders[:10]]  # primeros 10 pedidos
    distances = [[o.distance_km for o in scenario.orders[:10]] for _ in drone_specs]
    cost_mat = build_cost_matrix(drone_specs, drone_batteries, order_weights_kg, distances, weights)
    drone_labels = [f"{d.spec.drone_id}\n({d.spec.max_payload_kg}kg)" for d in scenario.drones]
    order_labels = [f"P{o.order_id}\n{o.weight_kg}kg" for o in scenario.orders[:10]]
    plot_cost_heatmap(cost_mat, drone_labels, order_labels, output_dir / "cost_heatmap.png")
    print(f"  ✓ {output_dir / 'cost_heatmap.png'}")

    print(f"\n✅ Resultados guardados en: {output_dir}")


if __name__ == "__main__":
    main()

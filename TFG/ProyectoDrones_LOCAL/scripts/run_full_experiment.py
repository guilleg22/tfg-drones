import sys
import time
from pathlib import Path
import json

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from simulacion.optimizer_montecarlo import optimize_montecarlo
from simulacion.optimizer_genetic import optimize_genetic
from simulacion.scenario_generator import generate_batch
from simulacion.simulator import Simulator
from simulacion.cost_function import CostWeights
from simulacion.metrics import compute_comparison, results_summary_text, to_latex_table
from simulacion.visualization import plot_comparison_bars, plot_comparison_boxplots

def run_compare(scenarios, weights, out_dir_name, name=""):
    sim = Simulator()
    print(f"  [{name}] Ejecutando Greedy...")
    greedy_results = sim.run_batch(scenarios, "greedy", weights)
    print(f"  [{name}] Ejecutando JV...")
    jv_results = sim.run_batch(scenarios, "cost_matrix", weights)
    
    metrics = compute_comparison(greedy_results, jv_results)
    
    out_dir = _ROOT / "results" / out_dir_name
    out_dir.mkdir(parents=True, exist_ok=True)
    
    summary = f"=== {name} ===\nPesos: w1={weights.w1:.4f}, w2={weights.w2:.4f}, w3={weights.w3:.4f}, w4={weights.w4:.4f}\n\n"
    summary += results_summary_text(metrics)
    
    (out_dir / "summary.txt").write_text(summary, encoding="utf-8")
    (out_dir / "comparison.tex").write_text(to_latex_table(metrics), encoding="utf-8")
    
    plot_comparison_bars(metrics, out_dir / "comparison_bars.png")
    plot_comparison_boxplots(metrics, out_dir / "comparison_boxplots.png")
    
    print(f"  [{name}] Ahorro Energía: {metrics.energy_saving_pct:+.2f}% | p-value: {metrics.p_value_energy:.4f}")
    return metrics

def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    N_SCENARIOS_OPT = 10
    N_SCENARIOS_TEST = 30
    N_DRONES = 5
    N_ORDERS = 30
    
    print("=" * 60)
    print("EXPERIMENTO COMPLETO: NEUTROS vs MONTECARLO vs GENÉTICO")
    print("=" * 60)
    print(f"Drones: {N_DRONES} | Pedidos: {N_ORDERS}")
    print(f"Escenarios para Optimización: {N_SCENARIOS_OPT}")
    print(f"Escenarios para Test Final:   {N_SCENARIOS_TEST}\n")
    
    print("1. Generando escenarios...")
    scenarios_opt = generate_batch(N_SCENARIOS_OPT, N_DRONES, N_ORDERS, seed=42)
    scenarios_test = generate_batch(N_SCENARIOS_TEST, N_DRONES, N_ORDERS, seed=100)
    
    print("\n2. Ejecutando Optimización Monte Carlo (1000 trials)...")
    t0 = time.time()
    res_mc = optimize_montecarlo(scenarios_opt, n_trials=1000, objective="energy", seed=42, verbose=False)
    w_mc = res_mc.best_weights
    print(f"  ✓ Completado en {time.time()-t0:.1f}s")
    print(f"  Mejores pesos MC: w1={w_mc.w1:.4f}, w2={w_mc.w2:.4f}, w3={w_mc.w3:.4f}, w4={w_mc.w4:.4f}")
    
    print("\n3. Ejecutando Algoritmo Genético (pop=40, gen=30)...")
    t0 = time.time()
    res_ga = optimize_genetic(scenarios_opt, pop_size=40, n_generations=30, objective="energy", seed=42, verbose=False)
    w_ga = res_ga.best_weights
    print(f"  ✓ Completado en {time.time()-t0:.1f}s")
    print(f"  Mejores pesos GA: w1={w_ga.w1:.4f}, w2={w_ga.w2:.4f}, w3={w_ga.w3:.4f}, w4={w_ga.w4:.4f}")
    
    print("\n4. Evaluando Pesos Neutros (1.0, 1.0, 1.0, 1.0)...")
    w_neutros = CostWeights(1.0, 1.0, 1.0, 1.0)
    run_compare(scenarios_test, w_neutros, "experiment_neutros", "Pesos Neutros")
    
    print("\n5. Evaluando pesos Monte Carlo...")
    run_compare(scenarios_test, w_mc, "experiment_mc", "Pesos Monte Carlo")
    
    print("\n6. Evaluando pesos Algoritmo Genético...")
    run_compare(scenarios_test, w_ga, "experiment_ga", "Pesos GA")

    print("\n✅ ¡Todos los experimentos completados! Revisa las carpetas en results/")

if __name__ == "__main__":
    main()

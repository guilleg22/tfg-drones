import sys
import time
from pathlib import Path

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
    sim = Simulator(charger_power_w=300.0)
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
    
    print(f"  [{name}] Ahorro Tiempo: {metrics.time_saving_pct:+.2f}% | p-value: {metrics.p_value_time:.4f}")
    return metrics

def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    # Configuración de un día operativo en Castelldefels
    N_DRONES = 10
    N_ORDERS_TEST = 150 # Unos 15 pedidos por dron a lo largo del día
    N_SCENARIOS_TEST = 10
    
    # Parámetros para optimización
    N_SCENARIOS_OPT = 5
    N_ORDERS_OPT = 100 
    
    print("=" * 60)
    print("SIMULACIÓN: DÍA OPERATIVO CASTELLDEFELS (10 Drones, 150 Pedidos)")
    print("=" * 60)
    
    print("1. Generando escenarios...")
    scenarios_opt = generate_batch(N_SCENARIOS_OPT, N_DRONES, N_ORDERS_OPT, seed=200)
    scenarios_test = generate_batch(N_SCENARIOS_TEST, N_DRONES, N_ORDERS_TEST, seed=300)
    
    print("\n2. Ejecutando Optimización Monte Carlo (1000 trials)...")
    t0 = time.time()
    res_mc = optimize_montecarlo(scenarios_opt, n_trials=1000, objective="time", seed=42, verbose=False)
    w_mc = res_mc.best_weights
    print(f"  ✓ Completado en {time.time()-t0:.1f}s")
    print(f"  Mejores pesos MC: w1={w_mc.w1:.4f}, w2={w_mc.w2:.4f}, w3={w_mc.w3:.4f}, w4={w_mc.w4:.4f}")
    
    print("\n3. Ejecutando Algoritmo Genético (pop=50, gen=40)...")
    t0 = time.time()
    res_ga = optimize_genetic(scenarios_opt, pop_size=50, n_generations=40, objective="time", seed=42, verbose=False)
    w_ga = res_ga.best_weights
    print(f"  ✓ Completado en {time.time()-t0:.1f}s")
    print(f"  Mejores pesos GA: w1={w_ga.w1:.4f}, w2={w_ga.w2:.4f}, w3={w_ga.w3:.4f}, w4={w_ga.w4:.4f}")
    
    print("\n4. Evaluando Pesos Neutros...")
    run_compare(scenarios_test, CostWeights(1.0, 1.0, 1.0, 1.0), "castelldefels_neutros", "Pesos Neutros")
    
    print("\n5. Evaluando pesos Monte Carlo...")
    run_compare(scenarios_test, w_mc, "castelldefels_mc", "Pesos MC")
    
    print("\n6. Evaluando pesos Algoritmo Genético...")
    run_compare(scenarios_test, w_ga, "castelldefels_ga", "Pesos GA")

    print("\n✅ Completado. Revisa la carpeta results/castelldefels_*")

if __name__ == "__main__":
    main()

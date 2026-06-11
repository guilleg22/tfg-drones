import sys
import time
import math
from pathlib import Path
import csv

import matplotlib.pyplot as plt
import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from simulacion.optimizer_genetic import optimize_genetic
from simulacion.scenario_generator import generate_batch
from simulacion.simulator import Simulator
from simulacion.metrics import compute_comparison

def get_fleet_composition(size, comp_type):
    if comp_type == "Balanceada":
        l = max(1, round(size * 0.4))
        m = max(1, round(size * 0.4))
        p = size - l - m
    elif comp_type == "Foco Ligeros":
        l = max(1, round(size * 0.6))
        m = max(1, round(size * 0.2))
        p = size - l - m
    elif comp_type == "Foco Pesados":
        p = max(1, round(size * 0.6))
        m = max(1, round(size * 0.2))
        l = size - p - m
    else:
        raise ValueError("Unknown comp_type")
    
    return {"ligero": l, "medio": m, "pesado": p}

def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    out_dir = _ROOT / "results" / "macro_simulation"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Definir dimensiones
    fleet_sizes = [5, 15, 30]
    fleet_types = ["Balanceada", "Foco Ligeros", "Foco Pesados"]
    saturations = [5, 20] # Pedidos por dron
    weight_profiles = [
        ("E-commerce (0.1-1.5kg)", 0.1, 1.5),
        ("Industrial (1.5-4.0kg)", 1.5, 4.0)
    ]

    results = []
    
    total_runs = len(fleet_sizes) * len(fleet_types) * len(saturations) * len(weight_profiles)
    current_run = 0

    print("=" * 60)
    print(f"INICIANDO MACRO SIMULACIÓN: {total_runs} ESCENARIOS")
    print("=" * 60)

    for w_name, w_min, w_max in weight_profiles:
        for sat in saturations:
            for size in fleet_sizes:
                for comp_type in fleet_types:
                    current_run += 1
                    
                    n_orders = size * sat
                    comp_dict = get_fleet_composition(size, comp_type)
                    
                    print(f"[{current_run}/{total_runs}] Evaluando: {w_name} | {sat} ped/dron | Flota: {size} ({comp_type})")
                    
                    # Generar escenarios (3 para optimizar rapido, 10 para evaluar)
                    scenarios_opt = generate_batch(
                        n_scenarios=3, n_drones=size, n_orders=n_orders, seed=42, 
                        charger_power_w=300.0, fleet_composition=comp_dict, 
                        weight_min_kg=w_min, weight_max_kg=w_max
                    )
                    scenarios_test = generate_batch(
                        n_scenarios=10, n_drones=size, n_orders=n_orders, seed=100, 
                        charger_power_w=300.0, fleet_composition=comp_dict, 
                        weight_min_kg=w_min, weight_max_kg=w_max
                    )
                    
                    # Ejecutar Genético muy rápido (pop=20, gen=15) para hallar pesos adaptados
                    res_ga = optimize_genetic(
                        scenarios_opt, pop_size=20, n_generations=15, 
                        objective="time", seed=42, verbose=False
                    )
                    best_w = res_ga.best_weights
                    
                    # Evaluar Greedy vs JV (con best_w)
                    sim = Simulator(charger_power_w=300.0)
                    greedy_results = sim.run_batch(scenarios_test, "greedy", best_w)
                    jv_results = sim.run_batch(scenarios_test, "cost_matrix", best_w)
                    
                    metrics = compute_comparison(greedy_results, jv_results)
                    saving_pct = metrics.time_saving_pct
                    p_value = metrics.p_value_time
                    
                    print(f"    -> Ahorro: {saving_pct:+.2f}% | p-value: {p_value:.4f} | Pesos: [{best_w.w1:.2f}, {best_w.w2:.2f}, {best_w.w3:.2f}, {best_w.w4:.2f}]")
                    
                    results.append({
                        "WeightProfile": w_name,
                        "Saturation": sat,
                        "FleetSize": size,
                        "Composition": comp_type,
                        "TimeSavingPct": saving_pct,
                        "PValue": p_value,
                        "w1": best_w.w1, "w2": best_w.w2, "w3": best_w.w3, "w4": best_w.w4
                    })

    # Guardar a CSV
    csv_path = out_dir / "macro_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
        
    print("\nGenerando visualizaciones...")
    
    # Heatmaps por Perfil de Carga y Saturación
    for w_name, _, _ in weight_profiles:
        for sat in saturations:
            # Matriz 3x3 para (FleetSize x Composition)
            matrix = np.zeros((len(fleet_types), len(fleet_sizes)))
            
            for i, comp_type in enumerate(fleet_types):
                for j, size in enumerate(fleet_sizes):
                    # Buscar el resultado
                    row = next(r for r in results if r["WeightProfile"] == w_name and r["Saturation"] == sat and r["FleetSize"] == size and r["Composition"] == comp_type)
                    matrix[i, j] = row["TimeSavingPct"]
            
            plt.figure(figsize=(8, 6))
            plt.imshow(matrix, cmap="RdYlGn", aspect="auto", vmin=-2, vmax=max(2, np.max(matrix)+1))
            
            # Añadir valores a las celdas
            for i in range(len(fleet_types)):
                for j in range(len(fleet_sizes)):
                    plt.text(j, i, f"{matrix[i, j]:+.2f}%", ha="center", va="center", color="black", fontweight="bold")
                    
            plt.colorbar(label="Ahorro de Tiempo (%)")
            plt.xticks(range(len(fleet_sizes)), [f"{s} drones" for s in fleet_sizes])
            plt.yticks(range(len(fleet_types)), fleet_types)
            plt.title(f"Ahorro Jonker-Volgenant vs Greedy\n{w_name} - Saturación: {sat} ped/dron")
            plt.tight_layout()
            
            safe_w_name = w_name.split()[0]
            plt.savefig(out_dir / f"heatmap_{safe_w_name}_sat{sat}.png")
            plt.close()
            
    print(f"✅ Macro simulación completada. Resultados guardados en {out_dir}")

if __name__ == "__main__":
    main()

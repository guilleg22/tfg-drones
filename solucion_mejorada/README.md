# Solución mejorada — Optimización del reparto con drones

Esta carpeta contiene una **segunda solución independiente** del estudio de
optimización, que aplica todas las mejoras propuestas tras revisar la solución
base. La solución base original permanece intacta en `simulacion/`, `scripts/`
y `results/` del proyecto raíz.

## Las dos soluciones

| | Solución base (raíz) | Solución mejorada (esta carpeta) |
|---|---|---|
| Paquete | `simulacion/` | `solucion_mejorada/sim2/` |
| Recarga | siempre al 100 % | **parcial adaptativa** |
| Función de costes | 4 pesos (w1–w4) | **5 pesos** (+ w5 balanceo de carga) |
| Objetivos | energy / time / combined | + **time_p90 / time_cvar** (riesgo) |
| Tuners | Monte Carlo, Genético | + **Bayesiano** (scikit-optimize) |
| Validación exacta | — | **baseline MILP** (PuLP/CBC) |
| Asignador | `linear_sum_assignment` | `linear_sum_assignment` (sin cambios) |
| Informe | `results/Informe_Optimizacion_Parametros_TFG.docx` | `results/Informe_Solucion_Mejorada_TFG.docx` |

## Las cinco mejoras

1. **Recarga parcial** (`sim2/simulator.py`): recarga solo lo necesario para la
   cuota de viajes pendientes de cada dron. Es la mejora de mayor impacto en el
   makespan, especialmente en las rondas finales.
2. **Término w5 de balanceo de carga** (`sim2/cost_function.py`): penaliza
   asignar a drones ya muy cargados → asignación consciente del makespan.
3. **Objetivo sensible al riesgo P90/CVaR** (`sim2/objective.py`): optimiza la
   cola de la distribución (escenarios patológicos), no solo la media.
4. **Optimización bayesiana** (`sim2/optimizer_bayes.py`): tercer tuner, el más
   eficiente en evaluaciones para 5 variables continuas.
5. **Baseline MILP exacto** (`sim2/milp_baseline.py`): mide el gap de
   optimalidad del heurístico JV frente al óptimo real de makespan.

## Cómo ejecutar

```bash
cd solucion_mejorada
pip install scikit-optimize pulp      # dependencias añadidas
python scripts/run_study_v2.py        # estudio completo (--quick para rápido)
python scripts/generate_report_v2.py  # genera el .docx
```

Resultados en `solucion_mejorada/results/study_v2/` y el informe en
`solucion_mejorada/results/Informe_Solucion_Mejorada_TFG.docx`.

# Gestión autónoma de un enjambre de drones de reparto

Trabajo de Fin de Grado (UPC). El proyecto aborda el reparto urbano con una flota
de drones: cómo asignar pedidos a drones de forma eficiente y cómo coordinar el
tráfico del enjambre de manera segura.

Tiene tres partes:

- **Simulación y algoritmos** (`simulacion/`, `experiments/`): comparación entre
  una asignación voraz (greedy, FIFO) y una asignación global por matriz de costes
  resuelta con Jonker-Volgenant, sobre un modelo de energía y autonomía de la flota.
- **Portal de cliente en la nube** (`webapp/`, `portal_cliente/`): alta de clientes
  y pedidos con asignación automática de corredor, desplegado en Render con datos en
  Supabase (Postgres).
- **Aplicación de escritorio** (`main.py`, `cliente/`, `widgets/`, `negocio/`,
  `servicios/`): control del dron real vía dronLink/SITL (Mission Planner). Solo
  funciona en local porque requiere el enlace con el autopiloto.

**Portal en vivo:** https://tfg-drones.onrender.com/

## Estructura

```
simulacion/        Paquete de simulación: modelo de energía, función de costes,
                   asignadores (greedy y Jonker-Volgenant), optimizadores de pesos.
experiments/       CLI de experimentos (compare, genetic, montecarlo, nsga2, ...).
results/comparison/ Resultados reproducibles de la comparación greedy vs costes.
webapp/            Portal cloud (FastAPI): API REST + capa de datos SQLite/Postgres.
portal_cliente/    Estáticos del portal (HTML/JS/CSS) que sirve la webapp.
negocio/ servicios/ modelos/ utils/   Lógica de negocio reutilizada (geocoder, rutas...).
cliente/ widgets/ main.py             Aplicación de escritorio (PySide6).
servidor/ DesktopLAN.py RaspiAutopilotLANService.py   Servicios de enlace con el dron.
tests/             Pruebas (pytest).
```

El detalle de la simulación (función de costes, algoritmos, metodología y
gráficas explicadas) está en [`INFORME_SIMULACION.md`](INFORME_SIMULACION.md).

## Cómo probarlo

En resumen:

```bash
# Simulación (Python 3.12)
pip install -r requirements-dev.txt
python -m pytest -q                              # 44 pruebas
python -m experiments.run compare --n-scenarios 200 --seed 42
#   -> results/comparison/ (summary.txt, crossover.png, ...)

# Portal en local
pip install -r webapp/requirements.txt
uvicorn webapp.main:app --port 8080              # http://localhost:8080/
```

El experimento principal compara ambos algoritmos en una oleada de despacho con
escasez de capacidad: la asignación global entrega del orden de un 35 % más de
pedidos con menos energía por entrega que la voraz, y la curva de cruce
(`crossover.png`) muestra a partir de qué demanda aparece esa ventaja.

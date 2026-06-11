# Guion del vídeo demo (≈ 4 min)

Objetivo: enseñar al tribunal el estado de la entrega — portal en la nube,
simulación reproducible en el repo y el diseño de deconflicción en marcha.

---

## 0 · Intro (20 s)

- Contexto del TFG: gestión autónoma de un enjambre de drones de reparto.
- Qué se va a ver: portal en la nube, la simulación del algoritmo de asignación
  y el diseño de tráfico seguro del enjambre.

## 1 · Portal en la nube (70 s)

- Abrir `https://<servicio>.onrender.com`.
- **Acceder** con un nombre y una dirección de Castelldefels → mostrar que
  geocodifica y entra al panel.
- **Crear un pedido** con un peso → señalar que el sistema le asigna solo el
  corredor pre-aprobado más cercano y aparece en la lista con destino y distancia.
- Mostrar el corredor dibujado en el mapa.
- Comentar: datos en Supabase (Postgres); la telemetría en vivo es local (SITL),
  aquí es un stub.

## 2 · El repositorio y los tests (40 s)

- Mostrar la estructura: `simulacion/` (un único paquete), `webapp/`,
  `experiments/`, `docs/swarm/`.
- Ejecutar `python -m pytest -q` → **44 passed**.

## 3 · La simulación del algoritmo (60 s)

- Ejecutar `python -m experiments.run compare --n-scenarios 200 --seed 42`.
- Abrir `results/comparison/`: enseñar `summary.txt` (tasa de entrega, energía
  por pedido y makespan, con test estadístico sobre 200 escenarios), la gráfica
  `comparison_bars.png` y, sobre todo, `crossover.png`.
- Explicar la idea en una frase: en una oleada de despacho con escasez (baterías
  limitadas, paquetes pesados), la asignación global por matriz de costes
  (Jonker-Volgenant) entrega **~35 % más pedidos** con **~31 % menos energía por
  entrega** que el greedy FIFO; la curva de cruce muestra que la ventaja aparece
  justo cuando la demanda supera la capacidad de la flota.

## 4 · Deconflicción (40 s)

- Abrir `docs/swarm/06-DECONFLICTION.md`.
- Explicar el plan A (estratégico): corredores pre-aprobados + capas de altitud +
  secuenciación de despegue + reservas de tramo; y el plan B reactivo como
  contingencia.
- Mencionar que es la línea de trabajo que se empieza ahora, ya encajada con la
  arquitectura (`airspace_manager`, tabla `flight_segments`).

## 5 · Cierre (10 s)

- Próximos pasos: implementar el `PlannerService` multi-dron + `AirspaceManager`
  y validarlo en SITL con varios drones.

---

### Notas de grabación

- Despierta el servicio de Render **antes** de grabar (plan free: primer acceso lento).
- Ten `results/comparison/` ya generado por si la ejecución en directo tarda.

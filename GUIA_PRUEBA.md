# Guía de prueba

Dos formas de validar la entrega: el **portal en la nube** y la **simulación en el repo**.

---

## 1. Portal en la nube (Render + Supabase)

**URL:** https://tfg-drones.onrender.com/

Pasos:

1. Abre la URL. Se carga el portal del cliente.
2. **Acceder**: introduce un nombre y una dirección real cercana a Castelldefels
   (p.ej. *Carrer Major, Castelldefels*). El sistema geocodifica la dirección y
   crea/recupera el cliente.
3. **Crear pedido**: pulsa nuevo pedido, indica un peso (kg) y confirma. El
   backend asigna automáticamente el corredor pre-aprobado más cercano al
   cliente y el pedido aparece en la lista con su destino y distancia.
4. **Listado**: el pedido se muestra con su estado y la ruta asignada. En el mapa
   se dibuja el corredor (waypoints del perfil + tramo final al cliente).

> **Telemetría**: el indicador de telemetría del dron es un *stub* en la nube.
> El seguimiento en vivo requiere el dron real / SITL, que solo corre en local
> (no en Render). En la nube se valida toda la cadena cliente → pedido → ruta.

> **Primer acceso lento**: el plan gratuito de Render suspende el servicio tras
> un rato de inactividad; la primera petición puede tardar ~30 s en despertar.

> **Datos**: si `DATABASE_URL` apunta a Supabase (Postgres), clientes y pedidos
> persisten allí. Sin esa variable, la app usa un SQLite local efímero.

---

## 2. Simulación en el repo (local)

Requisitos: Python 3.11.

```bash
git clone <repo> && cd tfg-drones
pip install -r requirements-dev.txt
```

### 2.1 Tests

```bash
python -m pytest -q
```

Resultado esperado: **44 passed**.

### 2.2 Comparativa greedy vs matriz de costes

Experimento principal, reproducible (semilla fija) con 200 escenarios:

```bash
python -m experiments.run compare --n-scenarios 200 --seed 42
```

La comparación se hace en el régimen donde la asignación importa: una **oleada de
despacho** (ciclo único, sin recarga) con baterías limitadas y paquetes pesados,
de modo que la demanda supera la capacidad de la flota. Ahí la asignación global
(Jonker-Volgenant) se distingue del greedy FIFO. Resultado esperado: JV entrega
**~+35 % más pedidos** (≈47 % vs ≈35 % de tasa de entrega, p < 0.0001) con **~−31 %
de energía por pedido entregado**.

Genera en `results/comparison/`:

- `summary.txt` — tasa de entrega, energía por pedido entregado y makespan, con
  test t pareado.
- `comparison.tex` — tabla LaTeX lista para la memoria.
- `comparison_bars.png` — barras de las tres métricas.
- `crossover.png` — **curva de cruce**: cómo se separa JV del greedy a medida que
  crece la demanda (la clave del experimento).
- `comparison_boxplots.png`, `cost_heatmap.png`.

### 2.3 Otros experimentos (opcionales)

```bash
python -m experiments.run genetic     --generations 100   # optimiza pesos (AG)
python -m experiments.run montecarlo  --n-trials 2000     # optimiza pesos (MC)
python -m experiments.run nsga2       --generations 60    # frente de Pareto (requiere pymoo)
python -m experiments.run bayes       --n-calls 80        # bayesiana (requiere scikit-optimize)
python -m experiments.run milp        --n-scenarios 20    # baseline MILP (requiere PuLP)
```

Los tres últimos usan dependencias opcionales; si no están instaladas, el
subcomando lo indica con un mensaje claro.

---

## 3. Levantar el portal en local

```bash
pip install -r webapp/requirements.txt
uvicorn webapp.main:app --port 8080
# abrir http://localhost:8080/
```

Sin `DATABASE_URL` usa SQLite (`operations.db`). Para probar Postgres:

```bash
DATABASE_URL="postgresql://usuario:clave@host:5432/postgres" uvicorn webapp.main:app --port 8080
```

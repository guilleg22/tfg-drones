# Ejecución en local con Mission Planner (rama `local`)

Esta rama añade a la webapp la conexión real con el dron mediante **dronLink**
(Mission Planner / SITL), sin perder ninguna de las funciones del portal (login
de usuario, panel de administración, edición de rutas, etc.). La rama `main`
sigue siendo la versión cloud (sin dron, telemetría stub).

La pieza clave es el **backend de dron** (`webapp/drone_backend.py`), que se elige
con la variable de entorno `DRONE_BACKEND`:

- `stub` (por defecto): sin dron. Es lo que corre en Render.
- `local`: se conecta a Mission Planner por TCP (`tcp:127.0.0.1:5763`) usando
  dronLink, igual que la app de escritorio.

> Pensado para que un MqttBackend (Raspberry por MQTT) se añada en el futuro como
> otra implementación, sin tocar los endpoints.

## Requisitos

1. **Mission Planner con SITL** arrancado: pestaña *Simulation → Multirotor*
   (o un dron real / SITL por consola). Debe quedar escuchando MAVLink por TCP en
   `127.0.0.1:5763` (ajustable en `utils/constants.py`).
2. **dronLink** disponible (proyecto hermano `ProyectoDeDrones`). Si no está en una
   ubicación estándar junto al repo, define `DRONLINK_PATH` apuntando a la carpeta
   que contiene `dronLink/`.
3. Dependencias de la webapp: `pip install -r webapp/requirements.txt`

## Arranque

PowerShell:

```powershell
$env:DRONE_BACKEND = "local"
# Si dronLink no se encuentra solo, descomenta y ajusta:
# $env:DRONLINK_PATH = "C:\Users\test\Desktop\TFG\ProyectoDeDrones"
# Sin DATABASE_URL usa SQLite local; con ella, Supabase:
# $env:DATABASE_URL = "postgresql://..."
python -m uvicorn webapp.main:app --host 0.0.0.0 --port 8080
```

O directamente: `./run_local.ps1`

> Si ves `uvicorn no se reconoce...`, es que el ejecutable no está en el PATH;
> usa `python -m uvicorn ...` como arriba (el script ya lo hace así).

Abre **http://localhost:8080**.

## Flujo de prueba

1. **Cliente**: regístrate (usuario, contraseña, nombre, dirección de
   Castelldefels) y crea un pedido. Se le asigna ruta automáticamente.
2. **Admin** (`/admin.html`): entra, ve el pedido en *Pedidos/Flota* y pulsa
   **🛩 Enviar al dron**. La webapp construye la misión de la ruta y la sube/ejecuta
   en Mission Planner (`uploadMission` + `executeMission`).
3. En **Mission Planner** verás el dron despegar y seguir la ruta; en el mapa del
   portal verás su **telemetría en vivo** (posición, altitud, velocidad, rumbo),
   que llega por `GET /api/drone/telemetry`.

## Cómo se establece la conexión (resumen)

`webapp/drone_backend.py` (LocalBackend) hace lo mismo que la app de escritorio:

```python
cs = "tcp:127.0.0.1:5763"          # de utils/constants.py
dron.connect(cs, BAUD, freq=10)    # dronLink (pymavlink por debajo)
dron.send_telemetry_info(callback) # telemetría continua a 10 Hz
dron.uploadMission(mission); dron.executeMission()
```

Para un dron real, cambia en `utils/constants.py` el destino (puerto serie de la
radio o `udp:IP:14550`); el resto es idéntico.

"""
Backend de dron del portal: abstrae de dónde sale la telemetría y a quién se le
envían las misiones, para poder cambiar el origen sin tocar el resto de la app.

Implementaciones:
  - StubBackend  : sin dron (cloud / Render). Telemetría vacía. Es el de `main`.
  - LocalBackend : dron real o SITL en local vía dronLink (Mission Planner por
                   TCP, `tcp:127.0.0.1:5763`). Reutiliza exactamente las mismas
                   llamadas que la app de escritorio, que ya funcionan.
  - (futuro)     : un MqttBackend que hable con la Raspberry por MQTT encaja aquí
                   sin cambiar los endpoints; solo se añade otra clase.

Se elige con la variable de entorno DRONE_BACKEND (stub | local). Por defecto
'stub', para que el despliegue en la nube nunca intente importar dronLink.
"""

import os
import sys
import threading
from pathlib import Path


class StubBackend:
    """Sin dron conectado (cloud). Telemetría vacía y despacho no disponible."""
    name = "stub"

    def telemetry(self):
        return {"state": "idle", "telemetry": {}}

    def dispatch(self, mission, order_id=None):
        raise RuntimeError("No hay dron en este backend (modo cloud).")


def _add_dronlink_to_path():
    """Localiza la carpeta que contiene el paquete 'dronLink' y la añade a sys.path.

    dronLink vive en el proyecto hermano (ProyectoDeDrones). Se busca en varias
    ubicaciones habituales; con DRONLINK_PATH se puede forzar una ruta concreta.
    """
    candidates = []
    if os.environ.get("DRONLINK_PATH"):
        candidates.append(Path(os.environ["DRONLINK_PATH"]))
    root = Path(__file__).resolve().parent.parent  # ProyectoDrones_LOCAL
    candidates += [
        root.parent / "ProyectoDeDrones",
        root.parent / "TFG" / "ProyectoDeDrones",
        root.parent,
    ]
    for c in candidates:
        if c and (c / "dronLink").is_dir():
            if str(c) not in sys.path:
                sys.path.insert(0, str(c))
            return True
    return False


class LocalBackend:
    """Dron local/SITL vía dronLink. Conecta de forma perezosa en segundo plano."""
    name = "local"

    def __init__(self):
        self._dron = None
        self._latest = {}
        self._lock = threading.Lock()
        self._connecting = False

    # ── Conexión ─────────────────────────────────────────────────────────
    def _connection_string(self):
        from utils.constants import (
            MISSION_PLANNER_TRANSPORT, MISSION_PLANNER_IP, MISSION_PLANNER_PORT,
            MISSION_PLANNER_CONNECTION_STRING,
        )
        return MISSION_PLANNER_CONNECTION_STRING or \
            f"{MISSION_PLANNER_TRANSPORT}:{MISSION_PLANNER_IP}:{MISSION_PLANNER_PORT}"

    def _connect(self):
        from utils.constants import BAUD
        if self._dron is None:
            if not _add_dronlink_to_path():
                raise RuntimeError(
                    "No se encontró dronLink. Define DRONLINK_PATH apuntando a la "
                    "carpeta que contiene 'dronLink' (ProyectoDeDrones).")
            from dronLink.Dron import Dron
            self._dron = Dron()
        if getattr(self._dron, "state", "disconnected") in ("connected", "flying", "returning", "landing"):
            return
        self._dron.connect(self._connection_string(), BAUD, freq=10)
        # Telemetría continua: dronLink invoca el callback en su propio hilo.
        self._dron.send_telemetry_info(self._on_telemetry)

    def _on_telemetry(self, info):
        with self._lock:
            self._latest = info or {}

    def _ensure_connecting(self):
        """Lanza la conexión en segundo plano la primera vez (no bloquea la API)."""
        if self._dron is None and not self._connecting:
            self._connecting = True
            threading.Thread(target=self._safe_connect, daemon=True).start()

    def _safe_connect(self):
        try:
            self._connect()
        except Exception as e:  # noqa: BLE001
            print("LocalBackend: no se pudo conectar al dron:", e)
        finally:
            self._connecting = False

    # ── API pública ──────────────────────────────────────────────────────
    def telemetry(self):
        self._ensure_connecting()
        state = getattr(self._dron, "state", None) or ("connecting" if self._connecting else "idle")
        with self._lock:
            tel = dict(self._latest)
        return {"state": state, "telemetry": tel}

    def dispatch(self, mission, order_id=None):
        """Sube y ejecuta la misión en el dron (en segundo plano)."""
        def _do():
            try:
                self._connect()
                self._dron.uploadMission(mission, blocking=True)
                try:
                    self._dron.executeMission(blocking=False, wait_until_finish=False)
                except TypeError:
                    self._dron.executeMission(blocking=False)
            except Exception as e:  # noqa: BLE001
                print(f"LocalBackend.dispatch (pedido {order_id}) error:", e)
        threading.Thread(target=_do, daemon=True).start()


def get_backend():
    kind = os.environ.get("DRONE_BACKEND", "stub").lower()
    if kind == "local":
        return LocalBackend()
    return StubBackend()

"""
Portal cliente + panel de administración sobre FastAPI, desplegable en cloud.

Sirve los estáticos de portal_cliente/ y expone la API REST que consumen el
portal de cliente (alta/login de cliente, alta y listado de pedidos) y el panel
de administrador (login admin, gestión de perfiles de ruta y de pedidos/flota).

Los perfiles de ruta y los administradores se guardan en la base de datos
(Supabase en producción), no en disco, porque el sistema de ficheros de Render
es efímero. La telemetría del dron es un stub: en cloud no hay SITL ni dron real.
"""

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from negocio.geocoder import geocode_address
from servicios.route_service import RouteService
from simulacion.energy_model import DRONE_CATEGORIES
from simulacion.scenario_generator import DEFAULT_FLEET_DISTRIBUTION
from webapp import auth
from webapp.data import DataStore

PROJECT_DIR = Path(__file__).resolve().parent.parent
PORTAL_DIR = PROJECT_DIR / "portal_cliente"

app = FastAPI(title="Portal Drones")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

store = DataStore()


def _build_mission(profile_name, route_name):
    """Construye la misión (waypoints) usando los perfiles guardados en BD."""
    rs = RouteService.from_profiles(store.get_profiles())
    return rs.build_mission(profile_name, route_name)


# ── Modelos de entrada ───────────────────────────────────────────────────────

class LoginIn(BaseModel):
    name: str = ""
    address: str = ""


class OrderIn(BaseModel):
    weight_kg: float = 1.0


class AdminCredentials(BaseModel):
    username: str = ""
    password: str = ""


class UserRegister(BaseModel):
    username: str = ""
    password: str = ""
    name: str = ""
    address: str = ""


class UserLogin(BaseModel):
    username: str = ""
    password: str = ""


class OrderStateIn(BaseModel):
    status: str | None = None
    operational_state: str | None = None


# ── Portal de cliente ────────────────────────────────────────────────────────

@app.post("/api/clients/login")
def login(data: LoginIn):
    name, address = data.name.strip(), data.address.strip()
    if not name or not address:
        return JSONResponse({"error": "Nombre y dirección son obligatorios"}, 400)
    for c in store.list_clients():
        if c["name"].lower() == name.lower() and c["address"].lower() == address.lower():
            return {"client": c}
    try:
        lat, lon = geocode_address(address)
    except Exception:
        # Si el geocoder falla (rate-limit/timeout en cloud) no bloqueamos el
        # alta: el cliente queda sin coordenadas y se podrá corregir luego.
        lat, lon = None, None
    return {"client": store.create_client(name, address, lat, lon)}


# ── Cuentas de usuario (portal de cliente) ───────────────────────────────────

def require_user(authorization: str = Header(default="")):
    """Dependencia: exige un token de usuario válido y devuelve su cuenta."""
    token = authorization[7:] if authorization.lower().startswith("bearer ") else authorization
    username = auth.verify_token(token, "user")
    user = store.get_user(username) if username else None
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    return user


@app.post("/api/users/register")
def user_register(data: UserRegister):
    username, password = data.username.strip(), data.password
    name, address = data.name.strip(), data.address.strip()
    if not username or len(password) < 6 or not name or not address:
        return JSONResponse(
            {"error": "Usuario, contraseña (6+), nombre y dirección son obligatorios"}, 400)
    if store.get_user(username):
        return JSONResponse({"error": "Ese usuario ya existe"}, 409)
    try:
        lat, lon = geocode_address(address)
    except Exception:
        lat, lon = None, None
    client = store.create_client(name, address, lat, lon)
    store.create_user(username, auth.hash_password(password), client["id"])
    return {"token": auth.create_token(username, "user"), "client": client}


@app.post("/api/users/login")
def user_login(data: UserLogin):
    user = store.get_user(data.username.strip())
    if not user or not auth.verify_password(data.password, user["password_hash"]):
        return JSONResponse({"error": "Credenciales incorrectas"}, 401)
    client = store.get_client(user["client_id"])
    return {"token": auth.create_token(user["username"], "user"), "client": client}


def _attach_waypoints(order_list):
    """Añade a cada pedido los waypoints de su ruta para dibujarla en el mapa."""
    for o in order_list:
        pname, rname = o.get("assigned_profile_name"), o.get("assigned_route_name")
        if pname and rname:
            try:
                wps = _build_mission(pname, rname).get("waypoints", [])
                coords = [{"lat": float(w["lat"]), "lon": float(w["lon"])} for w in wps]
                clat, clon = o.get("client_latitude"), o.get("client_longitude")
                if clat is not None and clon is not None:
                    coords.append({"lat": float(clat), "lon": float(clon)})
                o["route_waypoints"] = coords
            except Exception:
                pass
    return order_list


@app.get("/api/orders")
def list_orders(user=Depends(require_user)):
    try:
        result = store.list_orders(user["client_id"])
    except Exception as e:
        return JSONResponse({"error": str(e)}, 400)
    return {"orders": _attach_waypoints(result)}


@app.post("/api/orders")
def create_order(data: OrderIn, user=Depends(require_user)):
    try:
        assignment = store.create_order(user["client_id"], data.weight_kg)
    except Exception as e:
        return JSONResponse({"error": str(e)}, 400)
    return {"success": True, "assignment": assignment}


@app.get("/api/drone/telemetry")
def telemetry():
    # Stub: sin dron/SITL en cloud no hay telemetría real.
    return {"state": "idle", "telemetry": {}}


# ── Autenticación de administrador ───────────────────────────────────────────

def require_admin(authorization: str = Header(default="")):
    """Dependencia: exige un token de admin válido en la cabecera Authorization."""
    token = authorization[7:] if authorization.lower().startswith("bearer ") else authorization
    username = auth.verify_token(token, "admin")
    if not username:
        raise HTTPException(status_code=401, detail="No autorizado")
    return username


@app.get("/api/admin/needs-setup")
def admin_needs_setup():
    """Indica si aún no hay ningún administrador (para mostrar el alta inicial)."""
    return {"needs_setup": store.count_admins() == 0}


@app.post("/api/admin/register")
def admin_register(data: AdminCredentials):
    # Solo se permite crear el primer admin (bootstrap). Después, ninguno más
    # por esta vía pública.
    if store.count_admins() > 0:
        return JSONResponse({"error": "Ya existe un administrador"}, 403)
    username, password = data.username.strip(), data.password
    if not username or len(password) < 6:
        return JSONResponse({"error": "Usuario obligatorio y contraseña de 6+ caracteres"}, 400)
    store.create_admin(username, auth.hash_password(password))
    return {"token": auth.create_token(username, "admin"), "username": username}


@app.post("/api/admin/login")
def admin_login(data: AdminCredentials):
    admin = store.get_admin(data.username.strip())
    if not admin or not auth.verify_password(data.password, admin["password_hash"]):
        return JSONResponse({"error": "Credenciales incorrectas"}, 401)
    return {"token": auth.create_token(admin["username"], "admin"), "username": admin["username"]}


# ── Panel de administrador: perfiles de ruta ─────────────────────────────────

@app.get("/api/admin/profiles")
def admin_get_profiles(_: str = Depends(require_admin)):
    return store.get_profiles()


@app.put("/api/admin/profiles")
def admin_save_profiles(payload: dict, _: str = Depends(require_admin)):
    if not isinstance(payload.get("profiles"), list):
        return JSONResponse({"error": "Formato inválido: falta 'profiles'"}, 400)
    store.save_profiles(payload)
    return {"success": True}


# ── Panel de administrador: pedidos y flota ──────────────────────────────────

@app.get("/api/admin/orders")
def admin_orders(_: str = Depends(require_admin)):
    return {"orders": _attach_waypoints(store.list_orders(None))}


@app.post("/api/admin/orders/{order_id}/state")
def admin_order_state(order_id: int, data: OrderStateIn, _: str = Depends(require_admin)):
    store.update_order(order_id, status=data.status, operational_state=data.operational_state)
    return {"success": True}


@app.delete("/api/admin/orders/{order_id}")
def admin_delete_order(order_id: int, _: str = Depends(require_admin)):
    store.delete_order(order_id)
    return {"success": True}


@app.get("/api/admin/clients")
def admin_clients(_: str = Depends(require_admin)):
    return {"clients": store.list_clients()}


@app.get("/api/admin/fleet")
def admin_fleet(_: str = Depends(require_admin)):
    """Flota de referencia: categorías de dron y composición por defecto.

    Es informativa: la flota real se controla desde la app de escritorio (SITL);
    aquí se expone la configuración del modelo de simulación.
    """
    categories = {
        name: {
            "max_payload_kg": spec.max_payload_kg,
            "battery_capacity_wh": spec.battery_capacity_wh,
            "cruise_speed_mps": spec.cruise_speed_mps,
        }
        for name, spec in DRONE_CATEGORIES.items()
    }
    fleet = [{"id": drone_id, "category": cat} for cat, drone_id in DEFAULT_FLEET_DISTRIBUTION]
    return {"categories": categories, "fleet": fleet}


app.mount("/", StaticFiles(directory=str(PORTAL_DIR), html=True), name="portal")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

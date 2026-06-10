"""
Portal cliente sobre FastAPI, desplegable en cloud.

Sirve los estáticos de portal_cliente/ y expone la API REST mínima que el
portal consume: alta/login de cliente, alta y listado de pedidos. La
telemetría del dron es un stub: en cloud no hay SITL ni dron real conectado.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from negocio.geocoder import geocode_address
from servicios.route_service import RouteService
from webapp.data import DataStore, PROFILES_FILE

PROJECT_DIR = Path(__file__).resolve().parent.parent
PORTAL_DIR = PROJECT_DIR / "portal_cliente"

app = FastAPI(title="Portal Drones")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

store = DataStore()
routes = RouteService(PROFILES_FILE)


class LoginIn(BaseModel):
    name: str = ""
    address: str = ""


class OrderIn(BaseModel):
    client_id: int
    weight_kg: float = 1.0


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


@app.get("/api/orders")
def list_orders(client_id: int | None = None):
    try:
        result = store.list_orders(client_id)
    except Exception as e:
        return JSONResponse({"error": str(e)}, 400)
    for o in result:
        pname, rname = o.get("assigned_profile_name"), o.get("assigned_route_name")
        if pname and rname:
            try:
                wps = routes.build_mission(pname, rname).get("waypoints", [])
                coords = [{"lat": float(w["lat"]), "lon": float(w["lon"])} for w in wps]
                clat, clon = o.get("client_latitude"), o.get("client_longitude")
                if clat is not None and clon is not None:
                    coords.append({"lat": float(clat), "lon": float(clon)})
                o["route_waypoints"] = coords
            except Exception:
                pass
    return {"orders": result}


@app.post("/api/orders")
def create_order(data: OrderIn):
    try:
        assignment = store.create_order(data.client_id, data.weight_kg)
    except Exception as e:
        return JSONResponse({"error": str(e)}, 400)
    return {"success": True, "assignment": assignment}


@app.get("/api/drone/telemetry")
def telemetry():
    # Stub: sin dron/SITL en cloud no hay telemetría real.
    return {"state": "idle", "telemetry": {}}


app.mount("/", StaticFiles(directory=str(PORTAL_DIR), html=True), name="portal")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

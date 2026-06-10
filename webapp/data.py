"""
Capa de datos del portal cloud.

Agnóstica del motor: usa SQLAlchemy Core para hablar igual con SQLite (local,
desarrollo) o Postgres (Supabase, producción). El motor se elige por la
variable de entorno DATABASE_URL; si no está definida se cae a un fichero
SQLite local.

La asignación de ruta a cada pedido reutiliza servicios.route_matcher, el
mismo criterio que la app de escritorio.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, MetaData, String, Table,
    create_engine, func, select,
)

from servicios.route_matcher import find_best_route

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE = "sqlite:///" + str(PROJECT_DIR / "operations.db")
PROFILES_FILE = PROJECT_DIR / "route_profiles.json"

metadata = MetaData()

clients = Table(
    "clients", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("address", String(512), nullable=False),
    Column("latitude", Float),
    Column("longitude", Float),
    Column("created_at", DateTime, default=lambda: datetime.now(timezone.utc)),
)

orders = Table(
    "orders", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("client_id", Integer, ForeignKey("clients.id"), nullable=False),
    Column("weight_kg", Float, nullable=False),
    Column("status", String(32), nullable=False, default="pendiente"),
    Column("assigned_profile_name", String(255)),
    Column("assigned_route_name", String(255)),
    Column("assigned_destination_name", String(255)),
    Column("assigned_destination_lat", Float),
    Column("assigned_destination_lon", Float),
    Column("assigned_distance_km", Float),
    Column("operational_state", String(64)),
    Column("created_at", DateTime, default=lambda: datetime.now(timezone.utc)),
)


def _normalize_url(url):
    # SQLAlchemy no acepta el viejo esquema postgres:// que sirven algunos
    # proveedores; lo pasamos a postgresql://.
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


class DataStore:
    def __init__(self, database_url=None, profiles_path=PROFILES_FILE):
        url = _normalize_url(database_url or os.environ.get("DATABASE_URL") or DEFAULT_SQLITE)
        self.engine = create_engine(url, future=True)
        self.profiles_path = Path(profiles_path)
        metadata.create_all(self.engine)

    def _load_profiles(self):
        with open(self.profiles_path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return payload.get("profiles", []) if isinstance(payload, dict) else []

    def _assign(self, lat, lon):
        if lat is None or lon is None:
            raise ValueError("Cliente sin coordenadas")
        return find_best_route(self._load_profiles(), float(lat), float(lon))

    # ── Clientes ─────────────────────────────────────────────────────────

    def list_clients(self):
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(clients.c.id, clients.c.name, clients.c.address,
                       clients.c.latitude, clients.c.longitude)
                .order_by(clients.c.name)
            ).mappings().all()
        return [dict(r) for r in rows]

    def create_client(self, name, address, lat, lon):
        with self.engine.begin() as conn:
            cid = conn.execute(
                clients.insert().values(
                    name=name.strip(), address=address.strip(),
                    latitude=lat, longitude=lon,
                )
            ).inserted_primary_key[0]
        return {"id": cid, "name": name.strip(), "address": address.strip(),
                "latitude": lat, "longitude": lon}

    # ── Pedidos ──────────────────────────────────────────────────────────

    def list_orders(self, client_id=None):
        j = orders.join(clients, clients.c.id == orders.c.client_id)
        stmt = (
            select(
                orders.c.id, orders.c.client_id, clients.c.name.label("client_name"),
                clients.c.latitude.label("client_latitude"),
                clients.c.longitude.label("client_longitude"),
                orders.c.weight_kg, orders.c.status,
                orders.c.assigned_profile_name, orders.c.assigned_route_name,
                orders.c.assigned_destination_name, orders.c.assigned_destination_lat,
                orders.c.assigned_destination_lon, orders.c.assigned_distance_km,
                orders.c.operational_state,
            )
            .select_from(j)
            .order_by(orders.c.id.desc())
        )
        if client_id is not None:
            stmt = stmt.where(orders.c.client_id == int(client_id))
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(r) for r in rows]

    def create_order(self, client_id, weight_kg, status="pendiente"):
        with self.engine.connect() as conn:
            row = conn.execute(
                select(clients.c.latitude, clients.c.longitude)
                .where(clients.c.id == int(client_id))
            ).first()
        if row is None:
            raise ValueError("Cliente no encontrado")
        a = self._assign(row[0], row[1])
        with self.engine.begin() as conn:
            conn.execute(orders.insert().values(
                client_id=int(client_id), weight_kg=float(weight_kg), status=status,
                assigned_profile_name=a["profile_name"],
                assigned_route_name=a["route_name"],
                assigned_destination_name=a["destination_name"],
                assigned_destination_lat=a["destination_lat"],
                assigned_destination_lon=a["destination_lon"],
                assigned_distance_km=a["distance_km"],
            ))
        return a

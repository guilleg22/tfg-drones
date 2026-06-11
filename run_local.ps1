# Arranca la webapp en modo local conectada a Mission Planner (dronLink).
# Requiere Mission Planner con SITL escuchando en tcp:127.0.0.1:5763.

$env:DRONE_BACKEND = "local"

# Descomenta y ajusta si dronLink no se encuentra automaticamente:
# $env:DRONLINK_PATH = "C:\Users\test\Desktop\TFG\ProyectoDeDrones"

# Descomenta para usar Supabase en vez de SQLite local:
# $env:DATABASE_URL = "postgresql://..."

# Se invoca como 'python -m uvicorn' para no depender de que el ejecutable
# uvicorn esté en el PATH (con la Python de la Microsoft Store no suele estarlo).
python -m uvicorn webapp.main:app --host 0.0.0.0 --port 8080

"""
Geocoder – Implementación limpia y robusta usando geopy (Nominatim).
"""

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

# Instancia global del geocoder, con un user_agent descriptivo
_geolocator = Nominatim(user_agent="proyecto_drones_tfg")

def geocode_address(address):
    """
    Convierte una dirección de texto a coordenadas (latitud, longitud).
    Utiliza OpenStreetMap Nominatim vía geopy.
    Retorna:
        tuple: (latitud, longitud)
    Lanza:
        ValueError: Si no se encuentra la dirección o falla el servicio.
    """
    if not address or not str(address).strip():
        raise ValueError("La dirección está vacía")

    try:
        location = _geolocator.geocode(str(address), timeout=10)
        if location:
            return location.latitude, location.longitude
        else:
            raise ValueError(f"No se encontraron coordenadas para: {address}")
    except (GeocoderTimedOut, GeocoderUnavailable) as e:
        raise ValueError(f"El servicio de mapas no está disponible actualmente. Detalle: {e}")
    except Exception as e:
        raise ValueError(f"Error inesperado al buscar la dirección: {e}")

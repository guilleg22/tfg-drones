"""
Modelos de datos: Waypoint y Mission.
"""


class Waypoint:
    """Representa un punto en el espacio con lat, lon y altitud."""

    __slots__ = ("lat", "lon", "alt", "name")

    def __init__(self, lat, lon, alt=8.0, name=""):
        self.lat = float(lat)
        self.lon = float(lon)
        self.alt = float(alt)
        self.name = str(name)

    def to_dict(self):
        d = {"lat": self.lat, "lon": self.lon, "alt": self.alt}
        if self.name:
            d["name"] = self.name
        return d

    @classmethod
    def from_dict(cls, data):
        return cls(
            lat=data["lat"],
            lon=data["lon"],
            alt=data.get("alt", 8.0),
            name=data.get("name", ""),
        )

    def __repr__(self):
        return "Waypoint({:.6f}, {:.6f}, alt={:.1f}, name={!r})".format(
            self.lat, self.lon, self.alt, self.name
        )


class Mission:
    """Estructura de misión con waypoints, velocidad y altitud de despegue."""

    def __init__(self, waypoints=None, speed=7.0, takeoff_alt=8.0):
        self.waypoints = waypoints or []
        self.speed = float(speed)
        self.takeoff_alt = float(takeoff_alt)

    def to_dict(self):
        return {
            "speed": self.speed,
            "takeOffAlt": self.takeoff_alt,
            "waypoints": [
                w.to_dict() if isinstance(w, Waypoint) else w
                for w in self.waypoints
            ],
        }

    @classmethod
    def from_dict(cls, data):
        wps = [Waypoint.from_dict(w) for w in data.get("waypoints", [])]
        return cls(
            waypoints=wps,
            speed=data.get("speed", 7.0),
            takeoff_alt=data.get("takeOffAlt", 8.0),
        )

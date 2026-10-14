# -*- coding: utf-8 -*-
"""Geodesia sem dependencias externas (sem PostGIS/SpatiaLite).

Distancia Haversine em metros (WGS84, raio medio 6.371.008,8 m) e bounding
box geografica que engloba com seguranca o circulo geodesico (spec 9.1/9.2).
"""
import math

from .config import EARTH_RADIUS_M

# Metros por grau de latitude (aprox. constante).
_M_PER_DEG_LAT = 111320.0


def haversine_m(lat1, lon1, lat2, lon2):
    """Distancia em metros entre dois pontos WGS84."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2.0) ** 2 +
         math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def bounding_box(lat, lon, raio_m):
    """Caixa que contem o circulo de raio `raio_m` ao redor de (lat, lon).

    Retorna dict com lat_min, lat_max, lon_min, lon_max, cruza_antimeridiano,
    inclui_polos. Perto dos polos aceita qualquer longitude (spec 9.1).
    """
    if lat < -90.0 or lat > 90.0:
        raise ValueError("latitude fora de -90..90")
    if lon < -180.0 or lon > 180.0:
        raise ValueError("longitude fora de -180..180")
    if raio_m <= 0:
        raise ValueError("raio deve ser positivo")

    dlat = math.degrees(raio_m / EARTH_RADIUS_M)
    lat_min = max(-90.0, lat - dlat)
    lat_max = min(90.0, lat + dlat)

    cos_lat = math.cos(math.radians(lat))
    # Perto dos polos (ou latitude + raio cruzando o polo) nao se limita lon.
    inclui_polos = (lat_max >= 90.0) or (lat_min <= -90.0)
    eps = 1e-9
    if inclui_polos or abs(cos_lat) < eps:
        return {
            "lat_min": lat_min, "lat_max": lat_max,
            "lon_min": -180.0, "lon_max": 180.0,
            "cruza_antimeridiano": False, "inclui_polos": True,
        }

    # dlon derivado da mesma aproximacao esferica, com folga de seguranca.
    dlon = math.degrees(raio_m / (EARTH_RADIUS_M * cos_lat))
    dlon = min(dlon, 180.0)
    lon_min = lon - dlon
    lon_max = lon + dlon

    cruza = False
    if lon_min < -180.0 or lon_max > 180.0:
        cruza = True

    return {
        "lat_min": lat_min, "lat_max": lat_max,
        "lon_min": lon_min, "lon_max": lon_max,
        "cruza_antimeridiano": cruza, "inclui_polos": False,
    }


def normaliza_longitude(lon):
    """Traz uma longitude para -180..180."""
    while lon < -180.0:
        lon += 360.0
    while lon > 180.0:
        lon -= 360.0
    return lon


def dentro_do_raio(lat, lon, lat0, lon0, raio_m):
    return haversine_m(lat0, lon0, lat, lon) <= raio_m

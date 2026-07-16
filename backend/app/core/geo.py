"""Geospatial helpers. No external dependency — pure stdlib math."""

from math import asin, cos, radians, sin, sqrt

_EARTH_RADIUS_M = 6_371_000.0  # mean Earth radius in metres


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in metres.

    Used to compare a customer's device location against the restaurant's stored
    point for the scan-time geofence check.
    """
    rlat1, rlat2 = radians(lat1), radians(lat2)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * asin(sqrt(a))

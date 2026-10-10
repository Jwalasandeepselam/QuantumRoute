"""Road distances from OSRM, with a Euclidean fallback (all in meters)."""

import numpy as np
import requests


def get_distance_matrix(nodes):
    """Return directed driving distances for an iterable of [latitude, longitude].

    If any request fails, replace the entire matrix with Euclidean distances
    in a local equirectangular projection, keeping the units in meters.
    """
    coordinates = np.asarray(nodes, dtype=float)
    if coordinates.size == 0:
        return np.zeros((0, 0), dtype=float)
    if coordinates.ndim != 2 or coordinates.shape[1] != 2:
        raise ValueError("nodes must have shape (N, 2) with [lat, lon] rows")
    if not np.isfinite(coordinates).all():
        raise ValueError("coordinates must be finite")
    if (np.abs(coordinates[:, 0]) > 90).any() or (np.abs(coordinates[:, 1]) > 180).any():
        raise ValueError("coordinates are outside latitude/longitude bounds")
    count = len(coordinates)
    distances = np.zeros((count, count), dtype=float)
    try:
        for i, (lat1, lon1) in enumerate(coordinates):
            for j, (lat2, lon2) in enumerate(coordinates):
                if i == j:
                    continue
                url = (
                    "http://router.project-osrm.org/route/v1/driving/"
                    f"{lon1},{lat1};{lon2},{lat2}?overview=false"
                )
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                payload = response.json()
                if payload.get("code") != "Ok":
                    raise ValueError("OSRM could not find a driving route")
                value = float(payload["routes"][0]["distance"])
                if not np.isfinite(value) or value < 0:
                    raise ValueError("OSRM returned an invalid distance")
                distances[i, j] = value
        return distances
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        radians = np.radians(coordinates)
        latitude = radians[:, 0]
        longitude = radians[:, 1]
        delta_lon = longitude[:, None] - longitude[None, :]
        delta_lon = (delta_lon + np.pi) % (2 * np.pi) - np.pi
        x = delta_lon * np.cos(latitude.mean())
        y = latitude[:, None] - latitude[None, :]
        return 6_371_000.0 * np.hypot(x, y)

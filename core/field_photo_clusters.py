"""Read-only, privacy-scoped geographic grid counts for the map overview."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.database import connect_database_read_only
from core.field_photo_map_query import map_visibility_conditions
from core.field_photo_store import database_path_for

OVERVIEW_GRID_SIZE = 16


def list_map_photo_clusters(
    storage_dir: Path,
    *,
    bounds: tuple[float, float, float, float],
    approved_types: tuple[str, ...] | None,
    pending_visible: bool,
) -> list[dict[str, Any]]:
    """Return at most 256 synthetic geographic cell centers and safe counts."""
    west, south, east, north = bounds
    n = OVERVIEW_GRID_SIZE
    lat_step = (north - south) / n or 1.0
    lon_span = east - west if west <= east else east + 360 - west
    lon_step = lon_span / n or 1.0
    crossing = west > east

    where, where_params = map_visibility_conditions(approved_types, pending_visible)
    if where == ["0"]:
        return []
    where.append("lat >= ? AND lat <= ?")
    where_params.extend((south, north))
    where.append("(lon >= ? OR lon <= ?)" if crossing else "lon >= ? AND lon <= ?")
    where_params.extend((west, east))

    lat_bin = "MIN(?, CAST((lat - ?) / ? AS INTEGER))"
    shifted = "(CASE WHEN lon < ? THEN lon + 360 ELSE lon END)" if crossing else "lon"
    lon_bin = f"MIN(?, CAST(({shifted} - ?) / ? AS INTEGER))"
    bins: list[Any] = [n - 1, south, lat_step, n - 1]
    if crossing:
        bins.append(west)
    bins.extend((west, lon_step))

    sql = f"""
        SELECT {lat_bin} AS lat_cell, {lon_bin} AS lon_cell,
            COUNT(*) AS total,
            SUM(CASE WHEN public_review_status = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN public_review_status = 'approved' AND issue_type = 'vehicle'
                     THEN 1 ELSE 0 END) AS vehicles,
            SUM(CASE WHEN public_review_status = 'approved' AND issue_type = 'infrastructure'
                     THEN 1 ELSE 0 END) AS infrastructure,
            SUM(CASE WHEN public_review_status = 'approved' AND issue_type = 'smoke'
                     THEN 1 ELSE 0 END) AS smoke
        FROM field_photos WHERE {" AND ".join(where)}
        GROUP BY lat_cell, lon_cell ORDER BY lat_cell, lon_cell
    """
    connection = connect_database_read_only(database_path_for(storage_dir))
    try:
        rows = connection.execute(sql, (*bins, *where_params)).fetchall()
    finally:
        connection.close()

    result = []
    for row in rows:
        lat_cell, lon_cell = int(row["lat_cell"]), int(row["lon_cell"])
        lon = west + (lon_cell + 0.5) * lon_step
        if lon > 180:
            lon -= 360
        result.append(
            {
                "lat": min(90.0, south + (lat_cell + 0.5) * lat_step),
                "lon": lon,
                "total": int(row["total"]),
                "vehicles": int(row["vehicles"]),
                "infrastructure": int(row["infrastructure"]),
                "smoke": int(row["smoke"]),
                "pending": int(row["pending"]),
            }
        )
    return result

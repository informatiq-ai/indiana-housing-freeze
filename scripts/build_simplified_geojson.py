"""Pre-compute a simplified ZIP-code GeoJSON for the Streamlit map app.

Reads the full Indiana ZCTA GeoJSON, simplifies geometries with a 0.0001 degree
tolerance (~10 m, invisible at zoom 8-10), and writes the result to disk so the
app can load it directly without invoking GeoPandas at runtime.

Run once after the source GeoJSON changes:
    python scripts/build_simplified_geojson.py
"""

import json
from pathlib import Path
from typing import Any, Dict

import geopandas as gpd
import requests
from shapely.geometry import MultiPolygon, Polygon

ROOT = Path(__file__).resolve().parents[1]
SOURCE_CACHE = ROOT / "data/processed/indiana_zips.geojson"
SOURCE_URL = (
    "https://raw.githubusercontent.com/OpenDataDE/"
    "State-zip-code-GeoJSON/master/in_indiana_zip_codes_geo.min.json"
)
OUTPUT = ROOT / "data/zip_geojson_simplified.json"
TOLERANCE = 0.0001


def load_source() -> Dict[str, Any]:
    if SOURCE_CACHE.exists():
        with open(SOURCE_CACHE) as f:
            return json.load(f)
    response = requests.get(SOURCE_URL, timeout=30)
    response.raise_for_status()
    data = response.json()
    SOURCE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(SOURCE_CACHE, "w") as f:
        json.dump(data, f)
    return data


def get_coord_count(geom: Any) -> int:
    """Count coordinates for Polygon or MultiPolygon geometries (Pylance-friendly)."""
    if isinstance(geom, Polygon):
        return len(geom.exterior.coords)
    if isinstance(geom, MultiPolygon):
        # Filter for Polygon components to ensure exterior access is type-safe
        return sum(
            len(p.exterior.coords) for p in geom.geoms if isinstance(p, Polygon)
        )
    return 0


def main() -> None:
    raw = load_source()
    gdf = gpd.GeoDataFrame.from_features(raw["features"], crs="EPSG:4326")
    n_in = sum(get_coord_count(g) for g in gdf.geometry)
    gdf["geometry"] = gdf.geometry.simplify(
        tolerance=TOLERANCE, preserve_topology=True
    )
    n_out = sum(get_coord_count(g) for g in gdf.geometry)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        f.write(gdf.to_json())
    print(f"Features: {len(gdf)}")
    pct = (n_out / n_in) if n_in > 0 else 0
    print(f"Coordinate count: {n_in:,} -> {n_out:,} ({pct:.1%})")
    print(f"Wrote: {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

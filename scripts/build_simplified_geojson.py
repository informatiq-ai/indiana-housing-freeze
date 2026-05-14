"""Pre-compute a simplified ZIP-code GeoJSON for the Streamlit map app.

Reads the full Indiana ZCTA GeoJSON, simplifies geometries with a 0.0001 degree
tolerance (~10 m, invisible at zoom 8-10), and writes the result to disk so the
app can load it directly without invoking GeoPandas at runtime.

Run once after the source GeoJSON changes:
    python scripts/build_simplified_geojson.py
"""

import json
from pathlib import Path

import geopandas as gpd
import requests

ROOT = Path(__file__).resolve().parents[1]
SOURCE_CACHE = ROOT / "data/processed/indiana_zips.geojson"
SOURCE_URL = (
    "https://raw.githubusercontent.com/OpenDataDE/"
    "State-zip-code-GeoJSON/master/in_indiana_zip_codes_geo.min.json"
)
OUTPUT = ROOT / "data/zip_geojson_simplified.json"
TOLERANCE = 0.0001


def load_source() -> dict:
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


def main() -> None:
    raw = load_source()
    gdf = gpd.GeoDataFrame.from_features(raw["features"], crs="EPSG:4326")
    n_in = sum(
        len(list(g.exterior.coords)) if g.geom_type == "Polygon"
        else sum(len(list(p.exterior.coords)) for p in g.geoms)
        for g in gdf.geometry
    )
    gdf["geometry"] = gdf.geometry.simplify(
        tolerance=TOLERANCE, preserve_topology=True
    )
    n_out = sum(
        len(list(g.exterior.coords)) if g.geom_type == "Polygon"
        else sum(len(list(p.exterior.coords)) for p in g.geoms)
        for g in gdf.geometry
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        f.write(gdf.to_json())
    print(f"Features: {len(gdf)}")
    print(f"Coordinate count: {n_in:,} -> {n_out:,} ({n_out / n_in:.1%})")
    print(f"Wrote: {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

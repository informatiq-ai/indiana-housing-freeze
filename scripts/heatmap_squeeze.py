import pandas as pd
import geopandas as gpd
import folium
import requests
import numpy as np
from branca.colormap import StepColormap
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]

# ── Load enriched zip data ────────────────────────────────────────────────────
zip_data = pd.read_csv(ROOT / "data/processed/zip_median_prices.csv")
zip_data["zip_code"] = zip_data["zip_code"].astype(str).str.zfill(5)
zip_data = zip_data[zip_data["zip_code"] != "00000"].copy()

# Aggregate to one row per zip weighted by transactions
zip_agg = (
    zip_data
    .groupby("zip_code")
    .apply(lambda x: pd.Series({
        "median_sale_price": np.average(
            x["median_sale_price"], weights=x["transactions"]
        ),
        "zcta_hhi": np.average(
            x["zcta_hhi"].fillna(x["zcta_hhi"].median()),
            weights=x["transactions"]
        ),
        "transactions": x["transactions"].sum(),
        "county": x.loc[x["transactions"].idxmax(), "county"]
    }))
    .reset_index()
)

# Compute squeeze ratio; drop rows where HHI is missing or zero
zip_agg = zip_agg[zip_agg["zcta_hhi"].notna() & (zip_agg["zcta_hhi"] > 0)].copy()
zip_agg["stress_ratio"] = zip_agg["median_sale_price"] / zip_agg["zcta_hhi"]

# Pre-format display columns — no lambda formatters in tooltip
zip_agg["hhi_display"]    = zip_agg["zcta_hhi"].apply(
    lambda x: f"${x:,.0f}")
zip_agg["price_display"]  = zip_agg["median_sale_price"].apply(
    lambda x: f"${x:,.0f}")
zip_agg["ratio_display"]  = zip_agg["stress_ratio"].apply(
    lambda x: f"{x:.1f}x")

print(f"Zip codes for squeeze map: {len(zip_agg)}")
print(f"Squeeze ratio range: {zip_agg['stress_ratio'].min():.2f}x"
      f" — {zip_agg['stress_ratio'].max():.2f}x")

# ── Download zip boundaries ───────────────────────────────────────────────────
zip_cache = ROOT / "data/processed/indiana_zips.geojson"
if zip_cache.exists():
    gdf = gpd.read_file(zip_cache)
else:
    print("Downloading zip boundaries (one-time)...")
    tiger_url = (
        "https://raw.githubusercontent.com/OpenDataDE/"
        "State-zip-code-GeoJSON/master/in_indiana_zip_codes_geo.min.json"
    )
    response = requests.get(tiger_url, timeout=30)
    gdf = gpd.read_file(response.text.encode())
    gdf.to_file(zip_cache, driver="GeoJSON")
    print("Cached to data/processed/indiana_zips.geojson")

zip_col = [c for c in gdf.columns
           if "zip" in c.lower() or "zcta" in c.lower()][0]
gdf[zip_col] = gdf[zip_col].astype(str).str.zfill(5)

gdf_merged = gdf.merge(
    zip_agg,
    left_on  = zip_col,
    right_on = "zip_code",
    how      = "inner"
).to_crs(epsg=4326)

print(f"Matched {len(gdf_merged)} zip codes")

# ── Build squeeze choropleth map ──────────────────────────────────────────────
m = folium.Map(
    location   = [39.90, -86.16],
    zoom_start = 10,
    tiles      = "CartoDB positron"
)

# 4-step palette matching the R Leaflet version:
#   0–3x  dark navy   #08306B (affordable)
#   3–4x  mid blue    #4472C4
#   4–5x  orange      #ED7D31 (stress threshold)
#   5x+   deep red    #C00000 (severe squeeze)
colormap = StepColormap(
    colors  = ["#08306B", "#4472C4", "#ED7D31", "#C00000"],
    vmin    = 0,
    vmax    = 6,
    index   = [0, 3, 4, 5, 6],
    caption = "Squeeze Ratio (Median Sale Price ÷ Median HHI)"
)

# ZIP polygons with tooltip
folium.GeoJson(
    gdf_merged,
    style_function = lambda feature: {
        "fillColor":   colormap(
            min(feature["properties"]["stress_ratio"], 5.99)
        ),
        "color":       "#555555",
        "weight":      0.8,
        "fillOpacity": 0.75
    },
    tooltip = folium.GeoJsonTooltip(
        fields  = ["zip_code", "county",
                   "hhi_display",
                   "price_display",
                   "ratio_display"],
        aliases = ["ZIP", "County",
                   "Median HHI",
                   "Median Sale Price",
                   "Squeeze Ratio"],
        localize = False
    )
).add_to(m)

# ── County boundary outlines ──────────────────────────────────────────────────
# Cache county GeoJSON locally to avoid repeated large downloads
county_cache = ROOT / "data/processed/counties_fips.geojson"
if county_cache.exists():
    counties_gdf = gpd.read_file(county_cache)
else:
    print("Downloading county boundaries (one-time)...")
    county_url   = (
        "https://raw.githubusercontent.com/plotly/datasets/"
        "master/geojson-counties-fips.json"
    )
    county_resp  = requests.get(county_url, timeout=60)
    counties_gdf = gpd.read_file(county_resp.text.encode())
    counties_gdf.to_file(county_cache, driver="GeoJSON")
    print("Cached to data/processed/counties_fips.geojson")
target_fips  = ["18097", "18057", "18011", "18063", "18081"]
counties_sub = counties_gdf[
    counties_gdf["id"].isin(target_fips)
].to_crs(epsg=4326)

folium.GeoJson(
    counties_sub,
    style_function = lambda x: {
        "fillColor":   "none",
        "color":       "#000000",
        "weight":      2.5,
        "fillOpacity": 0
    }
).add_to(m)

# ── County name labels ────────────────────────────────────────────────────────
county_labels = {
    "Marion":    (39.773, -86.158),
    "Hamilton":  (40.048, -86.046),
    "Boone":     (40.048, -86.470),
    "Hendricks": (39.773, -86.520),
    "Johnson":   (39.490, -86.100)
}

for name, (lat, lon) in county_labels.items():
    folium.Marker(
        location = [lat, lon],
        icon     = folium.DivIcon(
            html = f"""<div style="
                font-size:13px;font-weight:bold;
                color:#222;text-shadow:1px 1px 2px white;
                white-space:nowrap">{name} County</div>""",
            icon_size   = (130, 20),
            icon_anchor = (65, 10)
        )
    ).add_to(m)

# ── Title ─────────────────────────────────────────────────────────────────────
title_html = """
<div style="position:fixed;top:10px;left:50%;
    transform:translateX(-50%);z-index:1000;
    background:white;padding:6px 14px;
    border-radius:6px;box-shadow:0 2px 6px rgba(0,0,0,0.3);
    font-family:Arial,sans-serif;text-align:center;
    max-width:280px;">
    <div style="font-size:13px;font-weight:bold;color:#333">
        The Indy Squeeze: Housing Affordability by ZIP Code &mdash; Indianapolis Metro
    </div>
    <div style="font-size:10px;color:#666;margin-top:2px">
        Squeeze Ratio = Median Sale Price &divide; Median Household Income |
        2021&ndash;2025 | Source: STATS Indiana SDF &amp; U.S. Census Bureau ACS 2023
    </div>
</div>"""
m.get_root().html.add_child(folium.Element(title_html))
colormap.add_to(m)
m.get_root().html.add_child(folium.Element("""
<style>
.colormap {
    position: fixed !important;
    bottom: 40px !important;
    right: 10px !important;
    top: auto !important;
    left: auto !important;
    z-index: 1000 !important;
}
</style>
"""))

# ── Save ──────────────────────────────────────────────────────────────────────
os.makedirs(ROOT / "outputs/interactive", exist_ok=True)
m.save(ROOT / "outputs/interactive/heatmap_squeeze.html")
print("\nSaved outputs/interactive/heatmap_squeeze.html")

print("\nTop 10 zip codes by squeeze ratio:")
print(
    zip_agg.sort_values("stress_ratio", ascending=False)
    .head(10)[["zip_code", "county",
               "ratio_display", "price_display", "hhi_display"]]
    .to_string(index=False)
)

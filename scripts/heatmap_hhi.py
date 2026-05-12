import pandas as pd
import geopandas as gpd
import folium
import requests
import numpy as np
from branca.colormap import LinearColormap
from pathlib import Path

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
        "transactions":    x["transactions"].sum(),
        "pct_mid_luxury":  np.average(
            x["pct_mid_luxury"], weights=x["transactions"]
        ),
        "afford_ratio_zip": np.average(
            x["afford_ratio_zip"].fillna(0),
            weights=x["transactions"]
        ),
        "county": x.loc[x["transactions"].idxmax(), "county"]
    }))
    .reset_index()
)

# Pre-format display columns — no lambda formatters
zip_agg["hhi_display"]       = zip_agg["zcta_hhi"].apply(
    lambda x: f"${x:,.0f}")
zip_agg["price_display"]     = zip_agg["median_sale_price"].apply(
    lambda x: f"${x:,.0f}")
zip_agg["afford_display"]    = zip_agg["afford_ratio_zip"].apply(
    lambda x: f"{x:.1%}")
zip_agg["midlux_display"]    = zip_agg["pct_mid_luxury"].apply(
    lambda x: f"{x:.1f}%")
zip_agg["trans_display"]     = zip_agg["transactions"].apply(
    lambda x: f"{int(x):,}")

print(f"Zip codes for HHI map: {len(zip_agg)}")
print(f"HHI range: ${zip_agg['zcta_hhi'].min():,.0f}"
      f" — ${zip_agg['zcta_hhi'].max():,.0f}")

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

# ── Drop rows with missing HHI before mapping ─────────────────────────────────
gdf_merged = gdf_merged[gdf_merged["zcta_hhi"].notna()].copy()
print(f"Zip codes after dropping missing HHI: {len(gdf_merged)}")

# ── Build HHI choropleth map ──────────────────────────────────────────────────
m = folium.Map(
    location   = [39.90, -86.16],
    zoom_start = 10,
    tiles      = "CartoDB positron"
)

# Color scale: light blue → dark blue (income gradient)
# Distinct from sale price map (orange/red) for side-by-side comparison
colormap = LinearColormap(
    colors  = ["#EFF3FF", "#BDD7E7", "#6BAED6",
               "#3182BD", "#08519C", "#08306B"],
    vmin    = zip_agg["zcta_hhi"].quantile(0.05),
    vmax    = zip_agg["zcta_hhi"].quantile(0.95),
    caption = "Median household income 2023 (ACS 5-year)"
)

# Zip polygons
folium.GeoJson(
    gdf_merged,
    style_function = lambda feature: {
        "fillColor":   colormap(
            feature["properties"]["zcta_hhi"]
        ),
        "color":       "#555555",
        "weight":      0.8,
        "fillOpacity": 0.75
    },
    tooltip = folium.GeoJsonTooltip(
        fields  = ["zip_code", "county",
                   "hhi_display",
                   "price_display",
                   "afford_display",
                   "midlux_display",
                   "trans_display"],
        aliases = ["ZIP", "County",
                   "Median HHI",
                   "Median Sale Price",
                   "Afford. Ratio (6.2%)",
                   "% Mid-luxury",
                   "Transactions"],
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
        "color":       "#222222",
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
        Median Household Income by ZIP Code — Indianapolis Metro
    </div>
    <div style="font-size:10px;color:#666;margin-top:2px">
        ACS 2023 5-year estimates |
        Hover for sale price, affordability ratio, and mid-luxury share
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
import os
os.makedirs(ROOT / "outputs/interactive", exist_ok=True)
m.save(ROOT / "outputs/interactive/heatmap_hhi.html")
print("\nSaved outputs/interactive/heatmap_hhi.html")

print("\nTop 10 zip codes by HHI:")
print(
    zip_agg.sort_values("zcta_hhi", ascending=False)
    .head(10)[["zip_code", "county",
               "hhi_display", "price_display",
               "afford_display", "midlux_display"]]
    .to_string(index=False)
)
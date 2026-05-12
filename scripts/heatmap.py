import pandas as pd
import geopandas as gpd
import folium
import requests
import numpy as np
from branca.colormap import LinearColormap
from folium.plugins import MiniMap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── Load zip code summary ─────────────────────────────────────────────────────
zip_data = pd.read_csv(ROOT / "data/processed/zip_median_prices.csv")
zip_data["zip_code"] = zip_data["zip_code"].astype(str).str.zfill(5)
zip_data = zip_data[zip_data["zip_code"] != "00000"]

zip_agg = (
    zip_data
    .groupby("zip_code")
    .apply(lambda x: pd.Series({
        "median_sale_price": np.average(
            x["median_sale_price"], weights=x["transactions"]
        ),
        "transactions":   x["transactions"].sum(),
        "pct_mid_luxury": np.average(
            x["pct_mid_luxury"], weights=x["transactions"]
        ),
        "county": x.loc[x["transactions"].idxmax(), "county"]
    }))
    .reset_index()
)

# Format display columns — no lambdas, plain strings
zip_agg["price_display"]     = zip_agg["median_sale_price"].apply(
    lambda x: f"${x:,.0f}")
zip_agg["midlux_display"]    = zip_agg["pct_mid_luxury"].apply(
    lambda x: f"{x:.1f}%")
zip_agg["trans_display"]     = zip_agg["transactions"].apply(
    lambda x: f"{int(x):,}")

print(f"Zip codes: {len(zip_agg)}")
print(f"Price range: ${zip_agg['median_sale_price'].min():,.0f}"
      f" — ${zip_agg['median_sale_price'].max():,.0f}")

# ── Load Indiana zip code boundaries ─────────────────────────────────────────
print("\nDownloading zip code boundaries...")
tiger_url = (
    "https://raw.githubusercontent.com/OpenDataDE/"
    "State-zip-code-GeoJSON/master/in_indiana_zip_codes_geo.min.json"
)
response = requests.get(tiger_url, timeout=30)
gdf = gpd.read_file(response.text.encode(), driver="GeoJSON")

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

# ── Build map ─────────────────────────────────────────────────────────────────
m = folium.Map(
    location   = [39.90, -86.16],
    zoom_start = 10,
    tiles      = "CartoDB positron"
)

colormap = LinearColormap(
    colors  = ["#FFF7BC", "#FEC44F", "#FE9929",
               "#EC7014", "#CC4C02", "#8C2D04"],
    vmin    = zip_agg["median_sale_price"].quantile(0.05),
    vmax    = zip_agg["median_sale_price"].quantile(0.95),
    caption = "Median sale price 2021–2025"
)

# Zip polygons with tooltip — no formatter lambdas
folium.GeoJson(
    gdf_merged,
    style_function = lambda feature: {
        "fillColor":   colormap(
            feature["properties"]["median_sale_price"]
        ),
        "color":       "#555555",
        "weight":      0.8,
        "fillOpacity": 0.75
    },
    tooltip = folium.GeoJsonTooltip(
        fields  = ["zip_code", "county",
                   "price_display",
                   "trans_display",
                   "midlux_display"],
        aliases = ["ZIP", "County",
                   "Median Price",
                   "Transactions",
                   "% Mid-luxury"],
        localize = False
    )
).add_to(m)

# ── County boundary outlines ──────────────────────────────────────────────────
county_url = (
    "https://raw.githubusercontent.com/plotly/datasets/"
    "master/geojson-counties-fips.json"
)
county_resp  = requests.get(county_url, timeout=30)
counties_gdf = gpd.read_file(
    county_resp.text.encode(), driver="GeoJSON"
)
target_fips = ["18097", "18057", "18011", "18063", "18081"]
counties_subset = counties_gdf[
    counties_gdf["id"].isin(target_fips)
].to_crs(epsg=4326)

folium.GeoJson(
    counties_subset,
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

# ── Price labels on top 5 zip codes ──────────────────────────────────────────
gdf_proj  = gdf_merged.to_crs(epsg=3857)
top5_zips = zip_agg.nlargest(5, "median_sale_price")["zip_code"].tolist()
gdf_top5  = gdf_proj[gdf_proj["zip_code"].isin(top5_zips)].copy()

for _, row in gdf_top5.iterrows():
    # Calculate centroid in projected CRS then convert coordinates
    centroid    = row.geometry.centroid
    centroid_gdf = gpd.GeoSeries([centroid], crs=3857).to_crs(4326)
    lon = centroid_gdf.iloc[0].x
    lat = centroid_gdf.iloc[0].y

    folium.Marker(
        location = [lat, lon],
        icon     = folium.DivIcon(
            html = f"""<div style="
                font-size:10px;font-weight:bold;color:#8C2D04;
                background:rgba(255,255,255,0.85);
                padding:2px 5px;border-radius:3px;
                white-space:nowrap">
                {row['zip_code']}<br>${row['median_sale_price']/1000:.0f}K
            </div>""",
            icon_size   = (70, 28),
            icon_anchor = (35, 14)
        )
    ).add_to(m)

# ── Title ─────────────────────────────────────────────────────────────────────
title_html = """
<div style="position:fixed;top:10px;left:50%;
    transform:translateX(-50%);z-index:1000;
    background:white;padding:10px 20px;
    border-radius:6px;box-shadow:0 2px 6px rgba(0,0,0,0.3);
    font-family:Arial,sans-serif;text-align:center">
    <div style="font-size:16px;font-weight:bold;color:#333">
        Median Sale Price by ZIP Code — Indianapolis Metro
    </div>
    <div style="font-size:12px;color:#666;margin-top:4px">
        2021–2025 | Single family residential |
        Source: STATS Indiana SDF deed records (N=284,986)
    </div>
</div>"""
m.get_root().html.add_child(folium.Element(title_html))

colormap.add_to(m)

# ── Inset map: Indiana state with study area highlighted ──────────────────────
# Reuse the counties GeoJSON already downloaded above
indiana_gdf = counties_gdf.copy()

indiana_only = indiana_gdf[
    indiana_gdf["id"].str.startswith("18")
].to_crs(epsg=4326)

study_fips    = ["18097", "18057", "18011", "18063", "18081"]
study_area    = indiana_only[indiana_only["id"].isin(study_fips)]
other_indiana = indiana_only[~indiana_only["id"].isin(study_fips)]

inset = folium.Map(
    location          = [39.9, -86.3],
    zoom_start        = 6,
    tiles             = "CartoDB positron",
    zoom_control      = False,
    scrollWheelZoom   = False,
    dragging          = False,
    doubleClickZoom   = False,
    attributionControl = False
)

# Other Indiana counties — white fill with visible grey border
folium.GeoJson(
    other_indiana,
    style_function = lambda x: {
        "fillColor":   "#FFFFFF",
        "color":       "#888888",
        "weight":      0.8,
        "fillOpacity": 0.9
    }
).add_to(inset)

# Study area — bright red so it pops
folium.GeoJson(
    study_area,
    style_function = lambda x: {
        "fillColor":   "#E41A1C",
        "color":       "#333333",
        "weight":      1.5,
        "fillOpacity": 0.85
    }
).add_to(inset)

inset_html = inset.get_root().render()

# Larger inset — 220x240px
inset_element = f"""
<div style="
    position: fixed;
    bottom: 30px;
    left: 10px;
    z-index: 1000;
    width: 220px;
    height: 260px;
    border: 2px solid #333;
    border-radius: 4px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
    background: white;">
    <div style="
        position:absolute;top:0;left:0;right:0;
        background:#333333;color:white;
        font-size:11px;font-family:Arial;font-weight:bold;
        padding:4px 8px;z-index:10;
        letter-spacing:0.5px;">
        &#9679; Study area within Indiana
    </div>
    <iframe
        srcdoc='{inset_html.replace("'", "&apos;")}'
        style="width:100%;height:100%;border:none;margin-top:22px"
        scrolling="no">
    </iframe>
</div>
"""

m.get_root().html.add_child(folium.Element(inset_element))

# ── Save ──────────────────────────────────────────────────────────────────────
import os
os.makedirs(ROOT / "outputs/interactive", exist_ok=True)
m.save(ROOT / "outputs/interactive/heatmap_interactive.html")
print("\nSaved outputs/interactive/heatmap_interactive.html")
print("Open in browser and screenshot for presentation")

print("\nTop 10 zip codes by median price:")
print(
    zip_agg.sort_values("median_sale_price", ascending=False)
    .head(10)[["zip_code", "county",
               "price_display", "trans_display", "midlux_display"]]
    .to_string(index=False)
)
# pip install streamlit plotly geopandas

import json
import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px
import plotly.graph_objects as go
import requests
import numpy as np
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TARGET_FIPS = ["18097", "18057", "18011", "18063", "18081"]

MAP_CENTER = {"lat": 39.82, "lon": -86.20}
MAP_ZOOM   = 8.0

CITY_POINTS = [
    ("Indianapolis",  39.7684, -86.1581),
    ("Carmel",        39.9784, -86.1180),
    ("Fishers",       39.9567, -85.9669),
    ("Noblesville",   40.0456, -85.9669),
    ("Zionsville",    39.9506, -86.2661),
    ("Whitestown",    39.9914, -86.3522),
    ("Avon",          39.7626, -86.3994),
    ("Brownsburg",    39.8437, -86.3969),
    ("Greenwood",     39.6137, -86.1066),
    ("Plainfield",    39.7042, -86.3994),
    ("Mooresville",   39.6128, -86.3730),
    ("Franklin",      39.4806, -86.0558),
    ("Greenfield",    39.7870, -85.7697),
]

# ColorBrewer palettes matching the standalone heatmap scripts.
# Each list is [[normalized_position, color], ...] for Plotly's continuous colorscale.
HHI_COLORSCALE = [
    [0.0, "#C6DBEF"],
    [0.2, "#BDD7E7"],
    [0.4, "#6BAED6"],
    [0.6, "#3182BD"],
    [0.8, "#08519C"],
    [1.0, "#08306B"],
]

PRICE_COLORSCALE = [
    [0.0, "#FEE391"],
    [0.2, "#FEC44F"],
    [0.4, "#FE9929"],
    [0.6, "#EC7014"],
    [0.8, "#CC4C02"],
    [1.0, "#8C2D04"],
]

# 4-step RdBu colorscale; discrete steps at 3×, 4×, 5× within range [1, 6].
# Normalized breakpoints: (3-1)/(6-1)=0.40, (4-1)/5=0.60, (5-1)/5=0.80.
SQUEEZE_COLORSCALE = [
    [0.0, "#2166AC"],
    [0.4, "#2166AC"],
    [0.4, "#92C5DE"],
    [0.6, "#92C5DE"],
    [0.6, "#F4A582"],
    [0.8, "#F4A582"],
    [0.8, "#B2182B"],
    [1.0, "#B2182B"],
]


# ── Cached data loaders ───────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_zip_csv() -> pd.DataFrame:
    zip_data = pd.read_csv(ROOT / "data/processed/zip_median_prices.csv")
    zip_data["zip_code"] = zip_data["zip_code"].astype(str).str.zfill(5)
    return zip_data[zip_data["zip_code"] != "00000"].copy()


@st.cache_data(show_spinner=False)
def load_zip_geojson() -> dict:
    zip_cache = ROOT / "data/processed/indiana_zips.geojson"
    if zip_cache.exists():
        with open(zip_cache) as f:
            return json.load(f)
    response = requests.get(
        "https://raw.githubusercontent.com/OpenDataDE/"
        "State-zip-code-GeoJSON/master/in_indiana_zip_codes_geo.min.json",
        timeout=30,
    )
    data = response.json()
    with open(zip_cache, "w") as f:
        json.dump(data, f)
    return data


@st.cache_data(show_spinner=False)
def load_zip_geojson_simplified() -> dict:
    # Pre-simplified offline by scripts/build_simplified_geojson.py; loaded
    # straight from disk to skip the GeoPandas simplify pass at app start.
    with open(ROOT / "data/zip_geojson_simplified.json") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def load_county_boundaries() -> gpd.GeoDataFrame:
    county_cache = ROOT / "data/processed/counties_fips.geojson"
    if county_cache.exists():
        counties_gdf = gpd.read_file(county_cache)
    else:
        county_resp = requests.get(
            "https://raw.githubusercontent.com/plotly/datasets/"
            "master/geojson-counties-fips.json",
            timeout=60,
        )
        counties_gdf = gpd.read_file(county_resp.text.encode())
        counties_gdf.to_file(county_cache, driver="GeoJSON")
    return counties_gdf[counties_gdf["id"].isin(TARGET_FIPS)].to_crs(epsg=4326)


# ── Cached data prep (aggregation) ───────────────────────────────────────────
# Each function runs the groupby/apply once per unique zip_data input.
# Results are reused across radio button changes without re-aggregating.

@st.cache_data(show_spinner=False)
def _prep_hhi_data(zip_data: pd.DataFrame) -> tuple:
    zip_agg = (
        zip_data
        .groupby("zip_code")
        .apply(lambda x: pd.Series({
            "median_sale_price": np.average(
                x["median_sale_price"], weights=x["transactions"]
            ),
            "zcta_hhi": np.average(
                x["zcta_hhi"].fillna(x["zcta_hhi"].median()),
                weights=x["transactions"],
            ),
            "transactions":     x["transactions"].sum(),
            "pct_mid_luxury":   np.average(
                x["pct_mid_luxury"], weights=x["transactions"]
            ),
            "afford_ratio_zip": np.average(
                x["afford_ratio_zip"].fillna(0), weights=x["transactions"]
            ),
            "county": x.loc[x["transactions"].idxmax(), "county"],
        }))
        .reset_index()
    )
    zip_agg = zip_agg[zip_agg["zcta_hhi"].notna()].copy()
    zip_agg["hhi_display"]    = zip_agg["zcta_hhi"].apply(lambda x: f"${x:,.0f}")
    zip_agg["price_display"]  = zip_agg["median_sale_price"].apply(lambda x: f"${x:,.0f}")
    zip_agg["afford_display"] = zip_agg["afford_ratio_zip"].apply(lambda x: f"{x:.1%}")
    zip_agg["midlux_display"] = zip_agg["pct_mid_luxury"].apply(lambda x: f"{x:.1f}%")
    zip_agg["trans_display"]  = zip_agg["transactions"].apply(lambda x: f"{int(x):,}")
    vmin = zip_agg["zcta_hhi"].quantile(0.05)
    vmax = zip_agg["zcta_hhi"].quantile(0.95)
    return zip_agg, vmin, vmax


@st.cache_data(show_spinner=False)
def _prep_sale_price_data(zip_data: pd.DataFrame) -> tuple:
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
            "county": x.loc[x["transactions"].idxmax(), "county"],
        }))
        .reset_index()
    )
    zip_agg["price_display"]  = zip_agg["median_sale_price"].apply(lambda x: f"${x:,.0f}")
    zip_agg["midlux_display"] = zip_agg["pct_mid_luxury"].apply(lambda x: f"{x:.1f}%")
    zip_agg["trans_display"]  = zip_agg["transactions"].apply(lambda x: f"{int(x):,}")
    vmin = zip_agg["median_sale_price"].quantile(0.05)
    vmax = zip_agg["median_sale_price"].quantile(0.95)
    return zip_agg, vmin, vmax


@st.cache_data(show_spinner=False)
def _prep_squeeze_data(zip_data: pd.DataFrame) -> pd.DataFrame:
    zip_agg = (
        zip_data
        .groupby("zip_code")
        .apply(lambda x: pd.Series({
            "median_sale_price": np.average(
                x["median_sale_price"], weights=x["transactions"]
            ),
            "zcta_hhi": np.average(
                x["zcta_hhi"].fillna(x["zcta_hhi"].median()),
                weights=x["transactions"],
            ),
            "transactions": x["transactions"].sum(),
            "county":       x.loc[x["transactions"].idxmax(), "county"],
        }))
        .reset_index()
    )
    zip_agg = zip_agg[zip_agg["zcta_hhi"].notna() & (zip_agg["zcta_hhi"] > 0)].copy()
    zip_agg["stress_ratio"]  = zip_agg["median_sale_price"] / zip_agg["zcta_hhi"]
    zip_agg["hhi_display"]   = zip_agg["zcta_hhi"].apply(lambda x: f"${x:,.0f}")
    zip_agg["price_display"] = zip_agg["median_sale_price"].apply(lambda x: f"${x:,.0f}")
    zip_agg["ratio_display"] = zip_agg["stress_ratio"].apply(lambda x: f"{x:.1f}×")
    return zip_agg


# ── Shared helpers ────────────────────────────────────────────────────────────

def _county_outline_trace(counties_sub: gpd.GeoDataFrame) -> go.Scattermap:
    """Extract exterior ring coordinates from county polygons for a border overlay."""
    lats: list = []
    lons: list = []
    gdf_4326 = counties_sub.to_crs(epsg=4326)
    for geom in gdf_4326.geometry:
        rings = (
            [geom.exterior]
            if geom.geom_type == "Polygon"
            else [p.exterior for p in geom.geoms]
        )
        for ring in rings:
            xs, ys = ring.xy
            lons.extend(list(xs) + [None])
            lats.extend(list(ys) + [None])
    return go.Scattermap(
        lat=lats, lon=lons, mode="lines",
        line=dict(width=2.5, color="#222222"),
        hoverinfo="skip", showlegend=False,
    )


def _county_label_trace(counties_sub: gpd.GeoDataFrame) -> go.Scattermap:
    # representative_point() is guaranteed to lie inside the polygon, unlike
    # .centroid which can fall outside concave shapes.
    gdf_4326 = counties_sub.to_crs(epsg=4326)
    names: list = []
    lats: list = []
    lons: list = []
    for _, row in gdf_4326.iterrows():
        name = row.get("NAME", "")
        if not name:
            continue
        pt = row.geometry.representative_point()
        names.append(name)
        lats.append(pt.y)
        lons.append(pt.x)
    texts = [f"{n} County" for n in names]
    return go.Scattermap(
        lat=lats,
        lon=lons,
        mode="text",
        text=texts,
        textfont=dict(size=18, color="black"),
        textposition="middle center",
        hoverinfo="skip", showlegend=False,
    )


def _city_marker_trace() -> go.Scattermap:
    # Scattermapbox markers use Mapbox/Maki symbols; "circle-stroked" gives a hollow ring
    return go.Scattermap(
        lat=[c[1] for c in CITY_POINTS],
        lon=[c[2] for c in CITY_POINTS],
        mode="markers+text",
        text=[c[0] for c in CITY_POINTS],
        textposition="middle right",
        textfont=dict(size=8, color="#AAAAAA"),
        marker=dict(size=3, symbol="circle-stroked", color="#888"),
        hoverinfo="skip", showlegend=False,
    )


def _zip_centroid(geojson: dict, zip_code: str) -> tuple:
    """Return (lat, lon) mean centroid for a ZIP from GeoJSON polygon coordinates."""
    for feat in geojson["features"]:
        if feat.get("properties", {}).get("ZCTA5CE10") == zip_code:
            geom = feat["geometry"]
            ring = (
                geom["coordinates"][0]
                if geom["type"] == "Polygon"
                else max(geom["coordinates"], key=lambda p: len(p[0]))[0]
            )
            lons = [c[0] for c in ring]
            lats = [c[1] for c in ring]
            return sum(lats) / len(lats), sum(lons) / len(lons)
    return None, None


# ── Map builders ──────────────────────────────────────────────────────────────

def build_hhi_map(
    zip_data: pd.DataFrame,
    geojson: dict,
    _counties_sub: gpd.GeoDataFrame,
) -> go.Figure:
    zip_agg, vmin, vmax = _prep_hhi_data(zip_data)
    fig = px.choropleth_map(
        zip_agg,
        geojson=geojson,
        locations="zip_code",
        featureidkey="properties.ZCTA5CE10",
        color="zcta_hhi",
        color_continuous_scale=HHI_COLORSCALE,
        range_color=[vmin, vmax],
        map_style="carto-voyager",
        center=MAP_CENTER,
        zoom=MAP_ZOOM,
        opacity=0.88,
        custom_data=[
            "zip_code", "county", "hhi_display", "price_display",
            "afford_display", "midlux_display", "trans_display",
        ],
    )
    fig.update_traces(
        hovertemplate=(
            "<b>ZIP %{customdata[0]}</b> — %{customdata[1]}<br>"
            "Median HHI: %{customdata[2]}<br>"
            "Median Sale Price: %{customdata[3]}<br>"
            "Affordability Ratio: %{customdata[4]}<br>"
            "% Mid-luxury: %{customdata[5]}<br>"
            "Transactions: %{customdata[6]}"
            "<extra></extra>"
        )
    )
    fig.update_coloraxes(colorbar=dict(
        title=dict(text="Median HHI<br>(ACS 2023)", font=dict(size=11)),
        thickness=15, len=0.5,
        tickfont=dict(size=10),
        tickformat="$,.0f",
        x=1.01, y=0.5, xanchor="left", yanchor="middle",
    ))
    fig.add_trace(_county_outline_trace(_counties_sub))
    fig.add_trace(_city_marker_trace())
    fig.add_trace(_county_label_trace(_counties_sub))
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )
    return fig


def build_sale_price_map(
    zip_data: pd.DataFrame,
    geojson: dict,
    _counties_sub: gpd.GeoDataFrame,
) -> go.Figure:
    zip_agg, vmin, vmax = _prep_sale_price_data(zip_data)
    fig = px.choropleth_map(
        zip_agg,
        geojson=geojson,
        locations="zip_code",
        featureidkey="properties.ZCTA5CE10",
        color="median_sale_price",
        color_continuous_scale=PRICE_COLORSCALE,
        range_color=[vmin, vmax],
        map_style="carto-voyager",
        center=MAP_CENTER,
        zoom=MAP_ZOOM,
        opacity=0.88,
        custom_data=["zip_code", "county", "price_display", "trans_display", "midlux_display"],
    )
    fig.update_traces(
        hovertemplate=(
            "<b>ZIP %{customdata[0]}</b> — %{customdata[1]}<br>"
            "Median Price: %{customdata[2]}<br>"
            "Transactions: %{customdata[3]}<br>"
            "% Mid-luxury: %{customdata[4]}"
            "<extra></extra>"
        )
    )
    fig.update_coloraxes(colorbar=dict(
        title=dict(text="Median Sale Price<br>USD (2021–2025)", font=dict(size=11)),
        thickness=15, len=0.5,
        tickfont=dict(size=10),
        tickformat="$,.0f",
        x=1.01, y=0.5, xanchor="left", yanchor="middle",
    ))
    fig.add_trace(_county_outline_trace(_counties_sub))
    fig.add_trace(_city_marker_trace())
    fig.add_trace(_county_label_trace(_counties_sub))
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )
    return fig


def build_squeeze_map(
    zip_data: pd.DataFrame,
    geojson: dict,
    _counties_sub: gpd.GeoDataFrame,
) -> go.Figure:
    zip_agg = _prep_squeeze_data(zip_data)
    fig = px.choropleth_map(
        zip_agg,
        geojson=geojson,
        locations="zip_code",
        featureidkey="properties.ZCTA5CE10",
        color="stress_ratio",
        color_continuous_scale=SQUEEZE_COLORSCALE,
        range_color=[1.0, 6.0],
        map_style="carto-voyager",
        center=MAP_CENTER,
        zoom=MAP_ZOOM,
        opacity=0.88,
        custom_data=["zip_code", "county", "hhi_display", "price_display", "ratio_display"],
    )
    fig.update_traces(
        hovertemplate=(
            "<b>ZIP %{customdata[0]}</b> — %{customdata[1]}<br>"
            "Median HHI: %{customdata[2]}<br>"
            "Median Sale Price: %{customdata[3]}<br>"
            "Squeeze Ratio: %{customdata[4]}"
            "<extra></extra>"
        )
    )
    # Tick at 4× is labeled to mark the stress threshold
    fig.update_coloraxes(colorbar=dict(
        title=dict(text="Squeeze Ratio<br>(Price ÷ HHI)", font=dict(size=11)),
        thickness=15, len=0.5,
        tickfont=dict(size=10),
        tickvals=[1, 2, 3, 4, 5, 6],
        ticktext=["1×", "2×", "3×", "4× ◄stress", "5×", "6×"],
        x=1.01, y=0.5, xanchor="left", yanchor="middle",
    ))
    fig.add_trace(_county_outline_trace(_counties_sub))
    fig.add_trace(_city_marker_trace())
    fig.add_trace(_county_label_trace(_counties_sub))
    # Annotate the highest-stress ZIP dynamically so it updates with the data.
    top_row = zip_agg.loc[zip_agg["stress_ratio"].idxmax()]
    top_lat, top_lon = _zip_centroid(geojson, top_row["zip_code"])
    if top_lat is not None:
        fig.add_trace(go.Scattermap(
            lat=[top_lat], lon=[top_lon],
            mode="markers+text",
            text=[f"{top_row['ratio_display']} — highest stress in metro"],
            textposition="top right",
            marker=dict(size=8, color="red", symbol="circle"),
            textfont=dict(size=11, color="red"),
            hoverinfo="skip", showlegend=False,
        ))
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )
    return fig


# ── App layout ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Indianapolis Housing Market Analysis",
    page_icon="🏠",
    layout="wide",
)

st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
[data-testid="stToolbar"] {visibility: hidden;}
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"] { border-radius: 20px; }
.mapboxgl-ctrl-attrib { font-size: 9px !important; opacity: 0.5 !important; }
.maplibregl-ctrl-attrib { font-size: 9px !important; opacity: 0.5 !important; }
</style>
""", unsafe_allow_html=True)

st.title("Indianapolis Housing Market Analysis")

MAP_OPTIONS = [
    "Median Household Income",
    "Median Sale Price",
    "Housing Squeeze Index",
]

MAP_TITLES = {
    "Median Household Income": "Median Household Income · ACS 2023 5-year estimates",
    "Median Sale Price": "Median Sale Price · 2021–2025 (STATS Indiana SDF)",
    "Housing Squeeze Index": "Housing Squeeze Index · 2021–2025 | 4× = stress threshold",
}

LEDE = {
    "Median Household Income": (
        "Hamilton County leads the metro in household income, with several ZIP codes exceeding "
        "$120,000. Marion County's urban core clusters below $60,000 — a gap that shapes who "
        "can afford to buy."
    ),
    "Median Sale Price": (
        "Median sale prices in Hamilton County's Carmel and Fishers ZIPs surpassed $500,000 "
        "between 2021 and 2025. Prices in Johnson County's outer ZIPs remain below $250,000 — "
        "for now."
    ),
    "Housing Squeeze Index": (
        "A price-to-income ratio above 4× signals housing stress. Several eastern Marion County "
        "ZIPs have crossed that threshold. One ZIP exceeds 5.7× — the highest in the metro."
    ),
}

ABOUT_TEXT = (
    "Sale price data covers 198,407 arm's-length residential property transfers recorded in "
    "Boone, Hamilton, Hendricks, Marion, and Johnson counties between 2021 and 2025, sourced "
    "from STATS Indiana deed records. Household income figures are ZIP-code level medians from "
    "the U.S. Census Bureau's 2023 American Community Survey 5-year estimates. The "
    "price-to-income ratio divides median sale price by median household income for each ZIP "
    "code. Economists generally consider a ratio above 4× an indicator of housing affordability "
    "stress."
)

if "selected_map" not in st.session_state:
    st.session_state["selected_map"] = MAP_OPTIONS[0]

col1, col2, col3 = st.columns(3)
with col1:
    if st.button(
        MAP_OPTIONS[0],
        use_container_width=True,
        type="primary" if st.session_state["selected_map"] == MAP_OPTIONS[0] else "secondary",
    ):
        st.session_state["selected_map"] = MAP_OPTIONS[0]
        st.rerun()
with col2:
    if st.button(
        MAP_OPTIONS[1],
        use_container_width=True,
        type="primary" if st.session_state["selected_map"] == MAP_OPTIONS[1] else "secondary",
    ):
        st.session_state["selected_map"] = MAP_OPTIONS[1]
        st.rerun()
with col3:
    if st.button(
        MAP_OPTIONS[2],
        use_container_width=True,
        type="primary" if st.session_state["selected_map"] == MAP_OPTIONS[2] else "secondary",
    ):
        st.session_state["selected_map"] = MAP_OPTIONS[2]
        st.rerun()

selected = st.session_state["selected_map"]

st.markdown(
    f'<p style="font-size:1rem;color:inherit;line-height:1.6;'
    f'max-width:720px;margin:0 auto 0.5rem auto;">{LEDE[selected]}</p>',
    unsafe_allow_html=True,
)

zip_data     = load_zip_csv()
geojson      = load_zip_geojson_simplified()
counties_sub = load_county_boundaries()

if selected == MAP_OPTIONS[0]:
    fig = build_hhi_map(zip_data, geojson, counties_sub)
elif selected == MAP_OPTIONS[1]:
    fig = build_sale_price_map(zip_data, geojson, counties_sub)
else:
    fig = build_squeeze_map(zip_data, geojson, counties_sub)

st.markdown(
    f"<p style='text-align:center; font-size:0.95rem; line-height:1.4; "
    f"color:inherit; margin-bottom:0.25rem;'>{MAP_TITLES[selected]}</p>",
    unsafe_allow_html=True,
)

st.plotly_chart(
    fig,
    width="stretch",
    config={"scrollZoom": True, "displayModeBar": False},
)

with st.expander("About this data", expanded=False):
    st.markdown(ABOUT_TEXT)

"""City-based core geographies for the Minnesota squeeze comparison.

Marion County is consolidated with the city of Indianapolis, while Hennepin
and Ramsey each combine a core city with affluent suburbs. These helpers
relabel Hennepin and Ramsey sales as Minneapolis, St. Paul, or the county
balance (from the eCRV city code) and build the per-area income and
population controls the published transaction models need.
"""

from __future__ import annotations

import pandas as pd
import requests

ACS_URL = "https://api.census.gov/data/2023/acs/acs5"
ACS_FIELDS = "NAME,B19013_001E,B01003_001E"
MN_STATE = "27"
COUNTY_CODES = {
    "003": "Anoka", "019": "Carver", "037": "Dakota", "053": "Hennepin",
    "123": "Ramsey", "139": "Scott", "163": "Washington",
}
PLACE_CODES = {"43000": "Minneapolis", "58000": "St. Paul"}
COLLAR = ["Anoka", "Carver", "Dakota", "Scott", "Washington"]
CORE_CITY_UNITS = {
    ("Hennepin", "CORE_CITY"): "Minneapolis",
    ("Hennepin", "COUNTY_BALANCE"): "Hennepin balance",
    ("Ramsey", "CORE_CITY"): "St. Paul",
    ("Ramsey", "COUNTY_BALANCE"): "Ramsey balance",
}
# Each geography names its core areas and its suburban areas. Areas in
# neither list (for example, Minneapolis when St. Paul is the only core) are
# excluded from that comparison.
GEOGRAPHIES = {
    "stpaul_vs_collar": (["St. Paul"], COLLAR),
    "core_cities_vs_collar": (["Minneapolis", "St. Paul"], COLLAR),
    "core_cities_vs_all_suburbs": (
        ["Minneapolis", "St. Paul"], COLLAR + ["Hennepin balance", "Ramsey balance"]
    ),
}


def relabel_core_cities(sample: pd.DataFrame) -> pd.DataFrame:
    """Replace Hennepin and Ramsey with city or balance units.

    Sales whose ``core_city_status`` is not core city or county balance
    (mixed or unknown) cannot be placed and are dropped.
    """
    frame = sample.copy()
    core = frame["county"].isin(["Hennepin", "Ramsey"])
    units = [
        CORE_CITY_UNITS.get(key)
        for key in zip(frame.loc[core, "county"], frame.loc[core, "core_city_status"])
    ]
    frame.loc[core, "county"] = units
    return frame[frame["county"].notna()].reset_index(drop=True)


def fetch_acs_controls(api_key: str) -> pd.DataFrame:
    """Pull ACS 2023 5-year median household income and population.

    Returns one row per study county and per core city, with ``area`` names
    matching the relabeled sample.
    """
    if not api_key:
        raise EnvironmentError("CENSUS_API_KEY is not set")
    rows = []
    for geography, codes in (("county", COUNTY_CODES), ("place", PLACE_CODES)):
        response = requests.get(ACS_URL, params={
            "get": ACS_FIELDS, "for": f"{geography}:{','.join(codes)}",
            "in": f"state:{MN_STATE}", "key": api_key,
        }, timeout=60)
        response.raise_for_status()
        raw = response.json()
        frame = pd.DataFrame(raw[1:], columns=raw[0])
        frame["area"] = frame[geography].map(codes)
        frame["kind"] = geography
        rows.append(frame)
    acs = pd.concat(rows, ignore_index=True)
    return pd.DataFrame({
        "area": acs["area"], "kind": acs["kind"],
        "median_hhi": pd.to_numeric(acs["B19013_001E"]),
        "population": pd.to_numeric(acs["B01003_001E"]),
    })


def geography_controls(acs: pd.DataFrame, geography: str) -> pd.DataFrame:
    """Build the county-controls table for one comparison geography.

    Cities use their own ACS income and population. A county balance uses
    its parent county's median income, because a median cannot be split,
    and the county population minus the city population.
    """
    core, suburbs = GEOGRAPHIES[geography]
    values = acs.set_index("area")
    balance_parent = {"Hennepin balance": ("Hennepin", "Minneapolis"),
                      "Ramsey balance": ("Ramsey", "St. Paul")}
    rows = []
    for area, role in [(a, "metro") for a in core] + [(a, "suburb") for a in suburbs]:
        if area in balance_parent:
            county, city = balance_parent[area]
            hhi = values.loc[county, "median_hhi"]
            population = values.loc[county, "population"] - values.loc[city, "population"]
        else:
            hhi = values.loc[area, "median_hhi"]
            population = values.loc[area, "population"]
        rows.append({"county": area, "geography": role,
                     "median_hhi": int(hhi), "population": int(population)})
    return pd.DataFrame(rows)

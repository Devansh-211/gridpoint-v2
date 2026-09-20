"""One-time data acquisition script for GRIDPOINT geodata sampler.
Downloads the cities table from dr5hn/countries-states-cities-database (mirrored on Kaggle liewyousheng/geolocation).
Filters down to Indian cities/towns and writes data/cities_geodata.csv.
Licensed under Open Database License (ODbL) v1.0.
"""

import gzip
import io
import os
import urllib.request
import pandas as pd

DOWNLOAD_URL = "https://github.com/dr5hn/countries-states-cities-database/releases/download/v3.2-export.7/csv-cities.csv.gz"
OUTPUT_PATH = os.path.join("data", "cities_geodata.csv")


def download_and_filter_cities():
    print(f"Fetching cities table from {DOWNLOAD_URL}...")
    req = urllib.request.Request(DOWNLOAD_URL, headers={"User-Agent": "GRIDPOINT-Geodata-Loader/1.0"})
    with urllib.request.urlopen(req) as resp:
        compressed = resp.read()

    print(f"Downloaded {len(compressed):,} compressed bytes. Decompressing...")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as gz:
        df = pd.read_csv(gz)

    print(f"Full dataset contains {len(df):,} cities.")

    # Filter for India (country_code == 'IN')
    in_df = df[df["country_code"] == "IN"].copy()
    states_count = in_df["state_name"].nunique()
    print(f"Filtered to {len(in_df):,} Indian cities across {states_count} states/UTs.")

    cols = [
        "id", "name", "state_id", "state_code", "state_name",
        "country_id", "country_code", "country_name",
        "latitude", "longitude", "wikiDataId"
    ]
    # Handle column case drift if wikiDataId or wikidataid
    found_cols = []
    for col in cols:
        if col in in_df.columns:
            found_cols.append(col)
        elif col.lower() in in_df.columns:
            found_cols.append(col.lower())

    out_df = in_df[found_cols].copy()
    out_df.rename(columns={"wikiDataId": "wikidataid", "wikiDataID": "wikidataid"}, inplace=True)

    os.makedirs("data", exist_ok=True)
    out_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    size_bytes = os.path.getsize(OUTPUT_PATH)
    print(f"Successfully saved {len(out_df):,} rows to {OUTPUT_PATH} ({size_bytes:,} bytes).")


if __name__ == "__main__":
    download_and_filter_cities()

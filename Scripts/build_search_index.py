"""
Builds maps/lake_search_index.json: one compact row per searchable lake, so
the search page filters ~1k rows in memory instead of fetching 525 bundles.

Per lake: name, acres, max depth, clarity, campsite count, and for each fish
species the largest fish sampled (inches) and mean CPUE across surveys.
A lake is included if it has fisheries data OR at least one campsite.
Fisheries data is shared across every unique_guid with the same dowlknum
(same rule as build_fisheries_bundles.py).
"""
import json
from pathlib import Path
import pandas as pd

LAKES_IN = "../../Data/processed/bwca_lakes.parquet"
CAMPS_IN = "../../Data/processed/bwca_campsites_river.parquet"
FISH_DIR = Path("../../Data/fisheries")
OUT = "../../maps/lake_search_index.json"


def norm_dow(s):
    """DOW numbers as 8-char text, whatever dtype the file stored them in
    (int, float like 16002600.0, or text) - a dtype mismatch otherwise makes
    the join match nothing, with no error."""
    return (s.astype("string").str.strip()
            .str.replace(r"\.0$", "", regex=True).str.zfill(8))


def main():
    lakes = pd.read_parquet(LAKES_IN, columns=["unique_guid", "dowlknum", "pw_basin_name"])
    info = pd.read_parquet(FISH_DIR / "dnr_lake_info.parquet")
    lengths = pd.read_parquet(FISH_DIR / "dnr_fish_lengths.parquet")
    catches = pd.read_parquet(FISH_DIR / "dnr_fish_catches.parquet")
    for df in (lakes, info, lengths, catches):
        df["dowlknum"] = norm_dow(df["dowlknum"])
    info = info.set_index("dowlknum")

    overlap = len(set(lakes["dowlknum"].dropna()) & set(info.index))
    print(f"DOW numbers: {len(info)} in fisheries info, {overlap} found in bwca_lakes")
    if overlap == 0:
        raise SystemExit("No fisheries DOW numbers match bwca_lakes - not writing an empty index. "
                         f"Sample lakes: {lakes['dowlknum'].dropna().head(3).tolist()}, "
                         f"sample fisheries: {list(info.index[:3])}")

    max_len = lengths.groupby(["dowlknum", "species"])["length_inches"].max()
    cpue = catches.groupby(["dowlknum", "species"])["cpue"].mean()
    species_by_dow = {}
    for (dow, sp), ln in max_len.items():
        species_by_dow.setdefault(dow, {})[sp] = [int(ln), round(float(cpue.get((dow, sp), 0)), 2)]

    camps = {}
    if Path(CAMPS_IN).exists():
        c = pd.read_parquet(CAMPS_IN, columns=["lake_unique_guid", "water_type_final"])
        camps = c[c["water_type_final"] == "lake"]["lake_unique_guid"].value_counts().to_dict()
    else:
        print("campsites file not found - campsite counts will be 0")

    def num(v):
        return None if pd.isna(v) or v == 0 else round(float(v), 1)

    rows = []
    for r in lakes.itertuples():
        dow = r.dowlknum
        has_fish = isinstance(dow, str) and dow in info.index
        n_camps = int(camps.get(r.unique_guid, 0))
        if not has_fish and n_camps == 0:
            continue
        row = {"g": r.unique_guid, "n": r.pw_basin_name or "Unnamed", "cs": n_camps}
        if has_fish:
            i = info.loc[dow]
            row.update(ac=num(i["area_acres"]), md=num(i["max_depth_ft"]),
                       cl=num(i["average_water_clarity_ft"]), sp=species_by_dow.get(dow, {}))
        rows.append(row)

    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    json.dump(rows, open(OUT, "w"), separators=(",", ":"))
    print(f"{len(rows)} lakes ({sum(1 for r in rows if 'sp' in r)} with fish data, "
          f"{sum(1 for r in rows if r['cs'])} with campsites) -> {OUT}")


if __name__ == "__main__":
    main()
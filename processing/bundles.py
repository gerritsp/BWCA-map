import json
import pandas as pd
import geopandas as gpd

lakes = pd.read_parquet("../Data/processed/bwca_lakes.parquet",
                        columns=["unique_guid", "dowlknum", "pw_basin_name"])

# pick a lake by name and load its bundle
guid = lakes.loc[lakes["pw_basin_name"] == "Saganaga", "unique_guid"].iloc[0]
bundle = json.load(open(f"../maps/fisheries/{guid}.json"))

print(bundle.keys())
print(bundle["lake_info"])
print(len(bundle["fish_catches"]), "catch rows,",
      len(bundle["surveys"]), "surveys,",
      len(bundle["water_clarity"]), "clarity readings")
print(bundle["fish_catches"])

# lakes = gpd.read_parquet("../Data/processed/bwca_lakes.parquet")
# info = pd.read_parquet("../Data/processed/fisheries/dnr_lake_info.parquet", columns=["dowlknum"])
#
# lakes["has_fisheries_data"] = lakes["dowlknum"].isin(info["dowlknum"])
# print(lakes["has_fisheries_data"].sum())


def load_fisheries_dows():
    info = pd.read_parquet("../Data/processed/fisheries/dnr_lake_info.parquet", columns=["dowlknum"])
    return set(info["dowlknum"])

# inside lakes_geojson():
# fisheries_dows = load_fisheries_dows()
# for lake in load_fisheries_dows():
#     "has_fisheries_data": lake.dowlknum in fisheries_dows,
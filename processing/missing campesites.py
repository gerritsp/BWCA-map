import geopandas as gpd
raw_campesites = gpd.read_file("../Data/Campsites/USFS R09 SNF BWCA Wilderness Campsites Public fgdb.gdb",layer="Campsites")
processed = gpd.read_parquet("../Data/processed/old/bwca_campsites.parquet")
lakes = gpd.read_parquet("../Data/processed/bwca_lakes.parquet")
rivers = gpd.read_parquet("../Data/processed/old/bwca_rivers.parquet")
#
# print(len(processed))
# print(raw["STATUS"].unique())
# print(len(raw[raw["STATUS"]== "deommissioned"]))
# print(len(raw[raw["STATUS"]== "open"]))
# print(len(processed))
# print(len(raw))
# raw_ids = set(raw["CSITENO"])
# processed_ids = set(processed["CSITENO"])
#
# missing_ids = raw_ids - processed_ids
#
# print("Raw:", len(raw))
# print("Processed:", len(processed))
# print("Missing:", len(missing_ids))
#
# print(sorted(missing_ids))
# print(processed["STATUS"].value_counts())
# print("RAW")
# print(raw["STATUS"].value_counts())
#
# print("\nPROCESSED")
# print(processed["STATUS"].value_counts())
#
# print("\nRaw IDs:", len(raw["CSITENO"].unique()))
# print("Processed IDs:", len(processed["CSITENO"].unique()))
#
# print("\nMissing from processed:")
# print(sorted(set(raw["CSITENO"]) - set(processed["CSITENO"])))

print("\nClosed/decommissioned in processed:")
print(
    processed[
        processed["STATUS"].isin(["closed", "decommissioned"])
    ][["CSITENO", "STATUS", "LAKE_NAME"]]
)
print("RAW rows:", len(raw_campesites))
print("RAW unique CSITENO:", raw_campesites["CSITENO"].nunique())

print("\nRAW duplicate CSITENO:")
print(
    raw_campesites[raw_campesites["CSITENO"].duplicated(keep=False)]
    .sort_values("CSITENO")[["CSITENO", "STATUS", "LAKE_NAME"]]
)
print("\nPROCESSED rows:", len(processed))
print("PROCESSED unique CSITENO:", processed["CSITENO"].nunique())

print("\nPROCESSED duplicate CSITENO:")
print(
    processed[processed["CSITENO"].duplicated(keep=False)]
    .sort_values("CSITENO")[["CSITENO", "STATUS", "LAKE_NAME"]]
)
print(raw_campesites[["CSITENO", "LAKE_NAME"]].head(20))
print(raw_campesites["CSITENO"].value_counts().head(20))
print(raw_campesites.groupby("CSITENO").size().sort_values(ascending=False).head(20))

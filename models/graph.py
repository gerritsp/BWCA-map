import geopandas as gpd

from Campsite import Campsite
from Lake import Lake

gdf = gpd.read_parquet("../Data/processed/bwca_campsites.parquet")
lake_df = gpd.read_parquet("../Data/processed/bwca_lakes.parquet")

lakes = {}

for _, row in lake_df.iterrows():

    lake = Lake(
        fw_id=row["fw_id"],
        name=row["map_label"],
        geometry=row.geometry,
        acres=row["acres"],
        shoreline_miles=row["shore_mi"]
    )

    lakes[lake.fw_id] = lake

campsites = []
unmatched = []

for _, row in gdf.iterrows():

    campsite = Campsite(

        camp_id=row["camp_id"],

        site_number=row["CSITENO"],

        lake_name=row["LAKE_NAME"],

        fw_id=row["fw_id"],

        status=row["STATUS"],

        district=row["District"],

        geometry=row.geometry

    )
    if campsite.fw_id in lakes:
        campsites.append(campsite)
    else:
        unmatched.append(campsite)

for campsite in campsites:

    if campsite.fw_id in lakes:

        lake = lakes[campsite.fw_id]

        campsite.lake = lake

        lake.campsites.append(campsite)


knife = lakes[3731]

print(len(knife.campsites))
camp = knife.campsites[0]

print(camp.site_number)

print(camp.lake.name)
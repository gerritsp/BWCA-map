import geopandas as gpd

from Campsite import Campsite

gdf = gpd.read_parquet("../Data/processed/bwca_campsites.parquet")

for _, row in gdf.iterrows():

    campsite = Campsite(
        camp_id=row["camp_id"],
        site_number=row["CSITENO"],
        lake_name=row["LAKE_NAME"],
        status=row["STATUS"],
        district=row["District"],
        geometry=row.geometry
    )

    print(campsite)
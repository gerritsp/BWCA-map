import geopandas as gpd
import pyogrio
import os
from Campsite import Campsite

layers = pyogrio.list_layers(
    r"Data/Campsites/USFS R09 SNF BWCA Wilderness Campsites Public fgdb.gdb"
)
water_layers = pyogrio.list_layers(
    "data/lakes/water_dnr_hydrography.gdb"
)
gdf = gpd.read_file(
    r"Data/Campsites/USFS R09 SNF BWCA Wilderness Campsites Public fgdb.gdb",
    layer="Campsites"
)
# print(layers)


def create_Lake_objects(gdf):
    lakes = {}
    for lake_name in gdf["LAKE_NAME"].unique():
        lake_data = get_campsites_on_lake(lake_name)

        avg_x = lake_data.geometry.x.mean()
        avg_y = lake_data.geometry.y.mean()

        lakes[lake_name] = Lake(
            name=lake_name,
            x=avg_x,
            y=avg_y
        )
    return lakes
def create_campsites(gdf,lakes):
    campsites = []

    for _, row in gdf.iterrows():
        lake = lakes[row["LAKE_NAME"]]
        campsite = Campsite(
            site_number=row["CSITENO"],
            lake=lake,
            status=row["STATUS"],
            district=row["District"],
            utm_x=row.geometry.x,
            utm_y=row.geometry.y
        )

        lake.campsites.append(campsite)

def create_map(gdf):
    lakes = create_lake_objects(gdf)

    create_campsites(gdf, lakes)

    return lakes




def get_campsites_on_lake(lake):
    return gdf[
        (gdf["LAKE_NAME"] == lake)
        &
        (gdf["STATUS"] == "open")
    ]


def get_geometry(gdf):
    gdf["x"] = gdf.geometry.x
    gdf["y"] = gdf.geometry.y
    highest = gdf.loc[gdf["y"].idxmax()]
    lowest = gdf.loc[gdf["y"].idxmin()]
    east = gdf.loc[gdf["x"].idxmax()]
    west = gdf.loc[gdf["x"].idxmin()]
    return highest, lowest,east,west



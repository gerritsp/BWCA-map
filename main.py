import geopandas as gpd
import pyogrio
import os

layers = pyogrio.list_layers(
    r"Data/USFS R09 SNF BWCA Wilderness Campsites Public fgdb.gdb"
)

print(layers)


gdf = gpd.read_file(
    r"Data/USFS R09 SNF BWCA Wilderness Campsites Public fgdb.gdb",
    layer="Campsites"
)
def get_open_campsites():
    return gdf[gdf["STATUS"] == "open"]

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

# print(gdf.head())
# print()
# print(gdf.columns)
# print()
# print(gdf.info())
print(gdf["LAKE_NAME"].nunique())
# print(sorted(gdf["LAKE_NAME"].unique()))
# print(gdf[gdf["LAKE_NAME"].str.contains("Insula")])
#
# print(gdf["STATUS"].value_counts())
# print(get_open_campsites())
# Lake = "Davis Lake"
# print("campsites on " + Lake)
#
# print(get_campsites_on_lake(Lake))
print(gdf.crs)
print(get_geometry(gdf))
# print(highest["LatWGS84_DDM"])
# print(highest["LongWGS84_DDM"])


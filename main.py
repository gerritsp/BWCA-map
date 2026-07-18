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
Lake = "Davis Lake"
print("campsites on " + Lake)

print(get_campsites_on_lake(Lake))
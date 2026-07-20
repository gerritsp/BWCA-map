import geopandas as gpd
import pyogrio

layers = pyogrio.list_layers(
    r"../Data/Campsites/USFS R09 SNF BWCA Wilderness Campsites Public fgdb.gdb"
)
gdf = gpd.read_file(
    r"../Data/Campsites/USFS R09 SNF BWCA Wilderness Campsites Public fgdb.gdb",
    layer="Campsites"
)
print(layers)


def get_open_campsites():
    return gdf[gdf["STATUS"] == "open"]

def get_campsites_on_lake(lake):
    return gdf[
        (gdf["LAKE_NAME"] == lake)
        &
        (gdf["STATUS"] == "open")
    ]
def get_num_campsites(num):
    lake_name = []
    for lake in gdf["LAKE_NAME"].unique():
        x = get_campsites_on_lake(lake)
        if x.shape[0] == num:
            lake_name.append(lake)


    return  len(lake_name), lake_name

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
print(gdf["STATUS"].value_counts())
# print(get_open_campsites())
# Lake = "Amber Lake"
# print("campsites on " + Lake)
#
# print(get_campsites_on_lake(Lake))
# print(gdf.crs)
# print(get_geometry(gdf))
# print(highest["LatWGS84_DDM"])
# print(highest["LongWGS84_DDM"])
# print(get_num_campsites(1))
# counts = gdf["LAKE_NAME"].value_counts()
#
# print(counts[counts == 1])
# print(counts.head(10))


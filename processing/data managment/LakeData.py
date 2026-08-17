import geopandas as gpd
import pyogrio
import os
layers = pyogrio.list_layers(
    r"../../Data/Lakes/water_dnr_hydrography_uncompressed.gdb"
)
hydro = gpd.read_file(
    "../../Data/Lakes/water_dnr_hydrography_uncompressed.gdb",
    layer="dnr_rivers_and_streams"
)
boundary = gpd.read_file(
    "../../Data/Boundaries/bdry_boundary_waters_canoe_area/bdry_boundary_waters_canoe_area.gdb",
    layer="boundary_waters_canoe_area_wilderness"
)
streams = gpd.read_file(hydro, layer="dnr_rivers_and_streams")
boundary = boundary.to_crs(streams.crs)
bwca_streams = gpd.clip(streams, boundary)
print(len(bwca_streams))  # should be a small fraction of 133
# print(layers)
# print(gdf.geometry.iloc[0])
# print(gdf.geometry.iloc[0].geom_type)
# print(gdf.columns)
# print(len(gdf))
# print(gdf["in_lakefinder"].value_counts())
# print(gdf.iloc[0])
# lakefinder = gdf[gdf["in_lakefinder"] == "Y"]
# print(len(lakefinder))


# print(gdf["wb_class"].value_counts())
print(hydro.head())
print(hydro.info())
print(hydro.columns.to_list())
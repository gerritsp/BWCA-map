import geopandas as gpd
import pyogrio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HYDROGRAPHY = ROOT / "Data/Lakes/water_dnr_hydrography_uncompressed.gdb"
BOUNDARY = (
    ROOT / "Data/Boundaries/bdry_boundary_waters_canoe_area/"
    "bdry_boundary_waters_canoe_area.gdb"
)
layers = pyogrio.list_layers(
    HYDROGRAPHY
)
hydro = gpd.read_file(
    HYDROGRAPHY,
    layer="dnr_rivers_and_streams"
)
boundary = gpd.read_file(
    BOUNDARY,
    layer="boundary_waters_canoe_area_wilderness"
)
streams = hydro
boundary = boundary.to_crs(streams.crs)
wild = boundary.geometry.union_all()
bwca_streams = streams[streams.intersects(wild.buffer(2000))].copy()
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

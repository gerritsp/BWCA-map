import pyogrio
import geopandas as gpd

layers = pyogrio.list_layers(
    "../Data/Boundaries/bdry_boundary_waters_canoe_area/bdry_boundary_waters_canoe_area.gdb"
)


boundary = gpd.read_file(
    "../Data/Boundaries/bdry_boundary_waters_canoe_area/bdry_boundary_waters_canoe_area.gdb",
    layer="boundary_waters_canoe_area_wilderness"
)

# print(layers)
# print(boundary.head())
# print(boundary.crs)
# print(boundary.info())
print(boundary["BWCA_UNIT"])
print(boundary["BWCA_UNIT"].unique())
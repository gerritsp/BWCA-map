import geopandas as gpd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Data/Lakes/test.gpkg"
BOUNDARY = (
    ROOT / "Data/Boundaries/bdry_boundary_waters_canoe_area/"
    "bdry_boundary_waters_canoe_area.gdb"
)

gasket = gpd.read_file(SOURCE)
#
# print(gasket.crs)
# print(gasket.columns.tolist())
# print(gasket[["fw_id", "unique_id", "map_label", "acres", "shore_mi"]])
gasket = gasket.to_crs("EPSG:26915")

# Keep complete polygons that intersect the wilderness or its access buffer.
# Never clip a lake at the legal boundary: doing so removes shorelines needed
# to attach official entry points and portages.
boundary = gpd.read_file(
    BOUNDARY, layer="boundary_waters_canoe_area_wilderness"
).to_crs(gasket.crs)
wild = boundary.geometry.union_all()
gasket = gasket[gasket.intersects(wild.buffer(2000))].copy()
gasket["in_wilderness"] = gasket.intersects(wild)



print("Gasket:")
print(gasket[["fw_id", "unique_id", "map_label", "acres", "shore_mi"]])
print(gasket.crs)
# Make sure we're writing the complete 4,515-lake dataset
print("Number of lakes:", len(gasket))
print("Gasket:", len(gasket[gasket["map_label"] == "Gasket"]))

# Write updated lake dataset
gasket.to_parquet(ROOT / "Data/processed/bwca_lakes.parquet", index=False)

print("Lake parquet updated successfully.")

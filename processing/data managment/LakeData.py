import geopandas as gpd
import pyogrio
import os
layers = pyogrio.list_layers(
    r"../../Data/Lakes/water_dnr_hydrography_uncompressed.gdb"
)
hydro = gpd.read_file(
    "../../Data/Lakes/water_dnr_hydrography_uncompressed.gdb",
    layer="dnr_hydro_features_all"
)
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
for col in hydro.columns:
    if hydro[col].dtype == object:
        matches = hydro[
            hydro[col].astype(str).str.contains("gasket", case=False, na=False)
        ]

        if len(matches):
            print(f"\nFound in {col}")
            print(matches[[col]])
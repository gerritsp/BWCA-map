import geopandas as gpd
import pandas as pd
lakes = gpd.read_parquet(
    "../../Data/processed/bwca_lakes.parquet"
)

water = gpd.read_parquet(
    "../../Data/processed/bwca_waters.parquet"
)
print(lakes["fw_id"].max())
gasket = lakes[lakes["fw_id"]== 99999.0]
print(gasket.info())
water = water.to_crs(lakes.crs)
print(
    water[
        water["fw_id"] == 99999.0
    ][
        [
            "fw_id",
            "unique_guid",
            "wb_class",
            "map_label",
            "acres",
            "geometry"
        ]
    ]
)
# print(water.info())
# print("Gasket CRS:", gasket.crs)
# print("Water CRS:", water.crs)
# water.merge(gasket, on="")
# water = pd.concat(
#     [water, gasket],
#     ignore_index=True
# )
water = gpd.GeoDataFrame(
    pd.concat(
        [water, gasket],
        ignore_index=True
    ),
    geometry="geometry",
    crs=lakes.crs
)
# print(water.head())
# print(water.info())
# print(water[water["fw_id"]==99999.0].info())
water.to_parquet("../../Data/processed/bwca_waters.parquet")
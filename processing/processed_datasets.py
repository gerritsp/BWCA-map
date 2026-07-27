import geopandas as gpd
import matplotlib.pyplot as plt
import folium



lakes = gpd.read_parquet("../Data/processed/bwca_lakes.parquet")
lakes["acres"] = lakes["acres"].round(2)
lakes = lakes.to_crs(epsg=4326)


campsites = gpd.read_parquet("../Data/processed/bwca_campsites.parquet")
campsites = campsites.to_crs(epsg=4326)
# print(campsites.crs)
print(campsites.columns)

# print(lakes.head())
# print()
# print(lakes.columns)
# print()
# print(lakes.geometry.iloc[0])
# print()
# print(lakes.crs)


# stationary plot
# lakes.plot(figsize=(10,10))
#
# plt.show()
# print(lakes.crs)
#
# print(lakes.crs)
# print(lakes.total_bounds)


#

#
print(campsites["LAKE_NAME"].head(20))
camp_counts = campsites.groupby("LAKE_NAME").size()
print(camp_counts["Knife Lake"])
lakes = lakes.merge(
    camp_counts.rename("num_campsites"),
    left_on="map_label",
    right_index=True,
    how="left"
)
lakes["num_campsites"] = lakes["num_campsites"].fillna(0).astype(int)
tooltip = folium.GeoJsonTooltip(
    fields=[
        "map_label",
        "acres",
        "num_campsites"
    ],
    aliases=[
        "Lake",
        "Acres",
        "Campsites"
    ]
)

print(campsites.iloc[0])

fw = campsites.iloc[0]["fw_id"]

print(lakes[lakes["fw_id"] == fw][["map_label", "fw_id"]])
print(campsites["fw_id"].isna().sum())
print(lakes["fw_id"].isna().sum())
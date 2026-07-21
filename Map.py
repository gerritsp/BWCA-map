import geopandas as gpd
import matplotlib.pyplot as plt
import folium
from folium.plugins import MarkerCluster





lakes = gpd.read_parquet("Data/processed/bwca_lakes.parquet")
lakes["acres"] = lakes["acres"].round(2)
lakes = lakes.to_crs(epsg=4326)


campsites = gpd.read_parquet("Data/processed/bwca_campsites.parquet")
campsites = campsites.to_crs(epsg=4326)


print(len(campsites))
# minx, miny, maxx, maxy = lakes.total_bounds
# center = [(miny + maxy) / 2, (minx + maxx) / 2]
# print(center)
#
lakes = lakes[[
    "map_label",
    "acres",
    "geometry"
]]
#
m = folium.Map(
    location=[48.0, -91.5],
    zoom_start=8
)
#
folium.GeoJson(lakes).add_to(m)
# # #
# # # m.save("../maps/bwca_map.html")
# #
# #
folium.GeoJson(
    lakes,
    tooltip=folium.GeoJsonTooltip(
        fields=["map_label", "acres"],
        aliases=["Lake", "Acres"]
    )
).add_to(m)
# # m.save("../maps/bwca_map_labels.html")

# print(lakes["map_label"].head(20))
#
# print(campsites["LAKE_NAME"].head(20))

# camp_counts = campsites.groupby("LAKE_NAME").size()
# lakes = lakes.merge(
#     camp_counts.rename("num_campsites"),
#     left_on="map_label",
#     right_index=True,
#     how="left"
# )
# lakes["num_campsites"] = lakes["num_campsites"].fillna(0).astype(int)
# tooltip = folium.GeoJsonTooltip(
#     fields=[
#         "map_label",
#         "acres",
#         "num_campsites"
#     ],
#     aliases=[
#         "Lake",
#         "Acres",
#         "Campsites"
#     ]
# )
# geojson = folium.GeoJson(
#     lakes,
#     tooltip=tooltip
# )geojson.add_to(m)

cluster = MarkerCluster().add_to(m)
for _, row in campsites.iterrows():

    lat = row.geometry.y
    lon = row.geometry.x

    popup = folium.Popup(
        f"""
        <h4>Campsite {row['CSITENO']}</h4>
        <b>Lake:</b> {row['LAKE_NAME']}<br>
        <b>Status:</b> {row['STATUS']}<br>
        <b>District:</b> {row['District']}<br>
        <b>Distance to matched lake:</b> {row['distance_to_lake']:.1f} m
        """,
        max_width=250
    )

    folium.CircleMarker(
        location=[lat, lon],
        radius=3,
        color="red",
        fill=True,
        fill_color="red",
        fill_opacity=1,
        popup=popup
    ).add_to(cluster)

m.save("maps/bwca_map_Campesites.html")
# print(campsites.iloc[0])
#
# fw = campsites.iloc[0]["fw_id"]
#
# print(lakes[lakes["fw_id"] == fw][["map_label", "fw_id"]])
# print(campsites["fw_id"].isna().sum())
# print(lakes["fw_id"].isna().sum())
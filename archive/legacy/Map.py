from turtledemo.round_dance import stop

import geopandas as gpd
import matplotlib.pyplot as plt
import folium
from folium.plugins import MarkerCluster



waters = gpd.read_parquet("Data/processed/bwca_waters.parquet")
waters = waters.to_crs(epsg=4326)
for col in waters.select_dtypes(include=["datetime", "datetimetz"]).columns:
    waters[col] = waters[col].astype(str)

waters = waters.to_crs(epsg=4326)

lakes = gpd.read_parquet("Data/processed/bwca_lakes.parquet")
for col in lakes.select_dtypes(include=["datetime", "datetimetz"]).columns:
    lakes[col] = lakes[col].astype(str)

lakes["acres"] = lakes["acres"].round(2)
lakes = lakes.to_crs(epsg=4326)


campsites = gpd.read_parquet("Data/processed/bwca_campsites_river.parquet")
campsites = campsites.to_crs(epsg=4326)

portages = gpd.read_parquet("Data/portages_raw/processed_portages_interim.parquet")
portages = portages.to_crs(epsg=4326)
print(portages.info())

entry_points = gpd.read_parquet("Data/entry_raw/entry_points.parquet")
entry_points = entry_points.to_crs(epsg=4326)
new_portages = gpd.read_parquet("Data/portages_raw/portages.parquet")
new_portages = new_portages.to_crs(epsg=4326)
final_portage = gpd.read_parquet("Data/processed/portages_final.parquet")
final_portage = final_portage.to_crs(epsg=4326)
fires = gpd.read_parquet("Data/processed/fires2026.parquet")
fires = fires.to_crs(epsg=4326)

print("\n========== WATER DATA ==========")
print("Total water features:", len(waters))

print("\nWater classes:")
print(waters["wb_class"].value_counts(dropna=False))

print("\nGeometry types:")
print(waters.geometry.geom_type.value_counts())

print("\nCRS:")
print(waters.crs)

print("\nBounds:")
print(waters.total_bounds)

print("================================")
m = folium.Map(
    location=[48.0, -91.5],
    zoom_start=8
)

lake_layer = folium.FeatureGroup(
    name="Lakes",
    show=True
).add_to(m)
camp_counts = campsites.groupby("LAKE_NAME").size()

lakes = lakes.merge(
    camp_counts.rename("num_campsites"),
    left_on="map_label",
    right_index=True,
    how="left"
)
folium.GeoJson(
    lakes,
    tooltip=folium.GeoJsonTooltip(
        fields=["map_label", "acres", "num_campsites"],
        aliases=["Lake", "Acres", "Campsites"]
    ),
    style_function=lambda feature: {
        "color": "blue",
        "weight": 1,
        "fillColor": "blue",
        "fillOpacity": 0.25
    }
).add_to(lake_layer)



water_layer = folium.FeatureGroup(
    name="Rivers / Intermittent Water",
    show=True
).add_to(m)





folium.GeoJson(
    waters,
    style_function=lambda feature: {
        "color": "cyan",
        "weight": 2,
        "fillColor": "cyan",
        "fillOpacity": 0.35
    },
    tooltip=folium.GeoJsonTooltip(
        fields=[
            "map_label",
            "wb_class",
            "unique_guid"
        ],
        aliases=[
            "Water",
            "Type",
            "Water ID"
        ]
    )
).add_to(water_layer)



lakes["num_campsites"] = (
    lakes["num_campsites"]
    .fillna(0)
    .astype(int)
)



cluster = MarkerCluster().add_to(m)
for _, row in campsites.iterrows():

    lat = row.geometry.y
    lon = row.geometry.x

    popup = folium.Popup(
        f"""
        <h4>Campsite: {row['camp_id']}</h4>
        <b>Lake:</b> {row['LAKE_NAME']}<br>
        <b>Status:</b> {row['STATUS']}<br>
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

# m.save("maps/bwca_map_Campsites.html")
# portages["miles"]  = (portages["rods"]/320).round(3)
# new_portages["miles"] = (new_portages["rods"]/320).round(3)



folium.GeoJson(
    final_portage,
    name="Portages",
    style_function=lambda feature: {
        "color": "purple",
        "weight": 3,
        "opacity": 0.8
    },
    tooltip=folium.GeoJsonTooltip(
        fields=[
            "name",
            "rods",
            "lake1",
            "lake2",
            "meters"
        ],
        aliases=[
            "Portage",
            "Rods",
            "Lake A",
            "Lake B",
            "Meters"
        ]
    )
).add_to(m)

entry_cluster = MarkerCluster(name="Entry Points").add_to(m)

for _, row in entry_points.iterrows():

    folium.CircleMarker(
        location=[row.geometry.y, row.geometry.x],
        radius=6,
        color="green",
        fill=True,
        fill_color="green",
        fill_opacity=1,
        popup=f"""
        <b>Entry Point {row['code']}</b><br>
        {row['name']}
        """
    ).add_to(entry_cluster)

folium.GeoJson(
    fires,
    name="2026 Fires",
    style_function=lambda feature: {
        "fillColor": "#6e2c00",
        "color": "#ff6600",
        "weight": 2,
        "fillOpacity": 0.8,
    },
    highlight_function=lambda feature: {
        "weight": 4,
        "color": "yellow",
        "fillOpacity": 0.45,
    },
    tooltip=folium.GeoJsonTooltip(
        fields=[
            "incident_name",
            "acres",
            "status"
        ],
        aliases=[
            "Fire:",
            "Acres:",
            "Status:"
        ]
    )
).add_to(m)
folium.LayerControl().add_to(m)
m.save("maps/bwca_map_fires.html")


# m.save("../maps/bwca_map_labels.html")
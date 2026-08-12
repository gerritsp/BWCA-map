import geopandas as gpd
import pyogrio
import pandas as pd
from shapely.geometry import LineString
from models.Lake import Lake
from shapely.geometry import Point
import re

layers = gpd.list_layers("../../Data/thegpx_files_raw/Boundary Waters Canoe Area.gpx")
print(layers)
wpts = gpd.read_file(
    "../../Data/thegpx_files_raw/Boundary Waters Canoe Area.gpx",
    layer="waypoints"
)
print(wpts.info())
entry_points = wpts[
    wpts["type"].str.contains("Entry", case=False, na=False)
]
print(entry_points[["name", "type", "cmt"]].head(10))
print(entry_points.info())
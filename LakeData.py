import geopandas as gpd
import pyogrio
import os

print(os.listdir("Data/Lakes/water_dnr_hydrography.gdb")[:10])
layers = pyogrio.list_layers(
    r"Data/Lakes/water_dnr_hydrography.gdb"
)

print(layers)
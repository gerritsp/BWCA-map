import geopandas as gpd
import pyogrio

layers = pyogrio.list_layers(
    "data/lakes/water_dnr_hydrography.gdb"
)

print(layers)
import geopandas as gpd

fires = gpd.read_parquet("../../Data/processed/fires2026.parquet")
lakes = gpd.read_parquet("../../Data/Processed/bwca_lakes.parquet")

lake_fire = gpd.sjoin(
    lakes,
    fires,
    how="left",
    predicate="intersects"
)
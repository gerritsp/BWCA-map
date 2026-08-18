from collections import defaultdict
import geopandas as gpd
import pandas as pd
rivers = gpd.read_parquet("../../Data/processed/bwca_rivers_lines.parquet")

# every node key -> list of river_ids touching it
node_to_segments = defaultdict(list)
for _, row in rivers.iterrows():
    node_to_segments[row["node_a"]].append(row["river_id"])
    node_to_segments[row["node_b"]].append(row["river_id"])

# build one row per adjacency: (segment_a, segment_b, shared_node)
adjacency_records = []
for node, seg_ids in node_to_segments.items():
    unique_segs = list(set(seg_ids))
    if len(unique_segs) < 2:
        continue  # dead end, not a junction
    for i in range(len(unique_segs)):
        for j in range(i + 1, len(unique_segs)):
            adjacency_records.append({
                "segment_a": unique_segs[i],
                "segment_b": unique_segs[j],
                "shared_node": node,
            })

adjacency = pd.DataFrame(adjacency_records)
print(f"{len(adjacency)} segment-to-segment junctions across {rivers['river_id'].nunique()} segments")
adjacency.to_parquet("../../Data/Processed/bwca_river_adjacency.parquet")
from models.bwca_graph import bwca_graph
# print(bwca_graph)
# print(type(bwca_graph))
graph = bwca_graph()

graph.load_lakes("Data/processed/bwca_lakes.parquet")
graph.load_campsites("Data/processed/bwca_campsites.parquet")

graph.connect_campsites()

knife = graph.find_lake(3731)

print(knife.name)
print(len(knife.campsites))
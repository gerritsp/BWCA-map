"""Join mapped creek approaches to portage landings while retaining the carry."""
from dataclasses import replace

from shapely.geometry import Point
from shapely.ops import substring


# DNR centerlines checked against both mapped landings. Several reaches
# contain two carries. Keep both gaps in the water graph.
CREEK_CARRIES = {
    72: (169,),         # Pine Creek
    1313: (35,),        # Niki–Chippewa, on Papoose Creek
    1441: (221,),       # Hog Creek
    1659: (531,),       # Anit–Kivaniva
    1674: (524, 527),   # Kivaniva outlet
    2595: (77, 79),     # Tucker River carries
    4154: (215,),       # Kawishiwi River near Square Lake
    5176: (350,),       # Bingshick–Flying
}


def add_creek_approaches(graph):
    for river_id, numbers in CREEK_CARRIES.items():
        river = graph.rivers.get(river_id)
        if river is None or any(n not in graph.portages for n in numbers):
            continue
        line = river.geometry
        gaps = []
        for number in numbers:
            trail = graph.portages[number].geometry
            ends = [Point(trail.coords[i]) for i in (0, -1)]
            if max(line.distance(pt) for pt in ends) > 25:
                break
            gaps.append(sorted(line.project(pt) for pt in ends))
        if len(gaps) != len(numbers):
            continue
        gaps.sort()
        if any(b - a < 1 for a, b in gaps) or any(
                first[1] >= second[0] for first, second in zip(gaps, gaps[1:])):
            continue
        river.routable = False
        starts = [0.0] + [end for _, end in gaps]
        stops = [start for start, _ in gaps] + [line.length]
        for i, (start, stop) in enumerate(zip(starts, stops)):
            if stop - start < 0.5:
                continue
            geom = substring(line, start, stop)
            # Negative IDs distinguish derived pieces from source feature IDs.
            piece_id = -(river_id * 100 + i + 1)
            piece = replace(
                river, river_id=piece_id, routable=True, geometry=geom,
                length_m=geom.length,
                node_a=river.node_a if start == 0 else f"creek:{river_id}:{i}:a",
                node_b=river.node_b if stop == line.length else f"creek:{river_id}:{i}:b",
                unid_a=river.unid_a if start == 0 else None,
                unid_b=river.unid_b if stop == line.length else None,
            )
            graph.rivers[piece_id] = piece

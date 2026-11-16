import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path
import shutil
import tempfile
import unittest

from pyproj import Transformer
import shapely
from shapely.geometry import Point, shape

from Scripts.repair_routing_graph import repair_routing_graph


ROOT = Path(__file__).resolve().parents[1]
MAPS = ROOT / "maps"
TO_UTM = Transformer.from_crs(4326, 26915, always_xy=True).transform


def load(suffix):
    data = json.loads((MAPS / f"bwca_graph_map_{suffix}.json").read_text(
        encoding="utf-8"))
    if suffix == "lakes" and data.get("shards"):
        features = []
        for shard in data["shards"]:
            features.extend(json.loads((MAPS / shard).read_text(
                encoding="utf-8"))["features"])
        if len(features) != data["feature_count"]:
            raise AssertionError("lake layer shard count does not match its manifest")
        data = {"type": data["type"], "features": features}
    return data


class Components:
    def __init__(self, nodes, edges):
        adjacency = defaultdict(list)
        for edge in edges:
            adjacency[edge[0]].append(edge[1])
            adjacency[edge[1]].append(edge[0])
        self.component = {}
        self.sizes = {}
        for node in nodes:
            if node in self.component:
                continue
            self.component[node] = node
            queue = [node]
            for current in queue:
                for neighbor in adjacency[current]:
                    if neighbor not in self.component:
                        self.component[neighbor] = node
                        queue.append(neighbor)
            self.sizes[node] = len(queue)
        self.largest = max(self.sizes, key=self.sizes.get) if self.sizes else None


class RoutingConnectivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lakes = load("lakes")
        cls.portages = load("portages")
        cls.rivers = load("rivers")
        cls.entries = load("entry_points")
        cls.graph = load("paddle_edges")
        cls.nodes = {node[0]: node for node in cls.graph["nodes"]}
        cls.components = Components(cls.nodes, cls.graph["edges"])
        cls.lake_geometry = {
            feature["properties"]["unique_guid"]: shapely.transform(
                shape(feature["geometry"]), TO_UTM, interleaved=False
            )
            for feature in cls.lakes["features"]
        }
        cls.river_features = {
            str(int(feature["properties"]["river_id"])): feature
            for feature in cls.rivers["features"]
        }

    def test_review_portage_lengths_use_conservative_routing_distance(self):
        mismatches = []
        for feature in self.portages["features"]:
            properties = feature["properties"]
            recorded = float(properties["length_rods"]) * 5.0292
            drawn = float(properties["drawn_length_m"])
            routing = float(properties["routing_length_m"])
            if properties["routing_length_ok"]:
                self.assertAlmostEqual(routing, recorded, delta=0.11)
            else:
                mismatches.append(properties["portage_number"])
                self.assertEqual(properties["routing_status"], "review")
                self.assertAlmostEqual(routing, max(recorded, drawn), delta=0.11)
        self.assertEqual(len(mismatches), 24)

    def test_every_same_lake_portage_pair_has_direct_water_route(self):
        groups = defaultdict(list)
        for node_id, lake_id, coordinates in self.graph["nodes"]:
            if not node_id.startswith("portage:") or not lake_id:
                continue
            geometry = self.lake_geometry.get(lake_id)
            if geometry is None:
                continue
            point = shapely.transform(Point(coordinates), TO_UTM, interleaved=False)
            parts = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
            distances = [point.distance(part) for part in parts]
            part_index = min(range(len(parts)), key=distances.__getitem__)
            if distances[part_index] <= 25.01:
                groups[(lake_id, part_index)].append((node_id, point))

        paddle = {}
        for edge in self.graph["edges"]:
            if edge[3] != "paddle":
                continue
            key = tuple(sorted((edge[0], edge[1])))
            paddle[key] = min(float(edge[2]), paddle.get(key, float("inf")))

        checked = 0
        for key, landings in groups.items():
            for left, right in combinations(landings, 2):
                pair = tuple(sorted((left[0], right[0])))
                with self.subTest(lake_part=key, pair=pair):
                    self.assertIn(pair, paddle)
                checked += 1
        self.assertEqual(checked, 1403)

        # The audited Insula pair used to detour 74.5 km through 39 lakes.
        # Its direct, water-contained edge is now about 3.1 km for a 2.1 km
        # chord, so the route cannot leave the lake to reach the other landing.
        insula_pair = tuple(sorted(("portage:570:b", "portage:757:b")))
        insula_direct = self.nodes[insula_pair[0]][2], self.nodes[insula_pair[1]][2]
        left = shapely.transform(Point(insula_direct[0]), TO_UTM, interleaved=False)
        right = shapely.transform(Point(insula_direct[1]), TO_UTM, interleaved=False)
        self.assertLessEqual(paddle[insula_pair] / left.distance(right), 3.0)

    def test_connected_entries_reach_the_main_component(self):
        lake_components = defaultdict(set)
        for node_id, lake_id, _ in self.graph["nodes"]:
            if lake_id:
                lake_components[lake_id].add(self.components.component[node_id])

        connected = 0
        for feature in self.entries["features"]:
            properties = feature["properties"]
            if properties["routing_status"] != "connected":
                continue
            connected += 1
            reachable = False
            for attachment in properties.get("attachments", []):
                if attachment.get("confidence") == "review":
                    continue
                node_id = attachment.get("node_id")
                if (node_id in self.components.component and
                        self.components.component[node_id] == self.components.largest):
                    reachable = True
                if self.components.largest in lake_components.get(
                        attachment.get("lake_guid"), set()):
                    reachable = True
            self.assertTrue(reachable, properties.get("code"))
        self.assertGreater(connected, 0)

    def test_portage_endpoints_use_only_geometry_supported_anchors(self):
        self.assertEqual(len(self.portages["features"]), 905)
        invalid = []
        for feature in self.portages["features"]:
            properties = feature["properties"]
            line = shapely.transform(
                shape(feature["geometry"]), TO_UTM, interleaved=False
            )
            if not properties["routing_geometry_valid"]:
                invalid.append(properties["portage_number"])
            for side, point in (
                ("a", Point(line.coords[0])),
                ("b", Point(line.coords[-1])),
            ):
                routing_type = properties[f"routing_type_{side}"]
                self.assertIn(routing_type, {"lake", "river", "unresolved"})
                if routing_type == "lake":
                    guid = properties[f"routing_lake_guid_{side}"]
                    self.assertLessEqual(
                        point.distance(self.lake_geometry[guid]), 25.01
                    )
                elif routing_type == "river":
                    river_id = str(int(properties[f"routing_river_id_{side}"]))
                    river = self.river_features[river_id]
                    river_line = shapely.transform(
                        shape(river["geometry"]), TO_UTM, interleaved=False
                    )
                    self.assertLessEqual(point.distance(river_line), 25.01)
                    portage_node = f"portage:{properties['portage_number']}:{side}"
                    river_properties = river["properties"]
                    component = self.components.component
                    self.assertEqual(component[portage_node], component[river_properties["node_a"]])
                    self.assertEqual(component[portage_node], component[river_properties["node_b"]])
                else:
                    self.assertIsNone(properties[f"routing_lake_guid_{side}"])
                    self.assertIsNone(properties[f"routing_river_id_{side}"])
        self.assertEqual(invalid, [])
        corrected = next(
            feature for feature in self.portages["features"]
            if feature["properties"]["portage_number"] == 126
        )
        corrected_line = shapely.transform(
            shape(corrected["geometry"]), TO_UTM, interleaved=False
        )
        self.assertEqual(corrected["properties"]["geometry_source"], "usfs_trail_correction")
        self.assertEqual(corrected["properties"]["lake_a"], "Big Rice")
        self.assertEqual(corrected["properties"]["lake_b"], "Hook")
        self.assertAlmostEqual(corrected_line.length, 2671.9, delta=1.0)
        snake_entry = next(
            feature for feature in self.portages["features"]
            if feature["properties"]["portage_number"] == 679
        )
        snake_line = shapely.transform(
            shape(snake_entry["geometry"]), TO_UTM, interleaved=False
        )
        self.assertEqual(
            snake_entry["properties"]["geometry_source"],
            "usfs_trail_correction",
        )
        self.assertEqual(snake_entry["properties"]["routing_type_b"], "river")
        self.assertAlmostEqual(snake_line.length, 1132.9, delta=1.0)

    def test_graph_references_exist_and_each_lake_part_is_connected(self):
        for edge in self.graph["edges"]:
            self.assertIn(edge[0], self.nodes)
            self.assertIn(edge[1], self.nodes)

        groups = defaultdict(list)
        for node_id, lake_id, coordinates in self.graph["nodes"]:
            if not lake_id or node_id.startswith("vertex:"):
                continue
            geometry = self.lake_geometry.get(lake_id)
            if geometry is None:
                continue
            point = shapely.transform(Point(coordinates), TO_UTM, interleaved=False)
            parts = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
            distances = [point.distance(part) for part in parts]
            part_index = min(range(len(parts)), key=distances.__getitem__)
            if distances[part_index] <= 25.01:
                groups[(lake_id, part_index)].append(node_id)

        for key, nodes in groups.items():
            with self.subTest(lake_part=key):
                self.assertEqual(
                    len({self.components.component[node] for node in nodes}), 1
                )

    def test_exact_river_junction_components_are_connected(self):
        groups = defaultdict(list)
        for feature in self.rivers["features"]:
            properties = feature["properties"]
            component = properties.get("routing_component")
            if properties.get("routable") and component:
                groups[component].extend(
                    [properties["node_a"], properties["node_b"]]
                )
        for component, nodes in groups.items():
            with self.subTest(river_component=component):
                self.assertEqual(
                    len({self.components.component[node] for node in nodes}), 1
                )
        self.assertGreater(
            self.graph["topology_repair"]["river_junction_attachments"], 0
        )

    def test_topology_repair_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            stem = directory / "bwca_graph_map"
            for suffix in ("lakes", "portages", "rivers", "fires", "paddle_edges"):
                shutil.copyfile(
                    MAPS / f"bwca_graph_map_{suffix}.json",
                    directory / f"bwca_graph_map_{suffix}.json",
                )
            before = json.loads(stem.with_name(stem.name + "_paddle_edges.json").read_text(
                encoding="utf-8"))
            repair_routing_graph(stem)
            after = json.loads(stem.with_name(stem.name + "_paddle_edges.json").read_text(
                encoding="utf-8"))
            self.assertEqual(len(after["nodes"]), len(before["nodes"]))
            self.assertEqual(len(after["edges"]), len(before["edges"]))
            self.assertEqual(after["topology_repair"], before["topology_repair"])


if __name__ == "__main__":
    unittest.main()

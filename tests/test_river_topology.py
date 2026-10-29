import unittest

from shapely.geometry import LineString

from Scripts.river_topology import river_component_labels


class RiverTopologyTests(unittest.TestCase):
    def test_endpoint_on_line_interior_joins_components(self):
        rows = [
            {
                "river_id": 1,
                "node_a": "west",
                "node_b": "east",
                "geometry": LineString([(0, 0), (10, 0)]),
            },
            {
                "river_id": 2,
                "node_a": "south",
                "node_b": "confluence",
                "geometry": LineString([(5, -5), (5, 0)]),
            },
            {
                "river_id": 3,
                "node_a": "near-south",
                "node_b": "near-confluence",
                "geometry": LineString([(7, -5), (7, 0.2)]),
            },
        ]

        labels = river_component_labels(rows)

        self.assertEqual(labels[1], labels[2])
        self.assertNotEqual(labels[1], labels[3])


if __name__ == "__main__":
    unittest.main()

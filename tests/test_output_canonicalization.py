import unittest

from Scripts.canonicalize_output import (
    canonicalize_route_graph,
    round_floats,
)


class OutputCanonicalizationTests(unittest.TestCase):
    def test_coordinate_rounding_removes_platform_noise(self):
        # Shapely mappings contain coordinate tuples before JSON encoding.
        linux = {"coordinates": [(-92.0, 47.93229699999999)]}
        runner = {"coordinates": [(-92.0, 47.932297000000004)]}
        self.assertEqual(round_floats(linux), round_floats(runner))

    def test_graph_weights_and_geometry_are_canonical(self):
        left = {
            "nodes": [["a", "lake", [-92.0, 48.00000000000001]]],
            "edges": [[
                "a", "b", 1227.0589725008354, "paddle",
                {"type": "LineString", "coordinates": [[-92.0, 48.00000000000001]]},
                False,
            ]],
        }
        right = {
            "nodes": [["a", "lake", [-92.0, 48.0]]],
            "edges": [[
                "a", "b", 1227.058972499723, "paddle",
                {"type": "LineString", "coordinates": [[-92.0, 48.0]]},
                False,
            ]],
        }
        self.assertEqual(
            canonicalize_route_graph(left),
            canonicalize_route_graph(right),
        )


if __name__ == "__main__":
    unittest.main()

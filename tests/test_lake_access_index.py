import unittest

from Scripts.build_lake_access_index import build_access_index


def collection(*properties):
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": row, "geometry": None}
            for row in properties
        ],
    }


class LakeAccessIndexTests(unittest.TestCase):
    def test_retains_real_pareto_routes_for_combined_filters(self):
        portages = collection(
            {"unique_guid_a": "A", "unique_guid_b": "B", "length_rods": 10},
            {"unique_guid_a": "A", "unique_guid_b": "C", "length_rods": 20},
            {"unique_guid_a": "A", "unique_guid_b": "X", "length_rods": -1},
            {"unique_guid_a": "A", "unique_guid_b": "Y", "length_rods": float("nan")},
        )
        rivers = collection(
            {"unique_guid_a": "B", "unique_guid_b": "C", "routable": True},
            {"unique_guid_a": "C", "unique_guid_b": "D", "routable": False},
        )
        entries = collection(
            {"code": "10", "name": "Ten", "unique_guid": "C"},
            {"code": "2", "name": "Two", "unique_guid": "A"},
            {"code": None, "name": "Unmatched", "unique_guid": None},
        )

        result = build_access_index(portages, rivers, entries)

        self.assertEqual([entry["code"] for entry in result["entries"]], ["2", "10"])
        self.assertEqual(result["starts"]["A"]["A"], [[0.0, 0, 0]])
        self.assertEqual(result["starts"]["A"]["C"],
                         [[10.0, 1, 2], [20.0, 1, 1]])
        self.assertNotIn("D", result["starts"]["A"])
        self.assertNotIn("X", result["starts"]["A"])
        self.assertNotIn("Y", result["starts"]["A"])


if __name__ == "__main__":
    unittest.main()

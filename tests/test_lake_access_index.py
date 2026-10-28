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
            {"code": "10", "name": "Ten", "location_count": 1,
             "attachments": [{"lake_guid": "C", "initial_rods": 0, "initial_portages": 0}]},
            {"code": "2", "name": "Two", "location_count": 1,
             "attachments": [{"lake_guid": "A", "initial_rods": 5, "initial_portages": 1}]},
            {"code": None, "name": "Unmatched", "attachments": []},
        )

        result = build_access_index(portages, rivers, entries)

        self.assertEqual(result["schema_version"], 3)
        self.assertEqual([entry["code"] for entry in result["entries"]], ["2", "10"])
        self.assertEqual(result["starts"]["2"]["A"], [[5.0, 1, 0]])
        self.assertEqual(result["starts"]["2"]["C"],
                         [[15.0, 2, 2], [25.0, 2, 1]])
        self.assertNotIn("D", result["starts"]["2"])
        self.assertNotIn("X", result["starts"]["2"])
        self.assertNotIn("Y", result["starts"]["2"])

    def test_river_entry_and_portage_use_verified_water_component(self):
        portages = collection({
            "routing_type_a": "river",
            "routing_river_id_a": 7,
            "routing_type_b": "lake",
            "routing_lake_guid_b": "B",
            "length_rods": 10,
        })
        rivers = collection({
            "river_id": 7,
            "node_a": "n1",
            "node_b": "n2",
            "unique_guid_a": None,
            "unique_guid_b": None,
            "routable": True,
        })
        entries = collection({
            "code": "1",
            "name": "River entry",
            "location_count": 1,
            "attachments": [{
                "routing_type": "river",
                "routing_river_id": 7,
                "node_id": "n1",
                "initial_rods": 0,
                "initial_portages": 0,
            }],
        })

        result = build_access_index(portages, rivers, entries)

        self.assertEqual(result["starts"]["1"]["B"], [[10.0, 1, 0]])


if __name__ == "__main__":
    unittest.main()

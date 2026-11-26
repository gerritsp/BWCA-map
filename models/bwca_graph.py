# models/graph.py
from models.lake_ids import normalize_dow
import geopandas as gpd
from models.Campsite import Campsite
from models.Lake import Lake
import pandas as pd
from models.Portage import Portage
from models.RiverSegment import RiverSegment


ROUTABLE_RIVER_TYPES = {"Centerline (River)", "Connector (River)"}


# Forest Service paddle entries 36 and 80 follow these DNR reaches.
# Use endpoint keys to avoid enabling unrelated same-name streams.
ENTRY_CREEKS = {
    # Kawishiwi Lake outlet to Square Lake (DNR unnamed perennial reach).
    (None, "641163.1_5302818.3"): "{285DAAF8-AFAD-43F8-8A5D-BFCC4A2B5D3B}",
    ("Hog Creek", "641333.3_5295096.8"): "{DF2E17D7-5A32-49BD-AB00-B3292C589460}",
    ("Larch Creek", "662065.5_5333128.9"): "{4A703264-A2CD-4879-A57A-40C63F25F745}",
}


class bwca_graph:

    def __init__(self):

        self.lakes = {}
        self.campsites = {}
        self.portages = {}
        self.rivers = {}

    @staticmethod
    def normalize_name(name):
        if pd.isna(name):
            return None

        return str(name).strip().lower()

    def load_lakes(self,filename):
        lake_df = gpd.read_parquet(filename)

        for _, row in lake_df.iterrows():
            lake = Lake(
                fw_id=row["fw_id"],
                name=row["map_label"],
                geometry=row.geometry,
                acres=row["acres"],
                shoreline_miles=row["shore_mi"],
                unique_guid=str(row["unique_guid"])
            )

            lake.dowlknum = normalize_dow(row.get("dowlknum"))
            self.lakes[lake.unique_guid] = lake

    def load_campsites(self, filename):
        camp_df = gpd.read_parquet(filename)
        for _, row in camp_df.iterrows():
            campsite = Campsite(
                camp_id=row["camp_id"],
                site_number=row["CSITENO"],
                lake_name=row["LAKE_NAME"],
                fw_id=row["lake_fw_id"],
                status=row["STATUS"],
                district=row["District"],  # not in this dataset yet - see note below
                distance_to_lake=row["distance_to_lake"],
                lake_unid=row["lake_unique_guid"],
                geometry=row.geometry
            )
            self.campsites[campsite.camp_id] = campsite

    def load_portages(self, filename):

        portage_df = gpd.read_parquet(filename)

        for _, row in portage_df.iterrows():
            portage = Portage(
                usfs_id=row["usfsid"],
                portage_num=row["portage_num"],
                name=row["name"],
                rods=row["rods"],
                meters=row["meters"],
                miles=row["miles"],
                start_lat=row["startlat"],
                start_lon=row["startlon"],
                end_lat=row["endlat"],
                end_lon=row["endlon"],
                lake1_name=row["lake1"],
                lake2_name=row["lake2"],
                start_fw_id=row["start_fw_id"],
                end_fw_id=row["end_fw_id"],
                start_unid=row["start_unid"],
                end_unid=row["end_unid"],
                start_snapped=row.get("start_snapped", False),
                end_snapped=row.get("end_snapped", False),
                geometry=row.geometry
            )
            # A USFS ID may describe more than one mapped segment (37 records
            # in the current snapshot would otherwise overwrite a sibling).
            # portage_num is the processed layer's unique per-feature key.
            self.portages[portage.portage_num] = portage

    def load_rivers(self, filename):
        river_df = gpd.read_parquet(filename)

        for _, row in river_df.iterrows():
            name = row["name"] if isinstance(row["name"], str) else None
            landing = ENTRY_CREEKS.get((name, row["node_a"]))
            # Documented paddle passage between Thomas and Fraser (Data/SOURCES.md).
            thomas_fraser = (row["node_a"], row["node_b"]) == (
                "633285.6_5317345.3", "633333.6_5317442.0")
            routable = row["strm_type"] in ROUTABLE_RIVER_TYPES or landing is not None or thomas_fraser
            segment = RiverSegment(
                river_id=row["river_id"],
                name=name,
                strm_type=row["strm_type"],
                routable=routable,
                node_a=row["node_a"],
                node_b=row["node_b"],
                length_m=row["length_m"],
                unid_a=landing or row["unid_a"],
                unid_b=row["unid_b"],
                geometry=row.geometry
            )
            self.rivers[segment.river_id] = segment

    def load_river_adjacency(self, filename):
        self._river_adjacency_df = pd.read_parquet(filename)


    def connect_campsites(self):

        for campsite in self.campsites.values():
            lake = self.lakes.get(campsite.lake_unid)

            if lake:
                campsite.lake = lake
                lake.campsites.append(campsite)

    def connect_portages(self):

        for portage in self.portages.values():

            lake_a = self.lakes.get(portage.start_unid)
            lake_b = self.lakes.get(portage.end_unid)

            portage.lake_a = lake_a
            portage.lake_b = lake_b

            if lake_a:
                lake_a.portages.append(portage)
            if lake_b and lake_b is not lake_a:
                lake_b.portages.append(portage)



    def connect_rivers(self):
        for segment in self.rivers.values():
            lake_a = self.lakes.get(segment.unid_a)
            lake_b = self.lakes.get(segment.unid_b)

            if lake_a:
                segment.lake_a = lake_a
                lake_a.river_segments.append(segment)
            if lake_b:
                segment.lake_b = lake_b
                lake_b.river_segments.append(segment)

    def connect_river_adjacency(self):
        # wire segment-to-segment neighbors from the junction table
        if not hasattr(self, "_river_adjacency_df"):
            return

        for _, row in self._river_adjacency_df.iterrows():
            seg_a = self.rivers.get(row["segment_a"])
            seg_b = self.rivers.get(row["segment_b"])

            if seg_a is None or seg_b is None:
                continue

            seg_a.neighbors.append(seg_b)
            seg_b.neighbors.append(seg_a)




    def connect(self):

        self.connect_campsites()
        self.connect_portages()
        self.connect_rivers()  # new
        self.connect_river_adjacency()  # new
    def find_campsite(self, campsite_id):
        return self.campsites.get(campsite_id)
    def get_num_campsites(self, lake):
        return len(lake.campsites)

    def find_entry_point(self, code):

        return self.entry_points.get(str(code))

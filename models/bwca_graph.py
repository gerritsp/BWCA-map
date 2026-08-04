# models/graph.py
import geopandas as gpd
from models.Campsite import Campsite
from models.Lake import Lake
import pandas as pd
from models.Portage import Portage


class bwca_graph:

    def __init__(self):

        self.lakes = {}
        self.lakes_by_name = {}  # name -> Lake
        self.campsites = {}
        self.portages = []

    @staticmethod
    def normalize_name(name):
        if pd.isna(name):
            return None

        return str(name).strip().lower()

    lakes = {}
    def load_lakes(self,filename):
        lake_df = gpd.read_parquet(filename)

        for _, row in lake_df.iterrows():
            lake = Lake(
                fw_id=row["fw_id"],
                name=row["map_label"],
                geometry=row.geometry,
                acres=row["acres"],
                shoreline_miles=row["shore_mi"]
            )

            self.lakes[lake.fw_id] = lake
            normalized = self.normalize_name(lake.name)

            if normalized is not None:
                self.lakes_by_name[normalized] = lake
                self.lakes_by_name[normalized + " lake"] = lake


    def load_campsites(self,filename):
        camp_df = gpd.read_parquet(filename)
        unmatched = []
        for _, row in camp_df.iterrows():

            campsite = Campsite(

                camp_id=row["camp_id"],

                site_number=row["CSITENO"],

                lake_name=row["LAKE_NAME"],

                fw_id=row["fw_id"],

                status=row["STATUS"],

                district=row["District"],

                distance_to_lake=row["distance_to_lake"],

                geometry=row.geometry

            )

            self.campsites[campsite.camp_id] = campsite

    def load_portages(self, filename):

        portage_df = gpd.read_parquet(filename)

        for _, row in portage_df.iterrows():
            portage = Portage(

                portage_number=row["portage_num"],

                usfs_id=row["usfs_id"],

                fw_id_a=row["start_fw_id"],

                fw_id_b=row["end_fw_id"],

                length_rods=row["rods"],

                geometry=row.geometry,

                waterbody=row["name"],

                dist_lake_a=row["start_distance_m"],

                dist_lake_b=row["end_distance_m"],

                lake_match_uncertain=row["uncertain"]

            )

            self.portages.append(portage)

    def connect_campsites(self):

        for campsite in self.campsites.values():
            lake = self.lakes.get(campsite.fw_id)

            if lake:
                campsite.lake = lake
                lake.campsites.append(campsite)

    def connect_portages(self):

        for portage in self.portages:

            lake_a = self.lakes.get(portage.fw_id_a)
            lake_b = self.lakes.get(portage.fw_id_b)

            if lake_a is None or lake_b is None:
                continue

            portage.Lake_a = lake_a
            portage.Lake_b = lake_b

            lake_a.connections.append(portage)
            lake_b.connections.append(portage)

    def find_lake_by_id(self, fw_id):
        return self.lakes.get(fw_id)

    def find_lake_by_name(self, name):
        return self.lakes_by_name.get(self.normalize_name(name))
    def find_campsite(self, campsite_id):
        return self.campsites.get(campsite_id)
    def get_num_campsites(self, lake):
        return len(lake.campsites)
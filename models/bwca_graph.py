# models/graph.py
import geopandas as gpd
from models.Campsite import Campsite
from models.Lake import Lake
import pandas as pd
from models.Portage import Portage
from models.EntryPoint import EntryPoint

class bwca_graph:

    def __init__(self):

        self.lakes = {}
        self.lakes_by_name = {} # name -> Lake
        self.campsites = {}
        self.portages = {}
        self.entry_points = {}

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
                shoreline_miles=row["shore_mi"],
                unique_guid=row["unique_guid"]
            )

            self.lakes[lake.unique_guid] = lake
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

                lake_unid= row["lake_unid"],

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
                geometry=row.geometry
            )
            self.portages[portage.usfs_id] = portage

    def load_entry_points(self, filename):
        entry_points_df = gpd.read_parquet(filename)
        for _, row in entry_points_df.iterrows():
            entry = EntryPoint(
                id = row["id"],
                code=row["code"],
                name = row["name"],
                fw_id=row["fw_id"],
                lat=row["latitude"],
                lon=row["longitude"],
                lake_unid=row["lake_unid"],
                geometry=row.geometry
            )
            self.entry_points[entry.code] = entry




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

            if lake_a is None or lake_b is None:
                continue

            portage.lake_a = lake_a
            portage.lake_b = lake_b

            lake_a.portages.append(portage)
            lake_b.portages.append(portage)



    def connect_entry_points(self):

        for entry in self.entry_points.values():

            lake = self.lakes.get(entry.lake_unid)

            if lake:
                entry.lake = lake

                lake.entry_points.append(entry)




    def connect(self):

        self.connect_campsites()

        self.connect_portages()

        self.connect_entry_points()




    def find_lake_by_id(self, fw_id):
        return self.lakes.get(fw_id)

    def find_lake_by_name(self, name):
        return self.lakes_by_name.get(self.normalize_name(name))
    def find_campsite(self, campsite_id):
        return self.campsites.get(campsite_id)
    def get_num_campsites(self, lake):
        return len(lake.campsites)

    def find_entry_point(self, code):

        return self.entry_points.get(str(code))
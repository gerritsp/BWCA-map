# models/graph.py
import geopandas as gpd
from models.Campsite import Campsite
from models.Lake import Lake

class bwca_graph:

    def __init__(self):

        self.lakes = {}

        self.campsites = {}




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

                geometry=row.geometry

            )

            self.campsites[campsite.camp_id] = campsite


    def connect_campsites(self):

        for campsite in self.campsites.values():

            if campsite.fw_id in self.lakes:
                lake = self.lakes[campsite.fw_id]

                campsite.lake = lake

                lake.campsites.append(campsite)

    def find_lake(self, fw_id):

        return self.lakes.get(fw_id)

    def find_lake_by_name(self, name):

        for lake in self.lakes.values():

            if lake.name.lower() == name.lower():
                return lake

        return None
class Portage:
    def __init__(
        self,
        usfs_id: int,
        portage_num: int,
        name: str,
        rods: float,
        meters: float,
        miles: float,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        lake1_name: str,
        lake2_name: str,
        start_fw_id: int | None,
        end_fw_id: int | None,
        geometry
    ):

        # IDs
        self.portage_num = portage_num
        self.usfs_id = usfs_id

        # Name
        self.name = name

        # Lengths
        self.length_rods = rods
        self.length_meters = meters
        self.length_miles = miles

        # Coordinates
        self.start_lat = start_lat
        self.start_lon = start_lon
        self.end_lat = end_lat
        self.end_lon = end_lon

        # Names from scraped dataset
        self.lake1_name = lake1_name
        self.lake2_name = lake2_name

        # Graph IDs
        self.fw_id_a = start_fw_id
        self.fw_id_b = end_fw_id

        # Actual Lake objects (filled in later)
        self.lake_a = None
        self.lake_b = None

        self.geometry = geometry

    # Helper methods placed at class level (out of __init__)
    def get_length_miles(self) -> float:
        return self.miles

    def connects_unknown(self) -> bool:
        return self.fw_id_a is None or self.fw_id_b is None

    def connects(self, fw_id):
        return self.fw_id_a == fw_id or self.fw_id_b == fw_id
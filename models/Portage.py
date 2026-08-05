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
        lake1: str,
        lake2: str,
        start_fw_id: int | None,
        end_fw_id: int | None,
        geometry
    ):
        # Identifiers
        self.portage_number = portage_num
        self.usfs_id = usfs_id
        self.waterbody = name

        # Waterbody Feature IDs
        self.fw_id_a = start_fw_id
        self.fw_id_b = end_fw_id

        # Measurements
        self.length_rods = rods
        self.meters = meters
        self.miles = miles

        # Coordinates
        self.start_lat = start_lat
        self.start_lon = start_lon
        self.end_lat = end_lat
        self.end_lon = end_lon

        # Lakes & Spatial Geometry
        self.Lake_a = lake1
        self.Lake_b = lake2
        self.geometry = geometry

    # Helper methods placed at class level (out of __init__)
    def get_length_miles(self) -> float:
        return self.miles

    def connects_unknown(self) -> bool:
        return self.fw_id_a is None or self.fw_id_b is None
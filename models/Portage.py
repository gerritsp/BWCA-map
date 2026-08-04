class Portage:
    def __init__(
        self,
        portage_number,
        usfs_id,
        fw_id_a,
        fw_id_b,
        length_rods,
        geometry,
        dist_lake_a,
        dist_lake_b,
        lake_match_uncertain=False,
        waterbody=None,
        uncertain=False
    ):
        self.portage_number = portage_number
        self.usfs_id = usfs_id

        self.fw_id_a = fw_id_a
        self.fw_id_b = fw_id_b

        self.length_rods = length_rods
        self.geometry = geometry

        self.waterbody = waterbody
        self.uncertain = uncertain

        self.dist_lake_a = dist_lake_a
        self.dist_lake_b = dist_lake_b

        self.lake_match_uncertain = lake_match_uncertain

        # Filled in later
        self.Lake_a = None
        self.Lake_b = None
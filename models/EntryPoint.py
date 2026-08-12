class EntryPoint:

    def __init__(
        self,
        id,
        code,
        name,
        fw_id,
        lat,
        lon,
        lake_unid,
        geometry
    ):
        self.id = id
        self.code = code
        self.name = name
        self.fw_id = fw_id
        self.lat = lat
        self.lon = lon
        self.lake_unid = lake_unid

        self.geometry = geometry

        self.lake = None
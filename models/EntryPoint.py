class EntryPoint:

    def __init__(
        self,
        id,
        code,
        name,
        fw_id,
        lat,
        lon,
        geometry
    ):
        self.id = id
        self.code = code
        self.name = name
        self.fw_id = fw_id
        self.lat = lat
        self.lon = lon

        self.geometry = geometry

        self.lake = None
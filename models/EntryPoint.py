class EntryPoint:

    def __init__(
        self,
        code,
        name,
        lat,
        lon,
        geometry
    ):

        self.code = code
        self.name = name

        self.lat = lat
        self.lon = lon

        self.geometry = geometry

        self.lake = None
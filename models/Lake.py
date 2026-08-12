from dataclasses import dataclass, field

@dataclass
class Lake:
    fw_id: int
    name: str

    geometry: object

    acres: float
    shoreline_miles: float

    unique_guid : str

    campsites: list = field(default_factory=list)

    portages: list = field(default_factory=list)

    entry_points: list = field(default_factory=list)

    connections: list = field(default_factory=list)
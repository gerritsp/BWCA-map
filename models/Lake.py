from dataclasses import dataclass, field

@dataclass
class Lake:
    name: str
    geometry: object  # Full lake polygon
    center_x: float
    center_y: float
    acres: float
    shoreline_miles: float
    campsites: list[Campsite]
    connections: list[Portage]

    campsites: list = field(default_factory=list)
    portages: list = field(default_factory=list)

    # later
    fish_species: list = field(default_factory=list)
    entry_points: list = field(default_factory=list)
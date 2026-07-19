from dataclasses import dataclass, field

@dataclass
class Lake:
    name: str
    x: float
    y: float

    campsites: list = field(default_factory=list)
    portages: list = field(default_factory=list)

    # later
    fish_species: list = field(default_factory=list)
    entry_points: list = field(default_factory=list)
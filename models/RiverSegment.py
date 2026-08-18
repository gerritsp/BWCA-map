from dataclasses import dataclass, field

@dataclass
class RiverSegment:
    river_id: int
    name: str | None
    strm_type: str
    routable: bool
    node_a: str
    node_b: str
    length_m: float
    geometry: object

    unid_a: str | None = None   # lake this segment's start connects to, if any
    unid_b: str | None = None   # lake this segment's end connects to, if any

    lake_a: object = None       # resolved Lake object (filled in later)
    lake_b: object = None

    neighbors: list = field(default_factory=list)  # adjacent RiverSegment objects (via shared node)
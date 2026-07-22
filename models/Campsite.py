from dataclasses import dataclass
from Lake import Lake

@dataclass
class Campsite:
    site_number: int
    camp_id: str
    lake_name: str
    # lake: Lake
    status: str
    district: str
    geometry: object
    # utm_x: float
    # utm_y: float
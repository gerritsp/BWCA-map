from dataclasses import dataclass
from Lake import Lake

@dataclass
class Campsite:
    site_number: int
    camp_id: str
    lake: Lake
    status: str
    district: str
    utm_x: float
    utm_y: float
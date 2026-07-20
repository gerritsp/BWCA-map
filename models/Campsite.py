from dataclasses import dataclass
from Lake import Lake

@dataclass
class Campsite:
    site_number: int
    lake: Lake
    status: str
    district: str
    utm_x: float
    utm_y: float
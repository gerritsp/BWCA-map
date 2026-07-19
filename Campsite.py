from dataclasses import dataclass

@dataclass
class Campsite:
    site_number: int
    lake: str
    status: str
    district: str
    utm_x: float
    utm_y: float
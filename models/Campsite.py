
from dataclasses import dataclass

@dataclass
class Campsite:

    camp_id: str

    site_number: int

    lake_name: str

    fw_id: int

    status: str

    district: str

    geometry: object

    lake = None
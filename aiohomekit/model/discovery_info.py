from __future__ import annotations
from uuid import UUID
from dataclasses import dataclass
from .status_flags import StatusFlags
from .categories import Category


@dataclass
class AbstractDiscoveryInfo:
    id: UUID # uuid5 from original id for convenience
    original_id: str # ”XX:XX:XX:XX:XX:XX”, where ”XX” is a hexadecimal string representing a byte; just in case
    name: str
    status_flags: StatusFlags
    config_num: int
    state_num: int # TODO: state_num vs config_num
    category: Category

from __future__ import annotations
from dataclasses import dataclass
from .status_flags import StatusFlags
from .categories import Categories


@dataclass
class AbstractDiscoveryInfo:
    id: str
    name: str
    status_flags: StatusFlags
    config_num: int
    state_num: int # TODO: state_num vs config_num
    category: Categories

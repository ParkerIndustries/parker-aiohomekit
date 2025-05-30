from __future__ import annotations
from dataclasses import dataclass
from .status_flags import StatusFlags
from .categories import Category
from .typed_dicts import HKDeviceID


@dataclass
class AbstractDiscoveryInfo:
    id: HKDeviceID
    name: str
    status_flags: StatusFlags
    config_num: int
    state_num: int
    category: Category

from __future__ import annotations

from dataclasses import dataclass

from .categories import Category
from .status_flags import StatusFlags
from .typed_dicts import HKDeviceID


@dataclass
class AbstractDiscoveryInfo:
    id: HKDeviceID
    name: str
    category: Category
    status_flags: StatusFlags
    config_num: int
    state_num: int

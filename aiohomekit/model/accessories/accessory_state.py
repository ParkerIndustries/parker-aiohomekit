from typing import Any
from dataclasses import dataclass
from .accessories import Accessories


@dataclass
class AccessoriesState:
    accessories: Accessories
    config_num: int
    broadcast_key: bytes | None = None
    state_num: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "config_num": self.config_num,
            "broadcast_key": self.broadcast_key,
            "state_num": self.state_num,
            "accessories": self.accessories.serialize(),
        }

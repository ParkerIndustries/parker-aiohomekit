from dataclasses import dataclass
from typing import Any

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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccessoriesState":
        return cls(
            accessories=Accessories.from_list(data["accessories"]),
            config_num=data["config_num"],
            broadcast_key=data.get("broadcast_key"),
            state_num=data.get("state_num"),
        )

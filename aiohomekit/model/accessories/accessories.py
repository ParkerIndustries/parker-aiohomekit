from __future__ import annotations

from typing import Iterator, Self

from aiohomekit import hkjson
from aiohomekit.model import typed_dicts
from aiohomekit.model.characteristics import EVENT_CHARACTERISTICS, CharacteristicKey
from aiohomekit.protocol.statuscodes import to_status_code

from .accessory import Accessory


class Accessories:
    """Represents a list of HomeKit accessories."""

    accessories: list[Accessory]

    def __init__(self):
        """Initialize a new list of accessories."""
        self.accessories = []
        self._aid_to_accessory: dict[int, Accessory] = {}

    def __iter__(self) -> Iterator[Accessory]:
        return iter(self.accessories)

    def __getitem__(self, idx: int) -> Accessory:
        return self.accessories[idx]

    @classmethod
    def from_file(cls, path) -> Accessories:
        with open(path, encoding="utf-8") as fp:
            return cls.from_list(hkjson.loads(fp.read()))

    @classmethod
    def from_list(cls, accessories: typed_dicts.Accessories) -> Self:
        self = cls()
        for accessory in accessories:
            self.add_accessory(Accessory.create_from_dict(accessory))
        return self

    def add_accessory(self, accessory: Accessory):
        """Add an accessory to the list of accessories."""
        self.accessories.append(accessory)
        self._aid_to_accessory[accessory.aid] = accessory

    def serialize(self) -> typed_dicts.Accessories:
        """Serialize the accessories to a list of dicts."""
        return [a.as_dict() for a in self.accessories]

    def as_dict(self) -> dict[str, typed_dicts.Accessories]:
        return {"accessories": self.serialize()}

    def aid(self, aid: int) -> Accessory:
        """Return the accessory with the given aid, raising KeyError if it does not exist."""
        return self._aid_to_accessory[aid]

    def aid_or_none(self, aid: int) -> Accessory | None:
        """Return the accessory with the given aid or None if it does not exist."""
        return self._aid_to_accessory.get(aid)

    def has_aid(self, aid: int) -> bool:
        """Return True if the given aid exists."""
        return aid in self._aid_to_accessory

    def process_changes(
        self, changes: typed_dicts.Response
    ) -> set[CharacteristicKey]:
        """Process changes from a HomeKit controller.

        Returns a set of the changes that were applied.
        """
        changed: set[CharacteristicKey] = set()
        for aid_iid, value in changes.items():
            (aid, iid) = aid_iid
            if not (char := self.aid(aid).characteristics.iid(iid)):
                continue

            if "value" in value:
                if char.set_value(value["value"]) or char.type in EVENT_CHARACTERISTICS:
                    changed.add(aid_iid)

            previous_status = char.status
            char.status = to_status_code(value.get("status") or 0)
            if previous_status != char.status:
                changed.add(aid_iid)

        return changed

from typing import Any, NamedTuple

type Value = Any


class CharacteristicKey(NamedTuple):
    aid: int
    iid: int


class CharacteristicKeyValue(NamedTuple):
    aid: int
    iid: int
    value: Value

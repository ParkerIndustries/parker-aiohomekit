#
# Copyright 2022 aiohomekit team # TODO: check and update the license
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Mechanism to cache characteristic database.

It is slow to query the BLE characteristics to find their iid and
signatures. We only need to do this work when the cn has incremented.

This interface must be kept compatible with Home Assistant. This is a
dumb implementation for development and CLI usage.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any, Protocol, TypedDict

import aiohomekit.hkjson as hkjson
from lark.exceptions import UnexpectedToken

logger = logging.getLogger(__name__)


class Pairing(TypedDict):
    """A versioned map of entity metadata as presented by aiohomekit."""

    config_num: int
    accessories: list[Any]
    broadcast_key: str | None
    state_num: int | None

class StorageLayout(TypedDict):
    """Cached pairing metadata needed by aiohomekit."""

    pairings: dict[str, Pairing]

class CharacteristicCacheType(Protocol): # TODO: split classes into files

    def get_map(self, homekit_id: str) -> Pairing | None:
        pass

    def async_create_or_update_map(
        self,
        homekit_id: str,
        config_num: int,
        accessories: list[Any],
        broadcast_key: str | None = None,
        state_num: int | None = None,
    ) -> Pairing:
        pass

    def async_delete_map(self, homekit_id: str):
        pass

class CharacteristicCacheMemory:

    def __init__(self):
        """Create a new entity map store."""
        self.storage_data: dict[str, Pairing] = {}

    def get_map(self, homekit_id: str) -> Pairing | None:
        """Get a pairing cache item."""
        return self.storage_data.get(homekit_id)

    def async_create_or_update_map(
        self,
        homekit_id: str,
        config_num: int,
        accessories: list[Any],
        broadcast_key: str | None = None,
        state_num: int | None = None,
    ) -> Pairing:
        """Create a new pairing cache."""
        data = Pairing(
            config_num=config_num,
            accessories=accessories,
            broadcast_key=broadcast_key,
            state_num=state_num,
        )
        self.storage_data[homekit_id] = data
        return data

    def async_delete_map(self, homekit_id: str):
        """Delete pairing cache."""
        if homekit_id not in self.storage_data:
            return

        self.storage_data.pop(homekit_id)

class CharacteristicCacheFile(CharacteristicCacheMemory):
    def __init__(self, location: pathlib.Path):
        """Create a new entity map store."""
        super().__init__()

        self.location = location
        if not location.exists():
            return # TODO: try create, log

        with open(location, encoding="utf-8") as fp:
            try:
                self.storage_data = hkjson.loads(fp.read())["pairings"]
                # print('CLI | Loaded characteristics: ', self.storage_data)
            except hkjson.JSON_DECODE_EXCEPTIONS as e:
                self._do_save() # write a correct empty schema to replace the corrupted cache
                logger.debug(
                    f"Characteristic cache was corrupted, proceeding with cold cache: {e}. Rewriting cache file with in-memory snapshot: {self.storage_data}"
                )
            except (UnexpectedToken, TypeError, KeyError) as e:
                self._do_save() # write a correct schema to replace the corrupted cache
                logger.debug(
                    f"Characteristic cache was corrupted, proceeding with cold cache: {e}. Rewriting cache file with in-memory snapshot: {self.storage_data}"
                )

    def async_create_or_update_map(
        self,
        homekit_id: str,
        config_num: int,
        accessories: list[Any], # TODO: better type annotation
        broadcast_key: str | None = None, # TODO: check broadcast_key: str vs bytes everywhere
        state_num: int | None = None,
    ) -> Pairing:
        data = super().async_create_or_update_map(
            homekit_id, config_num, accessories, broadcast_key, state_num
        )
        self._do_save()
        return data

    def async_delete_map(self, homekit_id: str):
        super().async_delete_map(homekit_id)
        self._do_save()

    def _do_save(self):
        with open(self.location, mode="w", encoding="utf-8") as fp:
            fp.write(hkjson.dumps(self._data_to_save()))

    def _data_to_save(self) -> StorageLayout:
        """Return data of entity map to store in a file."""
        return StorageLayout(pairings=self.storage_data if self.storage_data else {})

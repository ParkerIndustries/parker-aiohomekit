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
from uuid import UUID
from typing import Any, Protocol

import aiohomekit.hkjson as hkjson
from aiohomekit.model.characteristics.characteristic import Characteristics
from aiohomekit.models.accessories import AccessoriesState
from lark.exceptions import UnexpectedToken

from aiohomekit.storage.storage import DictStorageProtocol

logger = logging.getLogger(__name__)


class CharacteristicsStorageProtocol(DictStorageProtocol[UUID, AccessoriesState]): ...

class CharacteristicsStorageMemory(DictStorageMemory[UUID, AccessoriesState]): ...

class CharacteristicsStorageFile(DictStorageFile[UUID, AccessoriesState]): ...

#
# Copyright 2019 aiohomekit team
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
#
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any

import aiohomekit.hkjson as hkjson
from aiohomekit.protocol.statuscodes import to_status_code
from aiohomekit.uuid import normalize_uuid

from . import entity_map
from .categories import Categories
from .characteristics import (
    EVENT_CHARACTERISTICS,
    Characteristic,
    CharacteristicFormats,
    CharacteristicPermissions,
    CharacteristicsTypes,
)
from .feature_flags import FeatureFlags
from .services import Service, ServicesTypes

__all__ = [
    "Categories",
    "CharacteristicPermissions",
    "CharacteristicFormats",
    "FeatureFlags",
    "Accessory",
    "Service",
    "ServiceTypes",
    "Transport",
]

NEEDS_POLLINGS_CHARS = {
    CharacteristicsTypes.VENDOR_EVE_ENERGY_WATT,
    CharacteristicsTypes.VENDOR_CONNECTSENSE_ENERGY_WATT,
}

class Transport(Enum):
    BLE = "ble"
    COAP = "coap"
    IP = "ip"

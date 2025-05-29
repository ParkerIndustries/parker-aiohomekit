#
# Copyright 2022 aiohomekit team
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
from typing import Self

from abc import ABCMeta, abstractmethod
from collections.abc import AsyncIterable, Awaitable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
import logging
from typing import Any, final

from aiohomekit.model.accessories import Accessories, AccessoriesState
from aiohomekit.model.transport_type import TransportType
from aiohomekit.model.categories import Categories
from aiohomekit.model.characteristics.characteristic_types import CharacteristicsTypes
from aiohomekit.model.services.service_types import ServicesTypes
from aiohomekit.model.status_flags import StatusFlags
from aiohomekit.utils import (
    async_create_task,
    deserialize_broadcast_key,
    serialize_broadcast_key,
)

logger = logging.getLogger(__name__)

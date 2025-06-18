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

from functools import lru_cache
from uuid import UUID

BASE_UUID = "-0000-1000-8000-0026BB765291"


@lru_cache(maxsize=1024)
def shorten_uuid(value: str | UUID) -> str:
    """
    Returns the shortned version of a UUID.

    This only applies to official HK services and characteristics.
    """

    if isinstance(value, UUID):
        value = str(value)

    value = value.upper()

    if value.endswith(BASE_UUID):
        value = value.split("-", 1)[0]
        return value.lstrip("0")

    return str(normalize_uuid(value)).upper()


@lru_cache(maxsize=1024)
def normalize_uuid(value: int | str | UUID) -> UUID:
    """
    Returns a normalized UUID.

    This includes postfixing -0000-1000-8000-0026BB765291 and ensuring the case.
    """

    if isinstance(value, UUID):
        return value

    if isinstance(value, int):
        value = str(value)

    if isinstance(value, str):
        value = value.upper()

    if len(value) <= 8:
        prefix = "0" * (8 - len(value))
        return UUID(f"{prefix}{value}{BASE_UUID}")

    if len(value) == 36:
        return UUID(value)

    # Handle cases like 34AB8811AC7F4340BAC3FD6A85F9943B
    # Reject the rest
    try:
        return UUID(value.zfill(32))
    except ValueError:
        raise ValueError(f"{value} doesn't look like a valid UUID or short UUID")

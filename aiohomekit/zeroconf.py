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

"""Helpers for detecing homekit devices via zeroconf."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from zeroconf import (
    IPVersion,
    ServiceListener,
    Zeroconf,
)
from zeroconf.asyncio import AsyncServiceInfo

from aiohomekit.model.categories import Category
from aiohomekit.model.discovery_info import AbstractDiscoveryInfo
from aiohomekit.model.feature_flags import FeatureFlags
from aiohomekit.model.status_flags import StatusFlags
from aiohomekit.utils import make_uuid5


HAP_TYPE_TCP = "_hap._tcp.local."
HAP_TYPE_UDP = "_hap._udp.local."
CLASS_IN = 1
TYPE_PTR = 12

_TIMEOUT_MS = 3000

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class HomeKitService(AbstractDiscoveryInfo):
    type: str
    model: str
    feature_flags: FeatureFlags
    protocol_version: str

    address: str
    addresses: list[str]
    port: int

    @classmethod
    def from_service_info(cls, service: AsyncServiceInfo) -> HomeKitService:
        if not (addresses := service.ip_addresses_by_version(IPVersion.All)):
            raise ValueError("Invalid HomeKit Zeroconf record: Missing address")

        address: str | None = None
        #
        # Zeroconf addresses are guaranteed to be returned in LIFO (last in, first out)
        # order with IPv4 addresses first and IPv6 addresses second.
        #
        # This means the first address will always be the most recently added
        # address of the given IP version.
        #
        valid_addresses = [
            str(ip_addr)
            for ip_addr in addresses
            if not ip_addr.is_link_local and not ip_addr.is_unspecified
        ]
        if not valid_addresses:
            raise ValueError(
                "Invalid HomeKit Zeroconf record: Missing non-link-local or unspecified address"
            )
        address = valid_addresses[0]
        props = {
            k.lower(): v for k, v in service.decoded_properties.items() if v is not None
        }
        if "id" not in props:
            raise ValueError("Invalid HomeKit Zeroconf record: Missing device ID")

        return cls( # NOTE: looks important
            id=make_uuid5(props["id"].lower()),
            original_id=props["id"].lower(),
            name=service.name.removesuffix(f".{service.type}"),
            model=props.get("md", ""),
            config_num=int(props.get("c#", 0)),
            state_num=int(props.get("s#", 0)),
            feature_flags=FeatureFlags(int(props.get("ff", 0))),
            status_flags=StatusFlags(int(props.get("sf", 0))),
            category=Category(int(props.get("ci", 1))),
            protocol_version=props.get("pv", "1.0"),
            type=service.type,
            address=address,
            addresses=valid_addresses,
            port=service.port or 0,
        )

class EmptyZeroconfServiceListener(ServiceListener):

    def add_service(self, zc: Zeroconf, type_: str, name: str):
        """A service has been added."""

    def remove_service(self, zc: Zeroconf, type_: str, name: str):
        """A service has been removed."""

    def update_service(self, zc: Zeroconf, type_: str, name: str):
        """A service has been updated."""

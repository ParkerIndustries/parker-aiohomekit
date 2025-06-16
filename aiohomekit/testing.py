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

import base64
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Iterable

from aiohomekit import exceptions
from aiohomekit.model.characteristics.characteristic_key import CharacteristicKey
from aiohomekit.storage.characteristics_storage import CharacteristicsStorageMemory
from aiohomekit.storage.pairing_data_storage import PairingDataStorageMemory
from aiohomekit.controller.abstract import (
    AbstractController,
    AbstractDiscovery,
    AbstractPairing,
    FinishPairing,
)
from aiohomekit.exceptions import AccessoryNotFoundError
from aiohomekit.model.accessories import Accessories, AccessoriesState
from aiohomekit.model.typed_dicts import HKDeviceID, PairingData, Response
from aiohomekit.model.transport_type import TransportType
from aiohomekit.model.categories import Category
from aiohomekit.model.characteristics import Characteristic, CharacteristicsTypes
from aiohomekit.model.characteristics.characteristic_formats import (
    CharacteristicFormats,
)
from aiohomekit.model.status_flags import StatusFlags
from aiohomekit.protocol.statuscodes import HapStatusCode
from aiohomekit.uuid import normalize_uuid

_LOGGER = logging.getLogger(__name__)

FAKE_CAMERA_IMAGE = (
    b"/9j/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRE"
    b"NDg8QEBEQCgwSExIQEw8QEBD/yQALCAABAAEBAREA/8wABgAQEAX/2gAIAQEAAD8A0s8g/9k="
)


@dataclass
class FakeDescription:
    name: str = "TestDevice"
    id: str = "00:00:00:00:00:00"
    model: str = "TestDevice"
    status_flags: StatusFlags = StatusFlags.UNPAIRED
    config_num: int = 1
    state_num: int = 1
    category: Category = Category.OTHER


class FakeDiscovery(AbstractDiscovery):
    description = FakeDescription()

    def __init__(
        self, controller: FakeController, device_id: str, accessories: Accessories
    ):
        self.controller = controller
        self.accessories = accessories

        self.pairing_code = "111-22-333"

    def setup(self): ...

    @property
    def status_flags(self) -> StatusFlags:
        if self.description.id not in self.controller.pairings:
            return StatusFlags.UNPAIRED
        return StatusFlags(0)

    async def start_pairing(self) -> FinishPairing:
        if self.description.id in self.controller.pairings:
            raise exceptions.AlreadyPairedError(f"{self.description.id} already paired")

        async def finish_pairing(pairing_code: str) -> PairingData:
            if pairing_code != self.pairing_code:
                raise exceptions.AuthenticationError("M4")

            discovery = self.controller._discoveries[self.description.id]
            discovery.description = FakeDescription(status_flags=0)

            pairing_data = {}
            # pairing_data["AccessoryIP"] = self.address
            # pairing_data["AccessoryPort"] = self.port
            pairing_data["AccessoryPairingID"] = discovery.description.id
            pairing_data["Connection"] = "Fake"

            self.controller.pairings[discovery.description.id] = FakePairing(pairing_data, self.accessories)

            return pairing_data

        return finish_pairing

    async def identify(self):
        """Trigger an identify routinue."""


class PairingTester:
    """
    A holding class for test-only helpers.

    This is done to minimize the difference between a FakePairing and a real pairing.
    """

    def __init__(self, pairing: FakePairing, accessories: Accessories):
        self.pairing = pairing
        self.events_enabled = True

        self.characteristics = {}
        self.services = {}

        for accessory in accessories:
            for service in accessory.services:
                service_map = {}
                for char in service.characteristics:
                    self.characteristics[(accessory.aid, char.iid)] = char
                    service_map[char.type] = char
                    if char.type == CharacteristicsTypes.NAME:
                        self.services[char.get_value()] = service_map

    def set_events_enabled(self, value):
        self.events_enabled = value

    def update_named_service(self, name: str, new_values):
        """
        Finds a named service then sets characteristics by type.

        pairing.test.update_named_service("kitchen lamp", {
            CharacteristicsTypes.ON: True
        })

        Triggers events if enabled.
        """
        if name not in self.services:
            raise RuntimeError(f"Fake error: service {name!r} not found")

        service = self.services[name]

        changed = []
        for uuid, value in new_values.items():
            uuid = normalize_uuid(uuid)

            if uuid not in service:
                raise RuntimeError(
                    f"Unexpected characteristic {uuid!r} applied to service {name!r}"
                )

            char: Characteristic = service[uuid]
            changed.append((char.parent_service.accessory.aid, char.iid, value))

        self._send_events(changed)

    def update_aid_iid(self, characteristics):
        self._send_events(characteristics)

    def set_aid_iid_status(self, aid_iid_statuses: list[tuple[int, int, int]]):
        """Set status for an aid iid pair."""
        event = {
            CharacteristicKey(aid, iid): {"status": status} for aid, iid, status in aid_iid_statuses
        }

        if not event:
            return

        for listener in self.pairing._characteristic_observers:
            try:
                listener(self.pairing.id, event)
            except Exception:
                _LOGGER.exception("Unhandled error when processing event")

    def _send_events(self, characteristics):
        if not self.events_enabled:
            return

        event = {}
        for aid, iid, value in characteristics:
            char: Characteristic = self.characteristics[(aid, iid)]
            if char.format == CharacteristicFormats.bool:
                value = bool(value)
            event[(aid, iid)] = {"value": value}

        if not event:
            return

        for listener in self.pairing._characteristic_observers:
            try:
                listener(self.pairing.id, event)
            except Exception:
                _LOGGER.exception("Unhandled error when processing event")


class FakePairing(AbstractPairing):
    """
    A test fake that pretends to be a paired HomeKit accessory.

    This only contains methods and values that exist on the upstream Pairing
    class.
    """

    def __init__(
        self,
        pairing_data: PairingData,
        accessories: Accessories | None = None,
    ):
        """Create a fake pairing from an accessory model."""
        super().__init__(pairing_data)

        if accessories is None:
            accessories = Accessories()

        self._initial_accessories_state = AccessoriesState(accessories, 0)

        self._accessories_state = None
        self.pairing_data: dict[str, str] = {}
        self.available = True

        self.testing = PairingTester(self, accessories)

    @property
    def is_connected(self) -> bool:
        return True

    @property
    def is_available(self) -> bool:
        return True

    @property
    def transport(self) -> TransportType:
        transport_type = self.pairing_data.get("Connection", "IP")
        return {
            "BLE": TransportType.BLE,
            "CoAP": TransportType.COAP,
            "IP": TransportType.IP,
        }.get(transport_type, TransportType.IP)

    @property
    def poll_interval(self) -> timedelta:
        """Returns how often the device should be polled."""
        return timedelta(minutes=1)

    async def close(self):
        """Close the connection."""

    def _ensure_connected(self):
        if not self.available:
            raise AccessoryNotFoundError("Accessory not found")
        if not self._accessories_state:
            self._accessories_state = self._initial_accessories_state

    async def identify(self) -> bool:
        """Identify the accessory."""
        self._ensure_connected()
        return True

    async def list_pairings(self):
        """List pairing."""
        return []

    async def remove_pairing(self, pairing_id: HKDeviceID | None = None) -> bool:
        """Remove a pairing."""
        self._ensure_connected()
        return True

    async def populate_accessories_state(
        self, force_update: bool = False, attempts: int | None = None
    ) -> bool:
        """Populate the state of all accessories.

        This method should try not to fetch all the accessories unless
        we know the config num is out of date or force_update is True
        """
        self._ensure_connected()
        return True

    async def _process_config_changed(self, config_num: int):
        await self.fetch_accessories_and_characteristics(force_update=True)
        self._accessories_state = AccessoriesState(
            self._accessories_state.accessories, config_num
        )
        self._callback_config_changed(config_num)

    async def _process_disconnected_events(self):
        """Process any events that happened while we were disconnected."""

    async def _do_fetch_accessories_and_characteristics(self):
        """Fake implementation of _fetch_accessories_and_characteristics."""
        self._ensure_connected()
        return self.accessories_state

    async def get_characteristics(self, characteristics, include_meta: bool = False, include_perms: bool = False, include_type: bool = False, include_events: bool = False):
        """Fake implementation of get_characteristics."""
        self._ensure_connected()

        results = {}
        for aid, cid in characteristics:
            accessory = self.accessories.aid(aid)
            char = accessory.characteristics.iid(cid)
            if char.status != HapStatusCode.SUCCESS:
                results[(aid, cid)] = {"status": char.status.value}
                continue
            results[(aid, cid)] = {"value": char.get_value()}

        return results

    async def put_characteristics(self, characteristics):
        """Fake implementation of put_characteristics."""
        self._ensure_connected()

        filtered = []
        results = {}
        for aid, cid, value in characteristics:
            accessory = self.accessories.aid(aid)
            char = accessory.characteristics.iid(cid)
            if char.status != HapStatusCode.SUCCESS:
                results[(aid, cid)] = {"status": char.status.value}
                continue
            filtered.append((aid, cid, value))
        self.testing.update_aid_iid(filtered)
        return results

    async def thread_provision(
        self,
        dataset: str,
    ):
        # This ultimately needs refactoring so that we can have multiple test transports loaded
        # rather than patching this one to be COAP.
        self.pairing_data["Connection"] = "CoAP"
        # self.controller.transport_type = TransportType.COAP # TODO: check

    async def image(self, accessory: int, width: int, height: int) -> bytes:
        self._ensure_connected()

        return base64.b64decode(FAKE_CAMERA_IMAGE)

    async def subscribe_characteristics(
        self, characteristics: Iterable[CharacteristicKey]
    ) -> Response:
        ...

    async def unsubscribe_characteristics(
        self, characteristics: Iterable[CharacteristicKey]
    ) -> Response:
        ...

class FakeController(AbstractController):
    """
    A test fake that pretends to be a paired HomeKit accessory.

    This only contains methods and values that exist on the upstream Controller
    class.
    """

    started: bool
    # discoveries: dict[str, FakeDiscovery]
    # pairings: dict[str, FakePairing]
    # aliases: dict[str, FakePairing]

    transport_type = TransportType.IP

    def __init__(
        self, zeroconf_instance=None, char_cache=None, bleak_scanner_instance=None
    ):
        super().__init__(FakeDiscovery, FakePairing, char_cache or CharacteristicsStorageMemory(), PairingDataStorageMemory())

    def add_device(self, accessories):
        device_id = "00:00:00:00:00:00"
        discovery = self._discoveries[device_id] = FakeDiscovery(
            self,
            device_id,
            accessories=accessories,
        )
        return discovery

    async def add_paired_device(self, accessories: Accessories, id: HKDeviceID):
        discovery = self.add_device(accessories)
        finish_pairing = await discovery.start_pairing()
        return await finish_pairing(discovery.pairing_code)

    async def start(self):
        self.started = True

    async def stop(self):
        self.started = False

    async def discover(
        self, timeout_sec: float = 10
    ) -> AsyncIterable[AbstractDiscovery]:
        for discovery in self._discoveries.values():
            yield discovery

    async def find(self, device_id, timeout_sec: float = 10) -> AbstractDiscovery:
        try:
            return self._discoveries[device_id]
        except KeyError:
            raise AccessoryNotFoundError(device_id)

    async def is_reachable(self, device_id: str, timeout_sec: float = 10) -> bool:
        return True

    async def remove_pairing(self, pairing_id: HKDeviceID):
        del self.pairings[pairing_id]
        await self.char_cache_storage.delete(pairing_id)

    def load_pairing(self, pairing_data):
        # This assumes a test has already preseed self.pairings with a fake via
        # add_paired_device
        pairing_id = pairing_data["AccessoryPairingID"]
        pairing = self.pairings[pairing_id]
        pairing.pairing_data = pairing_data
        return pairing

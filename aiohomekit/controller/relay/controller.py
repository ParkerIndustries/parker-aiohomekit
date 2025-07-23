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

import asyncio
from collections.abc import AsyncIterable
from contextlib import AsyncExitStack
from typing import Any, override

from bleak import BleakScanner
from zeroconf.asyncio import AsyncZeroconf

from aiohomekit.const import (
    BLE_TRANSPORT_SUPPORTED,
    COAP_TRANSPORT_SUPPORTED,
    IP_TRANSPORT_SUPPORTED,
)
from aiohomekit.controller.abstract import (
    AbstractController,
    AbstractDiscovery,
    AbstractPairing,
    GenericDiscoveryCallback,
)
from aiohomekit.exceptions import AccessoryNotFoundError
from aiohomekit.model.transport_type import TransportType
from aiohomekit.model.typed_dicts import HKDeviceID, PairingData
from aiohomekit.storage.characteristics_storage import CharacteristicsStorageProtocol
from aiohomekit.storage.pairing_data_storage import PairingDataStorageProtocol

type DiscoveryCallback = GenericDiscoveryCallback[AbstractController, AbstractDiscovery]


class Controller(AbstractController[Any, AbstractDiscovery, AbstractPairing]):
    """
    This class represents a HomeKit controller (normally your iPhone or iPad).
    """

    def __init__(
        self,
        char_cache: CharacteristicsStorageProtocol,
        pairing_data_storage: PairingDataStorageProtocol,
        zeroconf_instance: AsyncZeroconf | None = None,
        bleak_scanner_instance: BleakScanner | None = None,
    ):
        """
        :param zeroconf_instance: optional AsyncZeroconf instance to use
        :param char_cache: optional CharacteristicCache to use
        :param bleak_scanner_instance: optional BleakScanner instance to use
        :param pairing_data_storage: optional storage for pairing data
        """
        super().__init__(
            AbstractDiscovery, AbstractPairing, char_cache, pairing_data_storage
        )

        self._zeroconf_instance = zeroconf_instance
        self._bleak_scanner_instance = bleak_scanner_instance
        self._transports: dict[TransportType, AbstractController] = {}
        self._tasks = AsyncExitStack()

    @property
    def transport_type(self) -> TransportType:
        # return {TransportType.IP, TransportType.COAP, TransportType.BLE} # TODO: make this prop a set?
        raise NotImplementedError(
            "Relay Controller does not have a transport type, it is a combination of all transports"
        )

    @override
    async def start(self):
        if IP_TRANSPORT_SUPPORTED or self._zeroconf_instance:
            self._zeroconf_instance = self._zeroconf_instance or AsyncZeroconf()
            from ..zeroconf.ip.controller import (
                IpController,  # pylint: disable=import-outside-toplevel
            )

            await self._register_backend(
                IpController(
                    self.char_cache_storage,
                    self.pairing_data_storage,
                    self._zeroconf_instance,
                )
            )

        if COAP_TRANSPORT_SUPPORTED:
            self._zeroconf_instance = self._zeroconf_instance or AsyncZeroconf()
            from ..zeroconf.coap.controller import (
                CoAPController,  # pylint: disable=import-outside-toplevel
            )

            await self._register_backend(
                CoAPController(
                    self.char_cache_storage,
                    self.pairing_data_storage,
                    self._zeroconf_instance,
                )
            )

        if BLE_TRANSPORT_SUPPORTED or self._bleak_scanner_instance:
            from ..ble.controller import (
                BleController,  # pylint: disable=import-outside-toplevel
            )

            await self._register_backend(
                BleController(
                    self.char_cache_storage,
                    self.pairing_data_storage,
                    self._bleak_scanner_instance,
                )
            )

    async def _register_backend(self, controller: AbstractController):
        controller.on_discovery(self._call_discovery_callback)
        self._transports[controller.transport_type] = (
            await self._tasks.enter_async_context(controller)
        )

    # Properties override to avoid duplicate storage

    @property
    @override
    def _pairings(self) -> dict[HKDeviceID, AbstractPairing]:
        """Returns all pairings from all transports"""
        pairings = {}
        for transport in self._transports.values():
            pairings.update(transport.pairings)
        return pairings

    @_pairings.setter
    @override
    def _pairings(self, value: dict[HKDeviceID, AbstractPairing]):  # type: ignore[override]
        pass  # do nothing, pairings are managed by transports

    @property
    @override
    def _discoveries(self) -> dict[HKDeviceID, AbstractDiscovery]:
        """Returns all discoveries from all transports"""
        discoveries = {}
        for transport in self._transports.values():
            discoveries.update(transport._discoveries)
        return discoveries

    @_discoveries.setter
    @override
    def _discoveries(self, value: dict[HKDeviceID, AbstractDiscovery]):  # type: ignore[override]
        pass  # do nothing, discoveries are managed by transports

    # Methods

    @override
    async def stop(self):
        await self._tasks.aclose()

    @override
    async def is_reachable(
        self, device_id: HKDeviceID, timeout_sec: float = 10
    ) -> bool:
        try:
            for transport in self._transports.values():
                if await transport.is_reachable(device_id, timeout_sec):  # parallel?
                    return True
            return False
        except Exception:
            return False

    @override
    async def discover(
        self, timeout_sec: float = 10
    ) -> AsyncIterable[AbstractDiscovery]:
        # TODO: check if timeout is needed, looks like it's neved used; fix pyright override
        """Returns already discovered and cached devices"""
        for transport in self._transports.values():  # TODO: parallel?
            async for device in transport.discover(timeout_sec):
                yield device

    @override
    def load_pairing(self, pairing_data: PairingData) -> AbstractPairing | None:
        if pairing_data["Connection"] in self._transports \
           and (pairing := self._transports[pairing_data["Connection"]].load_pairing(pairing_data)):
            return pairing

    @override
    async def remove_pairing(self, pairing_id: HKDeviceID) -> AbstractPairing:
        for transport in self._transports.values():
            if pairing_id in transport.pairings:
                return await transport.remove_pairing(pairing_id)
        raise AccessoryNotFoundError(
            f'Pairing "{pairing_id}" is not found in any transport.'
        )

    @override
    async def find(
        self, device_id: HKDeviceID, timeout_sec: float = 30.0
    ) -> AbstractDiscovery:
        pending = []

        for transport in self._transports.values():
            pending.append(asyncio.create_task(transport.find(device_id, timeout_sec)))

        try:
            while pending:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for result in done:
                    try:
                        return result.result()
                    except AccessoryNotFoundError:
                        continue
        finally:
            [task.cancel() for task in pending]
            for task in pending:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        raise AccessoryNotFoundError(f"Accessory with device id {device_id} not found")

    # Private

    def _call_discovery_callback(self, controller: AbstractController, discovery: AbstractDiscovery):
        if self._on_discovery_callback:
            self._on_discovery_callback(controller, discovery)

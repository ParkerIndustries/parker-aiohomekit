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
from asyncio.log import logger
from collections.abc import AsyncIterable
from contextlib import AsyncExitStack
from typing import Any
from typing_extensions import override
from uuid import UUID

from bleak import BleakScanner
from zeroconf.asyncio import AsyncZeroconf

from aiohomekit.characteristic_cache import (
    CharacteristicCacheMemory,
    CharacteristicCacheType,
)
from aiohomekit.controller.abstract.controller import (
    AbstractController,
    AbstractDiscovery,
    AbstractPairing,
    TransportType,
)
from aiohomekit.storage.pairing_data_storage import PairingDataStorageProtocol, PairingData

from ..const import (
    BLE_TRANSPORT_SUPPORTED,
    COAP_TRANSPORT_SUPPORTED,
    IP_TRANSPORT_SUPPORTED,
)
from ..exceptions import (
    AccessoryNotFoundError,
    TransportNotSupportedError,
)


class Controller(AbstractController[AbstractDiscovery, AbstractPairing]):
    """
    This class represents a HomeKit controller (normally your iPhone or iPad).
    """

    def __init__(
        self,
        char_cache: CharacteristicCacheType,
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
            char_cache=char_cache or CharacteristicCacheMemory(),
            pairing_data_storage=pairing_data_storage
        )

        self._zeroconf_instance = zeroconf_instance
        self._bleak_scanner_instance = bleak_scanner_instance
        self._transports: dict[TransportType, AbstractController] = {}
        self._tasks = AsyncExitStack()

    @override
    async def start(self):
        if IP_TRANSPORT_SUPPORTED or self._zeroconf_instance:
            from ..zeroconf.ip.controller import (
                IpController,  # pylint: disable=import-outside-toplevel
            )

            await self._register_backend(
                IpController(
                    char_cache=self.char_cache_storage,
                    pairing_data_storage=self.pairing_data_storage,
                    zeroconf_instance=self._zeroconf_instance,
                )
            )

        if COAP_TRANSPORT_SUPPORTED:
            from ..zeroconf.coap.controller import (
                CoAPController,  # pylint: disable=import-outside-toplevel
            )

            await self._register_backend(
                CoAPController(
                    char_cache=self.char_cache_storage,
                    pairing_data_storage=self.pairing_data_storage,
                    zeroconf_instance=self._zeroconf_instance,
                )
            )

        if BLE_TRANSPORT_SUPPORTED or self._bleak_scanner_instance:
            from ..ble.controller import (
                BleController,  # pylint: disable=import-outside-toplevel
            )

            await self._register_backend(
                BleController(
                    char_cache=self.char_cache_storage,
                    pairing_data_storage=self.pairing_data_storage,
                    bleak_scanner_instance=self._bleak_scanner_instance,
                )
            )

        await self._load_pairings_from_storage()

    async def _register_backend(self, controller: AbstractController):
        self._transports[controller.transport_type] = await self._tasks.enter_context(controller)

    @override
    async def stop(self):
        await self._tasks.aclose()

    @override
    async def find(self, device_id: str, timeout_sec: float = 30.0) -> AbstractDiscovery:

        pending = []

        for transport in self._transports.values():
            pending.append(
                asyncio.create_task(transport.find(device_id, timeout))
            )

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

    @override
    async def is_reachable(self, device_id: str, timeout_sec: float = 10) -> bool:
        try:
            for transport in self._transports.values():
                if await transport.is_reachable(device_id, timeout_sec):
                    return True
            return False
        except Exception:
            return False

    @override
    async def discover(self, timeout_sec: float = 10) -> AsyncIterable[AbstractDiscovery]: # TODO: check if timeout is needed, looks like it's neved used; fix pyright override
        '''Returns already discovered and cached devices'''
        for transport in self._transports.values(): # TODO: parallel
            async for device in transport.discover(timeout):
                yield device

    @override
    def on_discovery(self, callback: OnDiscoveryCallback):
        for transport in self._transports.values():
            transport.on_discovery(callback)

    @override
    def load_pairing(self, id: UUID, pairing_data: PairingData) -> AbstractPairing:
        for transport in self._transports.values():
            if pairing := transport.load_pairing(id, pairing_data):
                self._pairings[pairing_data["AccessoryPairingID"]] = pairing

    def _transport_for_pairing(self, pairing: AbstractPairing) -> AbstractController:
        for transport in self._transports.values():
            if pairing.transport_type == transport.transport_type:
                return transport

    # def save_data(self, filename: str): # TODO: c'mon, refactor to pairings_storage protocol and call internally on change
    #     """
    #     Saves the pairing data of the controller to a file.

    #     :param filename: the file name of the pairing data
    #     :raises ConfigSavingError: if the config could not be saved. The reason is given in the message.
    #     """
    #     aliases = {}
    #     # print('RC | Running edited save_data...')
    #     # print('RC | pairings file: ', filename)

    #     for controller in [self,] + list(self.transports.values()):
    #         # print('Checking: ', controller, len(controller.aliases), len(controller.pairings))
    #         for alias, pairing in controller.pairings.items():
    #             aliases[alias] = pairing.pairing_data

    #     # print('RC | Gathered data: ', aliases)

    #     path = pathlib.Path(filename)

    #     if not path.parent.exists():
    #         path.parent.mkdir(parents=True, exist_ok=True)

    #     try:
    #         with open(filename, mode="w", encoding="utf-8") as output_fp:
    #             output_fp.write(hkjson.dumps_indented(aliases))
    #     except PermissionError:
    #         raise ConfigSavingError(
    #             f'Could not write "{filename}" due to missing permissions'
    #         )
    #     except FileNotFoundError:
    #         raise ConfigSavingError(
    #             'Could not write "{f}" because it (or the folder) does not exist'.format(
    #                 f=filename
    #             )
    #         )

    # async def remove_pairing(self, id: UUID):
    #     """
    #     Remove a pairing between the controller and the accessory. The pairing data is delete on both ends, on the
    #     accessory and the controller.

    #     Important: no automatic saving of the pairing data is performed. If you don't do this, the accessory seems still
    #         to be paired on the next start of the application.

    #     :param alias: the controller's alias for the accessory
    #     :raises AuthenticationError: if the controller isn't authenticated to the accessory.
    #     :raises AccessoryNotFoundError: if the device can not be found via zeroconf
    #     :raises UnknownError: on unknown errors
    #     """
    #     if alias not in self.aliases:
    #         raise AccessoryNotFoundError(f'Alias "{alias}" is not found.')

    #     pairing = self.aliases[alias]

    #     try:
    #         # Remove the pairing from the controller first
    #         # so that it stops getting updates that might
    #         # trigger a disconnected event poll.
    #         self.aliases.pop(alias, None)
    #         pairing.controller.aliases.pop(alias, None) # TODO: call child.remove_pairing instead

    #         self.pairings.pop(pairing.id, None)
    #         pairing.controller.pairings.pop(pairing.id, None)

    #         primary_pairing_id = pairing.pairing_data["iOSDeviceId"]

    #         await pairing.remove_pairing(primary_pairing_id)

    #         await pairing.close()

    #     finally:
    #         self._char_cache.delete_map(pairing.id)

    #     # TODO: save the state

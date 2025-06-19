from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable
import logging
from typing import override

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakDBusError, BleakError

from aiohomekit.controller.abstract import AbstractController
from aiohomekit.controller.ble.manufacturer_data import (
    APPLE_MANUFACTURER_ID,
    HOMEKIT_ADVERTISEMENT_TYPE,
    HOMEKIT_ENCRYPTED_NOTIFICATION_TYPE,
    HomeKitAdvertisement,
    HomeKitEncryptedNotification,
)
from aiohomekit.controller.ble.pairing import BlePairing
from aiohomekit.exceptions import AccessoryNotFoundError
from aiohomekit.model.transport_type import TransportType
from aiohomekit.model.typed_dicts import HKDeviceID, PairingData
from aiohomekit.storage.characteristics_storage import CharacteristicsStorageProtocol
from aiohomekit.storage.pairing_data_storage import PairingDataStorageProtocol
from aiohomekit.utils import asyncio_timeout

from .discovery import BleDiscovery

logger = logging.getLogger(__name__)

class BleController(AbstractController):

    def __init__(
        self,
        char_cache_storage: CharacteristicsStorageProtocol,
        pairing_data_storage: PairingDataStorageProtocol,
        bleak_scanner_instance: BleakScanner | None = None,
    ):
        super().__init__(
            BleDiscovery,
            BlePairing,
            char_cache_storage,
            pairing_data_storage,
        )
        self._scanner = bleak_scanner_instance
        self._ble_futures: dict[str, list[asyncio.Future[BLEDevice]]] = {}

    @property
    def transport_type(self) -> TransportType:
        return TransportType.BLE

    @override
    async def start(self):
        logger.debug("Starting BLE controller with instance: %s", self._scanner)
        if not self._scanner:
            try:
                self._scanner = BleakScanner()
            except (FileNotFoundError, BleakDBusError, BleakError) as e:
                logger.debug(
                    "Failed to init scanner, HAP-BLE not available: %s", str(e)
                )
                self._scanner = None
                return

        try:
            self._scanner.register_detection_callback(self._device_detected)
            await self._scanner.start()
        except (FileNotFoundError, BleakDBusError, BleakError) as e:
            logger.debug("Failed to start scanner, HAP-BLE not available: %s", str(e))
            self._scanner = None

    @override
    async def stop(self, *args):
        if self._scanner:
            await self._scanner.stop()
            self._scanner.register_detection_callback(None)
            self._scanner = None

    @override
    async def is_reachable(self, device_id: HKDeviceID, timeout_sec: float = 10) -> bool:
        """Check if a device is reachable on the network."""
        return bool(
            (discovery := self._discoveries.get(device_id))
            and self._scanner
            and discovery.device.address in self._scanner.discovered_devices_and_advertisement_data
        )

    @override
    async def find(self, device_id: HKDeviceID, timeout_sec: float = 10) -> BleDiscovery:
        if discovery := self._discoveries.get(device_id):
            logger.debug("Discovery for %s already found", device_id)
            return discovery

        logger.debug(
            "Discovery for hkid %s not found, waiting for advertisement with timeout: %s",
            device_id,
            timeout_sec,
        )
        future = asyncio.get_running_loop().create_future()
        try:
            async with asyncio_timeout(timeout_sec):
                return await future
        except asyncio.TimeoutError:
            logger.debug(
                "Timed out after %s waiting for discovery with hkid %s",
                timeout_sec,
                device_id,
            )
            raise AccessoryNotFoundError(
                f"Accessory with device id {device_id} not found"
            )
        finally:
            # if device_id not in self._ble_futures:
            #     return
            if future in self._ble_futures[device_id]:
                self._ble_futures[device_id].remove(future)
            if not self._ble_futures[device_id]:
                del self._ble_futures[device_id]

    @override
    async def discover(self, timeout_sec: float = 10) -> AsyncIterable[BleDiscovery]:
        for device in self._discoveries.values():
            yield device

    def load_pairing(
        self, pairing_data: PairingData
    ) -> BlePairing | None:
        if pairing_data["Connection"] != "BLE":
            return None

        device: BLEDevice | None = None
        description: HomeKitAdvertisement | None = None

        # if discovery := self._discoveries.get(id):
        #     device = discovery.device
        #     description = discovery.description

        pairing = self.pairings[pairing_data["AccessoryPairingID"]] = BlePairing(
            pairing_data#, device=device, description=description
        )
        return pairing

    def _device_detected(
        self, device: BLEDevice, advertisement_data: AdvertisementData
    ):
        manufacturer_data = advertisement_data.manufacturer_data
        if not (mfr_data := manufacturer_data.get(APPLE_MANUFACTURER_ID)):
            return

        elif mfr_data[0] == HOMEKIT_ENCRYPTED_NOTIFICATION_TYPE:
            try:
                data = HomeKitEncryptedNotification.from_manufacturer_data(
                    device.name or '', device.address, manufacturer_data
                )
            except ValueError:
                return

            if pairing := self.pairings.get(data.id):
                pairing._async_notification(data)

            return

        if mfr_data[0] != HOMEKIT_ADVERTISEMENT_TYPE:
            return

        try:
            data = HomeKitAdvertisement.from_manufacturer_data(
                device.name or '', device.address, manufacturer_data
            )
        except ValueError:
            return

        if old_discovery := self._discoveries.get(data.id):
            if (old_name := old_discovery.description.name) and (
                not (name := data.name)
                or (
                    old_name != old_discovery.device.address
                    and len(old_name) > len(name)
                )
            ):
                #
                # If we have a pairing and the name is longer than the one we
                # just received, we assume the name is more accurate and
                # update it.
                #
                # SHORTENED LOCAL NAME
                # The Shortened Local Name data type defines a shortened version
                # of the Local Name data type. The Shortened Local Name data type
                # shall not be used to advertise a name that is longer than the
                # Local Name data type.
                #
                data.name = old_name

        if pairing := self.pairings.get(data.id):
            pairing.process_description_update(data)
            pairing._async_ble_update(device, advertisement_data)

        if futures := self._ble_futures.get(data.id):
            discovery = BleDiscovery(device, data, advertisement_data)
            logger.debug("BLE device for %s found, fulfilling futures", data.id)
            for future in futures:
                future.set_result(discovery)
            futures.clear()

        if old_discovery:
            # We need to make sure we update the device details
            # in case they changed
            old_discovery._async_process_advertisement(device, data, advertisement_data)
            return

        self._discoveries[data.id] = BleDiscovery(device, data, advertisement_data)

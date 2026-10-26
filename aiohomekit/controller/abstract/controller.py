from abc import ABC, abstractmethod
import asyncio
from collections.abc import AsyncIterable
import logging
from typing import Callable, Self, final

from aiohomekit.exceptions import AccessoryNotFoundError
from aiohomekit.model.discovery_info import AbstractDiscoveryInfo
from aiohomekit.model.transport_type import TransportType
from aiohomekit.model.typed_dicts import HKDeviceID, PairingData
from aiohomekit.storage.characteristics_storage import CharacteristicsStorageProtocol
from aiohomekit.storage.pairing_data_storage import PairingDataStorageProtocol
from aiohomekit.utils import async_create_task

from .discovery import AbstractDiscovery
from .pairing import AbstractPairing

logger = logging.getLogger(__name__)

type GenericDiscoveryCallback[S, T] = Callable[[S, T], None]


class AbstractController[
    DiscoveryInfo: AbstractDiscoveryInfo,  # TODO: check if this should be inside AbstractDiscovery
    Discovery: AbstractDiscovery,
    Pairing: AbstractPairing,
](ABC):

    type DiscoveryCallback = GenericDiscoveryCallback[Self, Discovery]

    char_cache_storage: CharacteristicsStorageProtocol
    pairing_data_storage: PairingDataStorageProtocol

    _discoveries: dict[HKDeviceID, Discovery]
    _pairings: dict[HKDeviceID, Pairing]
    _on_discovery_callback: DiscoveryCallback | None = None

    def __init__(
        self,
        Discovery: type[
            Discovery
        ],  # anoying workaround for 'typing.TypeVar' object is not callable
        Pairing: type[Pairing],
        char_cache_storage: CharacteristicsStorageProtocol,
        pairing_data_storage: PairingDataStorageProtocol,
    ):
        self.Discovery = Discovery
        self.Pairing = Pairing
        self.char_cache_storage = char_cache_storage
        self.pairing_data_storage = pairing_data_storage
        self._pairing_cleanups: dict[HKDeviceID, list[Callable[[], None]]] = {}
        self._pairings = {}
        self._discoveries = {}

    # Abstract

    @property
    @abstractmethod
    def transport_type(self) -> TransportType:
        raise NotImplementedError(self.transport_type)

    @abstractmethod
    async def find(
        self, device_id: HKDeviceID, timeout_sec: float = 10
    ) -> Discovery | None: ...

    @abstractmethod
    async def is_reachable(
        self, device_id: HKDeviceID, timeout_sec: float = 10
    ) -> bool: ...

    @abstractmethod
    def discover(self, timeout_sec: float = 10) -> AsyncIterable[Discovery]: ...

    # Public

    @final
    @property
    def pairings(self) -> dict[HKDeviceID, Pairing]:
        return self._pairings

    @final
    @property
    def discoveries(self) -> dict[HKDeviceID, Discovery]:
        return self._discoveries

    # Implementations

    async def identify(self, id: HKDeviceID):
        pairing = self.pairings.get(id)
        if pairing is None:
            raise AccessoryNotFoundError(f"Pairing with ID {id} not found.")

        await pairing.identify()

    async def remove_pairing(self, pairing_id: HKDeviceID) -> Pairing:
        """
        Remove a pairing between the controller and the accessory. The pairing data is delete on both ends, on the
        accessory and the controller.

        :param alias: the controller's alias for the accessory
        :raises AuthenticationError: if the controller isn't authenticated to the accessory.
        :raises AccessoryNotFoundError: if the device can not be found via zeroconf
        :raises UnknownError: on unknown errors
        """

        if pairing_id not in self.pairings:
            raise AccessoryNotFoundError(f'Pairing "{pairing_id}" is not found.')

        pairing = self.pairings.pop(pairing_id)

        self._cleanup_pairing(pairing_id)

        await pairing.remove_pairing()
        await self.char_cache_storage.delete(pairing_id)
        await self.pairing_data_storage.delete(pairing_id)

        return pairing

    def on_discovery(self, callback: DiscoveryCallback):
        """Register a callback to be called when a device is discovered."""
        self._on_discovery_callback = callback

    async def start(self):
        await self.load_pairings_from_storage()

    async def stop(self):
        self._stop_observing()

        # Close every session and its reconnect loop; the next start loads fresh pairings
        pairings = list(self._pairings.values())
        self._pairings.clear()
        results = await asyncio.gather(
            *(pairing.shutdown() for pairing in pairings), return_exceptions=True
        )
        for pairing, result in zip(pairings, results, strict=True):
            if isinstance(result, Exception):
                logger.warning(f"{pairing.name}: Failed to shut down: {result!r}")

    async def load_pairings_from_storage(self):
        for pairing_data in (await self.pairing_data_storage.get_all()).values():
            try:
                await self.load_pairing(pairing_data)
            except Exception:
                # One broken pairing must not keep the controller and the other pairings down
                logger.exception(
                    f"Failed to load pairing {pairing_data.get('AccessoryPairingID')!r}"
                )

    async def load_pairing(self, pairing_data: PairingData) -> Pairing | None:
        if pairing_data["Connection"] != self.transport_type:
            return None

        accessory_id = pairing_data["AccessoryPairingID"]

        if not accessory_id:
            raise ValueError("Invalid pairing data: Missing accessory ID")

        try:
            accessories_state = await self.char_cache_storage.get(accessory_id)
        except Exception:
            # The pairing loads without it and fetches the data model on demand
            logger.exception(f"{accessory_id}: Failed to read the cached data model")
            accessories_state = None

        if replaced := self._pairings.pop(accessory_id.lower(), None):
            # e.g. a re-paired accessory: the old session must not keep reconnecting
            self._cleanup_pairing(accessory_id.lower())
            await replaced.shutdown()

        pairing = self._pairings[accessory_id.lower()] = self.Pairing(pairing_data)

        # No connection here: the accessory may be offline. The pairing connects on demand
        # or on discovery, which also repopulates the cache when it is missing or outdated (c#).
        if accessories_state:
            pairing.restore_accessories_state(accessories_state)

        if discovery := self._discoveries.get(accessory_id.lower()):
            pairing.process_description_update(discovery.description)

        # TODO: initial save NOTE: current commented code causes "dict changed size during iteration" error

        # await self.char_cache_storage.save(accessory_id, pairing.accessories_state)
        # await self.pairing_data_storage.save(accessory_id, pairing_data)

        # observe changes in pairing data and data model

        unsubscribes = []

        def _schedule_save_config(id: HKDeviceID, config_num: int):
            async_create_task(
                self.char_cache_storage.save(accessory_id, pairing.accessories_state)
            )

        unsubscribes.append(pairing.add_observer_for_config(_schedule_save_config))

        def _schedule_pairing_save(id: HKDeviceID, pairing_data: PairingData):
            async_create_task(self.pairing_data_storage.save(id, pairing_data))

        unsubscribes.append(
            pairing.add_observer_for_pairing_data(_schedule_pairing_save)
        )

        self._pairing_cleanups[accessory_id.lower()] = unsubscribes

        return pairing

    async def _on_pairing(self, pairing_data: PairingData):
        #  async_create_task(self.load_pairing(pairing_data))
        if pairing := await self.load_pairing(pairing_data):
            # so we return to the caller of finish_pairing with completely loaded pairing
            await pairing.fetch_accessories_and_characteristics(force_update=True)

    def _make_discovery(self, discovery_info: DiscoveryInfo) -> Discovery:
        return self.Discovery(discovery_info, self._on_pairing)

    def _stop_observing(self):
        for pairing_id in self._pairing_cleanups.copy():
            self._cleanup_pairing(pairing_id)

    def _cleanup_pairing(self, pairing_id: HKDeviceID):
        for cleanup in self._pairing_cleanups.pop(pairing_id):
            cleanup()

    # Context Manager

    @final
    async def __aenter__(self):
        await self.start()
        return self

    @final
    async def __aexit__(self, *args):
        await self.stop()

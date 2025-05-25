from abc import ABC, abstractmethod
import logging
from typing import Callable, AsyncIterable, Any
from uuid import UUID

from aiohomekit.storage.characteristics_storage import CharacteristicsStorageProtocol
from aiohomekit.storage.pairing_data_storage import PairingDataStorageProtocol

logger = logging.getLogger(__name__)


class AbstractController[
    DiscoveryInfo: Any,
    Discovery: AbstractDiscovery,
    Pairing: AbstractPairing
](ABC):

    OnDiscoveryCallback = Callable[[Self, Discovery], None]

    char_cache_storage: CharacteristicsStorageProtocol
    pairing_data_storage: PairingDataStorageProtocol

    _discoveries: dict[UUID, Discovery]
    _pairings: dict[UUID, Pairing]
    _on_discovery_callback: OnDiscoveryCallback | None = None

    def __init__(self, char_cache_storage: CharacteristicsStorageProtocol, pairing_data_storage: PairingDataStorageProtocol | None = None):
        self.char_cache_storage = char_cache_storage
        self.pairing_data_storage = pairing_data_storage
        self._pairing_cleanups: dict[UUID, list[Callable[[], None]]] = {}

    # Abstract

    @property
    @abstractmethod
    def transport_type(self) -> TransportType:
        raise NotImplementedError(self.transport_type)

    @abstractmethod
    async def identify(self, id: UUID): ...

    @abstractmethod
    async def fetch(self, id: UUID) -> Pairing: ...

    @abstractmethod
    async def find(self, device_id: str, timeout_sec: float = 10) -> Discovery: ...

    @abstractmethod
    async def is_reachable(self, device_id: str, timeout_sec: float = 10) -> bool: ...

    @abstractmethod
    async def discover(self, timeout_sec: float = 10) -> AsyncIterable[Discovery]: ...

    @abstractmethod
    async def start(self): ...

    @abstractmethod
    async def stop(self):
        self._stop_observing()

    # Public

    @final
    @property
    def pairings(self) -> dict[str, Pairing]: return self._pairings

    @final
    @property
    def discoveries(self) -> dict[str, Discovery]: return self._discoveries

    # Implementations

    @final
    def on_discovery(self, callback: OnDiscoveryCallback):
        """Register a callback to be called when a device is discovered."""
        self._on_discovery_callback = callback

    def load_pairings_from_storage(self):
        for pairing_data in self.pairing_data_storage.get_all():
            self.load_pairing(pairing_data["AccessoryPairingID"], pairing_data)

    def load_pairing(self, pairing_data: PairingData) -> Pairing | None:
        if pairing_data["Connection"] != self.transport_type:
            return None

        accessory_id = pairing_data.get("AccessoryPairingID")

        if not accessory_id:
            return None

        pairing = self._pairings[UUID(accessory_id)] = Pairing(pairing_data, self.pairing_data_storage.save)

        if discovery := self._discoveries.get(accessory_id):
            pairing.process_description_update(discovery.description)

        # observe pairing data changes and store unsubscribe callables
        unsubscribes = []
        unsubscribes.append(pairing.add_observer_for_config(lambda _: self.char_cache_storage.save(pairing.pairing_data)))
        unsubscribes.append(pairing.add_observer_for_pairing_data(self.pairing_data_storage.save))
        self._pairing_cleanups[UUID(accessory_id)] = unsubscribes

        return pairing

    def _on_pairing(self, pairing_data: PairingData):
        self.load_pairing(pairing_data)
        self.pairing_data_storage.save(pairing_data)

    def _make_discovery(self, discovery_info: DiscoveryInfo) -> Discovery:
        return Discovery(discovery_info, self._on_pairing)

    def _stop_observing(self):
        for unsubscribes in self._pairing_cleanups.values():
            for unsubscribe in unsubscribes:
                unsubscribe()
        self._pairing_cleanups.clear()

    # Context Manager

    @final
    async def __aenter__(self):
        await self.start()
        return self

    @final
    async def __aexit__(self, *args):
        await self.stop()

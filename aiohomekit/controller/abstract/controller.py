from abstract import ABC, abstractmethod
from typing import Callable, AsyncIterable, TypeVar
from uuid import UUID
from aiohomekit.model import Accessories
from aiohomekit.model.accessories.accessory_state import AccessoriesState


class AbstractController[Discovery: AbstractDiscovery, Pairing: AbstractPairing](ABC):

    OnDiscoveryCallback = Callable[[Self, Discovery], None]

    char_cache: CharacteristicsStorageProtocol
    pairing_data_storage: PairingDataStorageProtocol

    _discoveries: dict[UUID, Discovery]
    _on_discovery_callback: OnDiscoveryCallback | None = None

    def __init__(self, char_cache: CharacteristicsStorageProtocol, pairing_data_storage: PairingDataStorageProtocol):
        self.char_cache = char_cache
        self.pairing_data_storage = pairing_data_storage

    @property # TODO: abstractproperty
    def transport_type(self) -> TransportType:
        raise NotImplementedError(self.transport_type)

    @abstractmethod
    async def identify(id: UUID): ...

    @abstractmethod
    async def fetch(id: UUID) -> Pairing: ...

    @abstractmethod
    async def find(self, device_id: str, timeout_sec: int = 10) -> Discovery: ...

    @abstractmethod
    async def is_reachable(self, device_id: str, timeout_sec: int = 10) -> bool: ...

    @abstractmethod
    async def discover(self, timeout_sec: int = 10) -> AsyncIterable[Discovery]: ...

    @abstractmethod
    async def start(self): ...

    @abstractmethod
    async def stop(self): ...

    @final
    async def __aenter__(self):
        await self.async_start()
        return self

    @final
    async def __aexit__(self, *args):
        await self.async_stop()

    @final
    def on_discovery(self, callback: OnDiscoveryCallback):
        """Register a callback to be called when a device is discovered."""
        self._on_discovery_callback = callback

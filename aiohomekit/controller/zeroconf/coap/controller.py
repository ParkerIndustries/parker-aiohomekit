from __future__ import annotations

from zeroconf.asyncio import AsyncZeroconf

from aiohomekit.model.transport_type import HAPZeroconfType, TransportType
from aiohomekit.storage.characteristics_storage import CharacteristicsStorageProtocol
from aiohomekit.storage.pairing_data_storage import PairingDataStorageProtocol

from ..controller import ZeroconfController
from .discovery import CoAPDiscovery
from .pairing import CoAPPairing


class CoAPController(ZeroconfController[CoAPDiscovery, CoAPPairing]):

    def __init__(
        self,
        char_cache_storage: CharacteristicsStorageProtocol,
        pairing_data_storage: PairingDataStorageProtocol,
        zeroconf_instance: AsyncZeroconf,
    ):
        super().__init__(CoAPDiscovery, CoAPPairing, char_cache_storage, pairing_data_storage, zeroconf_instance)

    @property
    def transport_type(self) -> TransportType:
        return TransportType.COAP

    @property
    def _hap_type(self) -> str:
        return HAPZeroconfType.TCP.value

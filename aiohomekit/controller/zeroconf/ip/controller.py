from __future__ import annotations

from zeroconf.asyncio import AsyncZeroconf

from aiohomekit.model.transport_type import HAPZeroconfType, TransportType
from aiohomekit.storage.characteristics_storage import CharacteristicsStorageProtocol
from aiohomekit.storage.pairing_data_storage import PairingDataStorageProtocol

from ..controller import ZeroconfController
from .discovery import IpDiscovery
from .pairing import IpPairing


class IpController(ZeroconfController[IpDiscovery, IpPairing]):

    def __init__(
        self,
        char_cache_storage: CharacteristicsStorageProtocol,
        pairing_data_storage: PairingDataStorageProtocol,
        zeroconf_instance: AsyncZeroconf,
    ):
        super().__init__(
            IpDiscovery,
            IpPairing,
            char_cache_storage,
            pairing_data_storage,
            zeroconf_instance,
        )

    @property
    def transport_type(self) -> TransportType:
        return TransportType.IP

    @property
    def _hap_type(self) -> str:
        return HAPZeroconfType.TCP.value

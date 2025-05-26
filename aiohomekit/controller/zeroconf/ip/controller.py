from __future__ import annotations

from aiohomekit.controller.abstract import TransportType
from aiohomekit.controller.ip.discovery import IpDiscovery
from aiohomekit.controller.ip.pairing import IpPairing


class IpController(ZeroconfController[IpDiscovery, IpPairing]):

    def __init__(
        self,
        char_cache_storage: CharacteristicsStorageProtocol,
        pairing_data_storage: PairingDataStorageProtocol,
        zeroconf_instance: AsyncZeroconf,
    ):
        super().__init__(IpDiscovery, IpPairing, char_cache_storage, pairing_data_storage, zeroconf_instance)

    @property
    def transport_type(self) -> TransportType:
        return TransportType.IP

    @property
    def _hap_type(self) -> str:
        return IpTransport.TCP

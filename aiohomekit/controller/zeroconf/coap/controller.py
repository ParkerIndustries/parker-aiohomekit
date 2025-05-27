from __future__ import annotations

from typing import Any

from aiohomekit.controller.abstract import TransportType
from aiohomekit.controller.coap.discovery import CoAPDiscovery
from aiohomekit.controller.coap.pairing import CoAPPairing
from aiohomekit.zeroconf import HAP_TYPE_UDP, ZeroconfController


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
        return IpTransportType.UDP

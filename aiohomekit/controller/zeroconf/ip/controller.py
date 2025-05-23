from __future__ import annotations

from aiohomekit.controller.abstract import TransportType
from aiohomekit.controller.ip.discovery import IpDiscovery
from aiohomekit.controller.ip.pairing import IpPairing


class IpController(ZeroconfController[IpPairing, IpDiscovery]):

    @property
    def _hap_type(self) -> str:
        return IpTransport.TCP

    @property
    def transport_type(self) -> TransportType:
        return TransportType.IP

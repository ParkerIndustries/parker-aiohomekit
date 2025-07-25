from unittest.mock import AsyncMock

from aiohomekit import Controller
from aiohomekit.controller.zeroconf.ip import IpDiscovery, IpPairing
from aiohomekit.controller.zeroconf.protocol import ZeroconfDiscoveryInfo
from aiohomekit.model.categories import Category


async def test_pair(controller_and_unpaired_accessory: tuple[Controller, int]):
    controller, port = controller_and_unpaired_accessory

    discovery = IpDiscovery(
        ZeroconfDiscoveryInfo(
            name="Test",
            id="00:01:02:03:04:05",
            model="Test",
            feature_flags=0,
            status_flags=1,
            config_num=0,
            state_num=0,
            category=Category.OTHER,
            protocol_version="1.0",
            zc_type="_hap._tcp.local",
            address="127.0.0.1",
            addresses=["127.0.0.1"],
            port=port,
        ),
        AsyncMock(),
    )

    finish_pairing = await discovery.start_pairing()
    pairing_data = await finish_pairing("031-45-154")
    pairing = IpPairing(pairing_data)

    assert isinstance(pairing_data, dict), type(pairing_data)

    assert await pairing.get_characteristics([(1, 9)]) == {
        (1, 9): {"value": False},
    }


async def test_identify(controller_and_unpaired_accessory: tuple[Controller, int]):
    controller, port = controller_and_unpaired_accessory

    discovery = IpDiscovery(
        ZeroconfDiscoveryInfo(
            name="Test",
            id="00:01:02:03:04:05",
            model="Test",
            feature_flags=0,
            status_flags=0,
            config_num=0,
            state_num=0,
            category=Category.OTHER,
            protocol_version="1.0",
            zc_type="_hap._tcp.local",
            address="127.0.0.1",
            addresses=["127.0.0.1"],
            port=port,
        ),
        AsyncMock(),
    )

    identified = await discovery.identify()
    assert identified is True

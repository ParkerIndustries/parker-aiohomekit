from unittest.mock import AsyncMock, patch

import pytest

from aiohomekit import Controller
from aiohomekit.controller.zeroconf.ip import IpDiscovery, IpPairing
from aiohomekit.controller.zeroconf.protocol import ZeroconfDiscoveryInfo
from aiohomekit.crypto.srp import SrpClient, SrpServer
from aiohomekit.model.categories import Category
from aiohomekit.model.feature_flags import FeatureFlags
from aiohomekit.model.status_flags import StatusFlags


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

    await pairing.close()


@pytest.mark.parametrize(
    ("server_key", "client_key"),
    [
        # Private keys found by search for the setup code and salt below: B is 383 bytes unpadded
        (
            231858281150555932071473749489685419053,
            292688228404009964368565123456917403653,
        ),
        # The session key K starts with a zero byte
        (
            289056419680220080309933872999607432372,
            195111329545385468715040223447013214186,
        ),
    ],
    ids=["short B", "short K"],
)
async def test_pair_with_a_leading_zero_byte(
    controller_and_unpaired_accessory: tuple[Controller, int],
    server_key: int,
    client_key: int,
):
    _, port = controller_and_unpaired_accessory

    discovery = IpDiscovery(
        ZeroconfDiscoveryInfo(
            name="Test",
            id="00:01:02:03:04:05",
            model="Test",
            feature_flags=FeatureFlags(0),
            status_flags=StatusFlags.UNPAIRED,
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

    with (
        patch.object(SrpServer, "_create_salt_bytes", return_value=bytes(range(1, 17))),
        patch.object(SrpServer, "generate_private_key", return_value=server_key),
        patch.object(SrpClient, "generate_private_key", return_value=client_key),
    ):
        finish_pairing = await discovery.start_pairing()
        pairing_data = await finish_pairing("031-45-154")

    assert pairing_data["AccessoryPairingID"] == "12:34:56:00:01:0A"


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

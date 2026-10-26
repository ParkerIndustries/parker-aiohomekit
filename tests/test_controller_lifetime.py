import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from zeroconf.asyncio import AsyncZeroconf

from aiohomekit.controller.zeroconf.ip import IpPairing
from aiohomekit.controller.zeroconf.ip.controller import IpController
from aiohomekit.controller.zeroconf.protocol import ZeroconfDiscoveryInfo
from aiohomekit.model.accessories import Accessories, AccessoriesState
from aiohomekit.model.transport_type import TransportType
from aiohomekit.model.typed_dicts import PairingData
from aiohomekit.storage.characteristics_storage import CharacteristicsStorageMemory
from aiohomekit.storage.pairing_data_storage import PairingDataStorageMemory
from aiohomekit.testing.mock_zeroconf import get_mock_service_info
from aiohomekit.testing.utils import next_available_port

ACCESSORY_ID = "00:00:01:00:00:02"  # the id get_mock_service_info advertises
FIXTURE = Path(__file__).parent / "fixtures" / "koogeek_ls1.json"


def offline_pairing_data(accessory_id: str = ACCESSORY_ID) -> PairingData:
    return {
        "Connection": TransportType.IP,
        "iOSDeviceLTPK": "d708df2fbf4a8779669f0ccd43f4962d6d49e4274f88b1292f822edc3bcf8ed8",
        "iOSDeviceId": "decc6fa3-de3e-41c9-adba-ef7409821bfc",
        "iOSDeviceLTSK": "fa45f082ef87efc6c8c8d043d74084a3ea923a2253e323a7eb9917b4090c2fcc",
        "AccessoryLTPK": "7986cf939de8986f428744e36ed72d86189bea46b4dcdc8d9d79a3e4fceb92b9",
        "AccessoryPairingID": accessory_id,
        "AccessoryAddress": "127.0.0.1",
        "AccessoryPort": next_available_port(),  # nothing listens there
    }


def cached_state() -> AccessoriesState:
    return AccessoriesState(Accessories.from_file(FIXTURE), config_num=1)


async def make_controller(
    zeroconf: AsyncZeroconf, *pairings: tuple[PairingData, AccessoriesState | None]
) -> IpController:
    pairing_data_storage = PairingDataStorageMemory()
    char_cache_storage = CharacteristicsStorageMemory()
    for pairing_data, accessories_state in pairings:
        accessory_id = pairing_data["AccessoryPairingID"]
        await pairing_data_storage.save(accessory_id, pairing_data)
        if accessories_state:
            await char_cache_storage.save(accessory_id, accessories_state)
    return IpController(char_cache_storage, pairing_data_storage, zeroconf)


async def test_start_loads_stored_pairings_without_connecting(
    mock_asynczeroconf: AsyncZeroconf,
):
    state = cached_state()
    controller = await make_controller(
        mock_asynczeroconf, (offline_pairing_data(), state)
    )

    async with asyncio.timeout(2):
        await controller.start()

    pairing = controller.pairings[ACCESSORY_ID]
    assert pairing.accessories_state is state
    assert not pairing.is_connected
    assert pairing.connection._connector is None
    await controller.stop()


async def test_start_skips_a_pairing_that_fails_to_load(
    mock_asynczeroconf: AsyncZeroconf,
):
    controller = await make_controller(
        mock_asynczeroconf,
        (offline_pairing_data(accessory_id=""), None),
        (offline_pairing_data(), cached_state()),
    )

    async with asyncio.timeout(2):
        await controller.start()

    assert list(controller.pairings) == [ACCESSORY_ID]
    await controller.stop()


async def test_discovery_repopulates_a_pairing_without_cache():
    pairing = IpPairing(offline_pairing_data())
    description = ZeroconfDiscoveryInfo.from_service_info(get_mock_service_info())

    with patch.object(pairing, "_process_config_changed", AsyncMock()) as repopulate:
        pairing.process_description_update(description)
        await asyncio.sleep(0)

    repopulate.assert_awaited_once_with(description.config_num)
    await pairing.close()

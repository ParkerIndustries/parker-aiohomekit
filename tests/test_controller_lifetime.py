import asyncio
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from zeroconf.asyncio import AsyncZeroconf

from aiohomekit.controller.relay import Controller
from aiohomekit.controller.zeroconf.ip import IpPairing
from aiohomekit.controller.zeroconf.ip.controller import IpController
from aiohomekit.controller.zeroconf.protocol import ZeroconfDiscoveryInfo
from aiohomekit.exceptions import AuthenticationError
from aiohomekit.model.accessories import Accessories, AccessoriesState
from aiohomekit.model.transport_type import TransportType
from aiohomekit.model.typed_dicts import PairingData
from aiohomekit.storage.characteristics_storage import CharacteristicsStorageMemory
from aiohomekit.storage.pairing_data_storage import PairingDataStorageMemory
from aiohomekit.testing.mock_zeroconf import (
    AsyncServiceBrowserStub,
    get_mock_service_info,
)
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


def reconnect_loops() -> list[asyncio.Task]:
    return [
        task
        for task in asyncio.all_tasks()
        if getattr(task.get_coro(), "__qualname__", "")
        == "HomeKitConnection._reconnect"
    ]


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


@pytest.fixture
def shared_browser(
    mock_asynczeroconf: AsyncZeroconf,
) -> Iterator[AsyncServiceBrowserStub]:
    """The mock's _hap._tcp browser, found by the controller as someone else's browser."""
    with patch(
        "aiohomekit.controller.zeroconf.controller.AsyncServiceBrowser",
        AsyncServiceBrowserStub,
    ):
        yield mock_asynczeroconf.zeroconf.listeners[0]


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


async def test_stop_closes_sessions_before_a_restart(
    controller_and_paired_accessory: Controller,
):
    controller = controller_and_paired_accessory
    old = next(iter(controller.pairings.values()))
    await old.get_characteristics([(1, 9)])
    assert old.is_connected

    await controller.stop()

    assert not old.is_connected
    assert not reconnect_loops()
    assert controller.pairings == {}

    await controller.start()
    new = next(iter(controller.pairings.values()))
    await new.get_characteristics([(1, 9)])

    assert new is not old
    assert new.is_connected
    assert not old.is_connected


async def test_stop_shuts_every_pairing_down_when_one_fails(
    mock_asynczeroconf: AsyncZeroconf,
):
    controller = await make_controller(
        mock_asynczeroconf,
        (offline_pairing_data(accessory_id="00:00:00:00:00:01"), cached_state()),
        (offline_pairing_data(), cached_state()),
    )
    await controller.start()
    failing, other = controller.pairings.values()

    # e.g. close() re-raises the error the reconnect loop ended with
    with patch.object(
        failing, "shutdown", AsyncMock(side_effect=AuthenticationError("step 4"))
    ):
        await controller.stop()

        failing.shutdown.assert_awaited_once()
    assert other._shutdown


async def test_stop_cancels_the_browser_it_created(mock_asynczeroconf: AsyncZeroconf):
    mock_asynczeroconf.zeroconf.listeners = []  # nobody browses _hap._tcp yet
    controller = await make_controller(mock_asynczeroconf)

    with patch(
        "aiohomekit.controller.zeroconf.controller.AsyncServiceBrowser"
    ) as browser_class:
        browser = browser_class.return_value
        browser.async_cancel = AsyncMock()
        await controller.start()
        await controller.stop()

    browser.async_cancel.assert_awaited_once()


async def test_stop_keeps_a_browser_it_shares(
    mock_asynczeroconf: AsyncZeroconf, shared_browser: AsyncServiceBrowserStub
):
    controller = await make_controller(mock_asynczeroconf)

    await controller.start()
    assert shared_browser._handlers  # listens on it instead of creating its own
    await controller.stop()

    assert mock_asynczeroconf.zeroconf.listeners == [shared_browser]
    assert shared_browser._handlers == []

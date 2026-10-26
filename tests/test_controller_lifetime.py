import asyncio
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncZeroconf

from aiohomekit.controller.relay import Controller, controller as relay_controller
from aiohomekit.controller.zeroconf.controller import ZeroconfController
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
    HAP_TYPE_TCP,
    AsyncServiceBrowserStub,
    MockedAsyncServiceInfo,
    get_mock_service_info,
    install_mock_service_info,
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
        if getattr(task.get_coro(), "__qualname__", "").startswith(
            "HomeKitConnection._reconnect"
        )
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


def announce(
    zeroconf: AsyncZeroconf, browser: AsyncServiceBrowserStub, name: str
):
    """A live zeroconf answer: the browser tells its handlers the service was added."""
    for handler in list(browser._handlers):
        handler(
            zeroconf=zeroconf.zeroconf,
            service_type=HAP_TYPE_TCP,
            name=name,
            state_change=ServiceStateChange.Added,
        )


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


async def test_start_loads_a_pairing_whose_cache_fails_to_read(
    mock_asynczeroconf: AsyncZeroconf,
):
    controller = await make_controller(
        mock_asynczeroconf, (offline_pairing_data(), cached_state())
    )
    error = RuntimeError("database is locked")

    with patch.object(controller.char_cache_storage, "get", side_effect=error):
        await controller.start()

    pairing = controller.pairings[ACCESSORY_ID]
    with pytest.raises(AssertionError, match="not populated"):
        assert pairing.accessories  # fetched on demand
    await controller.stop()


async def test_reloading_a_pairing_shuts_the_replaced_one_down(
    mock_asynczeroconf: AsyncZeroconf,
):
    controller = await make_controller(
        mock_asynczeroconf, (offline_pairing_data(), cached_state())
    )
    await controller.start()
    old = controller.pairings[ACCESSORY_ID]
    old.connection._start_connector()  # e.g. a re-paired accessory: the old keys keep trying

    new = await controller.load_pairing(offline_pairing_data())

    assert controller.pairings[ACCESSORY_ID] is new is not old
    assert old._shutdown
    assert not reconnect_loops()
    await controller.stop()


async def test_load_pairing_applies_a_known_discovery(
    mock_asynczeroconf: AsyncZeroconf,
):
    controller = await make_controller(mock_asynczeroconf)
    await controller.start()
    # Discoveries are keyed lower-case; HAP pairing ids are usually upper-case
    description = replace(
        ZeroconfDiscoveryInfo.from_service_info(get_mock_service_info()),
        id="aa:bb:cc:00:00:02",
    )
    controller.discoveries[description.id] = controller._make_discovery(description)

    pairing = await controller.load_pairing(offline_pairing_data("AA:BB:CC:00:00:02"))

    assert pairing and pairing.description == description
    await controller.stop()


async def test_discovery_repopulates_a_pairing_without_cache():
    pairing = IpPairing(offline_pairing_data())
    description = ZeroconfDiscoveryInfo.from_service_info(get_mock_service_info())

    with patch.object(pairing, "_process_config_changed", AsyncMock()) as repopulate:
        pairing.process_description_update(description)
        await asyncio.sleep(0)

    repopulate.assert_awaited_once_with(description.config_num)
    await pairing.close()


async def test_live_discovery_reaches_the_pairing(
    mock_asynczeroconf: AsyncZeroconf, shared_browser: AsyncServiceBrowserStub
):
    controller = await make_controller(
        mock_asynczeroconf, (offline_pairing_data(), cached_state())
    )
    await controller.start()  # nothing cached yet, as right after the zeroconf starts

    info = get_mock_service_info()
    with install_mock_service_info(mock_asynczeroconf, info):
        announce(mock_asynczeroconf, shared_browser, info.name)
        await asyncio.sleep(0.6)  # resolved 0.5 s later

    assert ACCESSORY_ID in controller.discoveries
    assert controller.pairings[ACCESSORY_ID].description  # it connects on discovery
    await controller.stop()


async def test_restarted_controller_sees_live_discoveries(
    mock_asynczeroconf: AsyncZeroconf, shared_browser: AsyncServiceBrowserStub
):
    controller = await make_controller(mock_asynczeroconf)
    await controller.start()
    await controller.stop()
    await controller.start()

    info = get_mock_service_info()
    with install_mock_service_info(mock_asynczeroconf, info):
        announce(mock_asynczeroconf, shared_browser, info.name)
        await asyncio.sleep(0.6)

    assert ACCESSORY_ID in controller.discoveries
    await controller.stop()


async def test_stop_ignores_a_discovery_still_resolving(
    mock_asynczeroconf: AsyncZeroconf, shared_browser: AsyncServiceBrowserStub
):
    controller = await make_controller(
        mock_asynczeroconf, (offline_pairing_data(), cached_state())
    )
    discovered = MagicMock()
    controller.on_discovery(discovered)
    await controller.start()
    pairing = controller.pairings[ACCESSORY_ID]
    info = get_mock_service_info()
    answered = asyncio.Event()

    async def answer_late(
        self: MockedAsyncServiceInfo, zc: Zeroconf, timeout: float
    ) -> bool:
        await answered.wait()
        return self.load_from_cache(zc)

    async def answer_during_shutdown():
        answered.set()
        await asyncio.sleep(0.1)

    with patch.object(MockedAsyncServiceInfo, "async_request", answer_late):
        # Nothing cached: the controller asks the accessory, which answers while stop() runs
        announce(mock_asynczeroconf, shared_browser, info.name)
        await asyncio.sleep(0.6)
        with (
            install_mock_service_info(mock_asynczeroconf, info),
            patch.object(pairing, "shutdown", answer_during_shutdown),
        ):
            await controller.stop()
        await asyncio.sleep(0.1)

    assert controller.discoveries == {}
    discovered.assert_not_called()


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

    # e.g. closing the session fails
    with patch.object(
        failing, "shutdown", AsyncMock(side_effect=AuthenticationError("step 4"))
    ):
        await controller.stop()

        failing.shutdown.assert_awaited_once()
    assert other._shutdown


async def test_stop_closes_the_socket_of_a_rejected_pairing(
    mock_asynczeroconf: AsyncZeroconf,
):
    controller = await make_controller(
        mock_asynczeroconf, (offline_pairing_data(), cached_state())
    )
    await controller.start()
    connection = controller.pairings[ACCESSORY_ID].connection

    async def rejected():
        raise AuthenticationError("step 4")

    # The last reconnect loop was rejected at pair-verify; the accessory kept the socket open
    connection._connector = asyncio.ensure_future(rejected())
    await asyncio.sleep(0)
    transport = connection.transport = MagicMock()
    connection.protocol = MagicMock()

    await controller.stop()

    transport.close.assert_called_once()
    assert connection.transport is None


async def test_relay_stop_shuts_each_pairing_down_once(
    mock_asynczeroconf: AsyncZeroconf, shared_browser: AsyncServiceBrowserStub
):
    pairing_data_storage = PairingDataStorageMemory()
    await pairing_data_storage.save(ACCESSORY_ID, offline_pairing_data())
    controller = Controller(
        CharacteristicsStorageMemory(),
        pairing_data_storage,
        zeroconf_instance=mock_asynczeroconf,
    )
    with (
        patch.object(relay_controller, "COAP_TRANSPORT_SUPPORTED", False),
        patch.object(relay_controller, "BLE_TRANSPORT_SUPPORTED", False),
    ):
        await controller.start()
    pairing = controller.pairings[ACCESSORY_ID]

    with patch.object(pairing, "shutdown", AsyncMock()) as shutdown:
        await controller.stop()

    shutdown.assert_awaited_once()


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


async def test_failed_start_leaves_nothing_running(
    mock_asynczeroconf: AsyncZeroconf, shared_browser: AsyncServiceBrowserStub
):
    # The stored accessory is advertised, so its discovery starts a reconnect loop before start fails
    controller = await make_controller(
        mock_asynczeroconf, (offline_pairing_data(), cached_state())
    )
    load_from_cache = ZeroconfController._load_zeroconf_from_cache

    async def load_then_fail(self: ZeroconfController, zc: Zeroconf | None = None):
        await load_from_cache(self, zc)
        assert reconnect_loops()
        raise RuntimeError("zeroconf failed")

    with (
        install_mock_service_info(mock_asynczeroconf, get_mock_service_info()),
        patch.object(ZeroconfController, "_load_zeroconf_from_cache", load_then_fail),
        pytest.raises(RuntimeError),
    ):
        await controller.start()

    assert shared_browser._handlers == []
    assert not reconnect_loops()
    assert controller.pairings == {}


async def test_failed_relay_start_stops_the_transports_it_started(
    mock_asynczeroconf: AsyncZeroconf, shared_browser: AsyncServiceBrowserStub
):
    scanner = AsyncMock(register_detection_callback=MagicMock())
    scanner.start.side_effect = RuntimeError("bluetooth failed")
    controller = Controller(
        CharacteristicsStorageMemory(),
        PairingDataStorageMemory(),
        zeroconf_instance=mock_asynczeroconf,
        bleak_scanner_instance=scanner,
    )

    with (
        patch.object(relay_controller, "IP_TRANSPORT_SUPPORTED", True),
        patch.object(relay_controller, "COAP_TRANSPORT_SUPPORTED", False),
        patch.object(relay_controller, "BLE_TRANSPORT_SUPPORTED", False),
        pytest.raises(RuntimeError),
    ):
        await controller.start()

    assert shared_browser._handlers == []

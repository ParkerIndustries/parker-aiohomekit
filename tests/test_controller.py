from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiohomekit.controller.ble.controller import BleController
from aiohomekit.controller.relay import Controller, controller as controller_module
from aiohomekit.controller.zeroconf.ip.controller import IpController
from aiohomekit.exceptions import AccessoryDisconnectedError, UnknownError
from aiohomekit.model.transport_type import TransportType
from aiohomekit.storage.characteristics_storage import CharacteristicsStorageMemory
from aiohomekit.storage.pairing_data_storage import PairingDataStorageMemory


async def test_remove_pairing(controller_and_paired_accessory):
    pairing_id = next(iter(controller_and_paired_accessory.pairings.keys()))
    pairing = controller_and_paired_accessory.pairings[pairing_id]

    # Verify that there is a pairing connected and working
    await pairing.get_characteristics([(1, 9)])

    # Remove pairing from controller
    await controller_and_paired_accessory.remove_pairing(pairing_id)

    # Verify now gives an appropriate error
    with pytest.raises(AccessoryDisconnectedError):
        await pairing.get_characteristics([(1, 9)])


async def test_remove_pairing_failure_still_shuts_down(
    controller_and_paired_accessory,
):
    controller = controller_and_paired_accessory
    pairing_id = next(iter(controller.pairings.keys()))
    pairing = controller.pairings[pairing_id]
    ip_controller = controller._transports[TransportType.IP]

    await pairing.get_characteristics([(1, 9)])
    assert pairing.connection.is_connected

    with (
        patch.object(pairing, "remove_pairing", side_effect=UnknownError("boom")),
        pytest.raises(UnknownError),
    ):
        await controller.remove_pairing(pairing_id)

    assert pairing._shutdown
    assert not pairing.connection.is_connected
    assert await ip_controller.pairing_data_storage.get(pairing_id) is None


async def test_endpoint_change_after_shutdown_does_not_reconnect(
    controller_and_paired_accessory,
):
    pairing = next(iter(controller_and_paired_accessory.pairings.values()))
    await pairing.shutdown()

    with patch.object(pairing.connection, "reconnect_soon") as reconnect_soon:
        pairing._endpoint_changed()

    reconnect_soon.assert_not_called()


async def test_passing_in_bleak_to_controller():
    """Test we can pass in a bleak scanner instance to the controller.

    Passing in the instance should enable BLE scanning.
    """
    with (
        patch.object(controller_module, "BLE_TRANSPORT_SUPPORTED", False),
        patch.object(controller_module, "COAP_TRANSPORT_SUPPORTED", False),
        patch.object(controller_module, "IP_TRANSPORT_SUPPORTED", False),
    ):
        controller = Controller(
            char_cache=CharacteristicsStorageMemory(),
            pairing_data_storage=PairingDataStorageMemory(),
            bleak_scanner_instance=AsyncMock(register_detection_callback=MagicMock()),
        )
        await controller.start()

    assert len(controller._transports) == 1, controller._transports
    assert isinstance(controller._transports[TransportType.BLE], BleController)


async def test_passing_in_async_zeroconf(mock_asynczeroconf):
    """Test we can pass in a zeroconf ServiceBrowser instance to the controller.

    Passing in the instance should enable zeroconf scanning.
    """
    with (
        patch.object(controller_module, "BLE_TRANSPORT_SUPPORTED", False),
        patch.object(controller_module, "COAP_TRANSPORT_SUPPORTED", False),
        patch.object(controller_module, "IP_TRANSPORT_SUPPORTED", False),
    ):
        controller = Controller(
            CharacteristicsStorageMemory(),
            PairingDataStorageMemory(),
            zeroconf_instance=mock_asynczeroconf,
        )
        await controller.start()

    assert len(controller._transports) == 1, controller._transports
    assert isinstance(controller._transports[TransportType.IP], IpController)


async def test_controller_on_discovery_callback_before_start():
    with (
        patch.object(controller_module, "BLE_TRANSPORT_SUPPORTED", False),
        patch.object(controller_module, "COAP_TRANSPORT_SUPPORTED", False),
        patch.object(controller_module, "IP_TRANSPORT_SUPPORTED", True),
    ):
        controller = Controller(
            CharacteristicsStorageMemory(),
            PairingDataStorageMemory(),
        )
        callback_mock = AsyncMock()
        controller.on_discovery(callback_mock)
        await controller.start()

    assert controller._transports
    child_controller = controller._transports[TransportType.IP]
    assert child_controller._on_discovery_callback
    child_controller._on_discovery_callback(child_controller, None)
    callback_mock.assert_called_once_with(child_controller, None)


async def test_controller_on_discovery_callback_after_start():
    with (
        patch.object(controller_module, "BLE_TRANSPORT_SUPPORTED", False),
        patch.object(controller_module, "COAP_TRANSPORT_SUPPORTED", False),
        patch.object(controller_module, "IP_TRANSPORT_SUPPORTED", True),
    ):
        controller = Controller(
            CharacteristicsStorageMemory(),
            PairingDataStorageMemory(),
        )
        callback_mock = AsyncMock()
        await controller.start()
        controller.on_discovery(callback_mock)

    assert controller._transports
    child_controller = controller._transports[TransportType.IP]
    assert child_controller._on_discovery_callback
    child_controller._on_discovery_callback(child_controller, None)
    callback_mock.assert_called_once_with(child_controller, None)


async def test_identify_by_an_upper_case_id(controller_and_paired_accessory):
    controller = controller_and_paired_accessory
    # Pairings are keyed lower-case; the fixture's AccessoryPairingID is upper-case
    pairing = controller.pairings["12:34:56:00:01:0a"]

    with patch.object(pairing, "identify") as identify:
        await controller.identify("12:34:56:00:01:0A")

    identify.assert_awaited_once()


async def test_remove_pairing_by_an_upper_case_id(controller_and_paired_accessory):
    controller = controller_and_paired_accessory
    pairing = controller.pairings["12:34:56:00:01:0a"]
    await pairing.get_characteristics([(1, 9)])

    await controller.remove_pairing("12:34:56:00:01:0A")

    assert controller.pairings == {}
    with pytest.raises(AccessoryDisconnectedError):
        await pairing.get_characteristics([(1, 9)])

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiohomekit.controller.ble.controller import BleController
from aiohomekit.controller.relay import Controller, controller as controller_module
from aiohomekit.controller.zeroconf.ip.controller import IpController
from aiohomekit.exceptions import AccessoryDisconnectedError
from aiohomekit.model.transport_type import TransportType
from aiohomekit.storage.characteristics_storage import CharacteristicsStorageMemory
from aiohomekit.storage.pairing_data_storage import PairingDataStorageMemory


async def test_remove_pairing(controller_and_paired_accessory):
    pairing_id = next(iter(controller_and_paired_accessory.pairings.keys()))  # TODO: check
    pairing = controller_and_paired_accessory.pairings[pairing_id]

    # Verify that there is a pairing connected and working
    await pairing.get_characteristics([(1, 9)])

    # Remove pairing from controller
    await controller_and_paired_accessory.remove_pairing(pairing_id)

    # Verify now gives an appropriate error
    with pytest.raises(AccessoryDisconnectedError):
        await pairing.get_characteristics([(1, 9)])


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
            bleak_scanner_instance=AsyncMock(register_detection_callback=MagicMock())
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
        controller = Controller(CharacteristicsStorageMemory(), PairingDataStorageMemory(), zeroconf_instance=mock_asynczeroconf)
        await controller.start()

    assert len(controller._transports) == 1, controller._transports
    assert isinstance(controller._transports[TransportType.IP], IpController)

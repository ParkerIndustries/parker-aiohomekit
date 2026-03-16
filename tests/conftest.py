import asyncio
import logging
import os
import pathlib
import tempfile
import threading
from unittest import mock

import pytest

from aiohomekit.controller.relay import Controller
from aiohomekit.controller.zeroconf.ip import IpPairing
from aiohomekit.model.accessories import Accessory
from aiohomekit.model.characteristics import CharacteristicsTypes
from aiohomekit.model.services import ServicesTypes
from aiohomekit.storage.characteristics_storage import CharacteristicsStorageMemory
from aiohomekit.storage.pairing_data_storage import (
    PairingDataStorageFile,
    PairingDataStorageMemory,
)
from aiohomekit.testing.accessoryserver import AccessoryServer
from aiohomekit.testing.mock_zeroconf import mock_asynczeroconf as do_mock_asynczeroconf
from aiohomekit.testing.utils import next_available_port, wait_for_server_online


@pytest.fixture
def mock_asynczeroconf():
    with do_mock_asynczeroconf() as zeroconf:
        yield zeroconf


@pytest.fixture
async def controller_and_unpaired_accessory(mock_asynczeroconf, id_factory):
    available_port = next_available_port()

    config_file = tempfile.NamedTemporaryFile(delete=False)
    config_file.write(b"""{
        "accessory_ltpk": "7986cf939de8986f428744e36ed72d86189bea46b4dcdc8d9d79a3e4fceb92b9",
        "accessory_ltsk": "3d99f3e959a1f93af4056966f858074b2a1fdec1c5fd84a51ea96f9fa004156a",
        "accessory_pairing_id": "12:34:56:00:01:0A",
        "accessory_pin": "031-45-154",
        "c#": 1,
        "category": "Lightbulb",
        "host_ip": "127.0.0.1",
        "host_port": %port%,
        "name": "unittestLight",
        "unsuccessful_tries": 0
    }""".replace(b"%port%", str(available_port).encode("utf-8")))
    config_file.close()

    httpd = AccessoryServer(config_file.name, None)
    accessory = Accessory.create_with_info(
        id_factory(), "Testlicht", "lusiardi.de", "Demoserver", "0001", "0.1"
    )
    lightBulbService = accessory.add_service(ServicesTypes.LIGHTBULB)
    lightBulbService.add_char(CharacteristicsTypes.ON, value=False)
    httpd.add_accessory(accessory)

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    await wait_for_server_online(available_port)

    controller = Controller(
        char_cache=CharacteristicsStorageMemory(),
        pairing_data_storage=PairingDataStorageMemory(),
        zeroconf_instance=mock_asynczeroconf,
    )

    with mock.patch("aiohomekit.__main__.Controller") as c:
        c.return_value = controller
        yield controller, available_port

    os.unlink(config_file.name)

    httpd.shutdown()


@pytest.fixture
async def controller_and_paired_accessory(mock_asynczeroconf, id_factory):
    available_port = next_available_port()

    config_file = tempfile.NamedTemporaryFile(delete=False)
    data = b"""{
        "accessory_ltpk": "7986cf939de8986f428744e36ed72d86189bea46b4dcdc8d9d79a3e4fceb92b9",
        "accessory_ltsk": "3d99f3e959a1f93af4056966f858074b2a1fdec1c5fd84a51ea96f9fa004156a",
        "accessory_pairing_id": "12:34:56:00:01:0A",
        "accessory_pin": "031-45-154",
        "c#": 1,
        "category": "Lightbulb",
        "host_ip": "127.0.0.1",
        "host_port": %port%,
        "name": "unittestLight",
        "peers": {
            "decc6fa3-de3e-41c9-adba-ef7409821bfc": {
                "admin": true,
                "key": "d708df2fbf4a8779669f0ccd43f4962d6d49e4274f88b1292f822edc3bcf8ed8"
            }
        },
        "unsuccessful_tries": 0
    }""".replace(b"%port%", str(available_port).encode("utf-8"))

    config_file.write(data)
    config_file.close()

    httpd = AccessoryServer(config_file.name, None)
    accessory = Accessory.create_with_info(
        id_factory(), "Testlicht", "lusiardi.de", "Demoserver", "0001", "0.1"
    )
    lightBulbService = accessory.add_service(ServicesTypes.LIGHTBULB)
    lightBulbService.add_char(CharacteristicsTypes.ON, value=False)
    httpd.add_accessory(accessory)

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    await wait_for_server_online(available_port)

    controller_file = tempfile.NamedTemporaryFile(delete=False)
    controller_file.write(b"""{
        "alias": {
            "Connection": "IP",
            "iOSDeviceLTPK": "d708df2fbf4a8779669f0ccd43f4962d6d49e4274f88b1292f822edc3bcf8ed8",
            "iOSDeviceId": "decc6fa3-de3e-41c9-adba-ef7409821bfc",
            "AccessoryLTPK": "7986cf939de8986f428744e36ed72d86189bea46b4dcdc8d9d79a3e4fceb92b9",
            "AccessoryPairingID": "12:34:56:00:01:0A",
            "AccessoryPort": %port%,
            "AccessoryAddress": "127.0.0.1",
            "iOSDeviceLTSK": "fa45f082ef87efc6c8c8d043d74084a3ea923a2253e323a7eb9917b4090c2fcc"
        }
    }""".replace(b"%port%", str(available_port).encode("utf-8")))
    controller_file.close()

    controller = Controller(
        char_cache=CharacteristicsStorageMemory(),
        pairing_data_storage=PairingDataStorageFile(pathlib.Path(controller_file.name)),
        zeroconf_instance=mock_asynczeroconf,
    )

    async with controller:
        config_file.close()

        import aiohomekit.__main__ as main_module

        main_module.aliases["alias"] = next(iter(controller.pairings.keys()))

        with mock.patch("aiohomekit.__main__.Controller") as c:
            c.return_value = controller
            yield controller

    os.unlink(config_file.name)
    os.unlink(controller_file.name)

    httpd.shutdown()


@pytest.fixture
async def pairing(controller_and_paired_accessory):
    pairing = next(iter(controller_and_paired_accessory.pairings.values()))
    yield pairing
    # try:
    await pairing.close()
    # except asyncio.CancelledError:
    #     pass


@pytest.fixture
async def pairings(controller_and_paired_accessory):
    """Returns a pairing of pairngs."""
    left = next(iter(controller_and_paired_accessory.pairings.values()))

    right = IpPairing(left.pairing_data)

    yield (left, right)

    try:
        await asyncio.shield(right.close())
    except asyncio.CancelledError:
        pass


@pytest.fixture(autouse=True)
def configure_test_logging(caplog):
    caplog.set_level(logging.DEBUG)


@pytest.fixture()
def id_factory():
    id_counter = 0

    def _get_id():
        nonlocal id_counter
        id_counter += 1
        return id_counter

    yield _get_id

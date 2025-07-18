import asyncio
from collections.abc import Iterable
import contextlib
import errno
import logging
import os
import pathlib
import socket
import tempfile
import threading
from typing import Optional
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zeroconf import DNSCache, DNSQuestionType, SignalRegistrationInterface, Zeroconf
from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

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

HAP_TYPE_TCP = "_hap._tcp.local."
HAP_TYPE_UDP = "_hap._udp.local."
TYPE_PTR = 12
CLASS_IN = 1


def _get_test_socket() -> socket.socket:
    """Create a socket to test binding ports."""
    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    test_socket.setblocking(False)
    test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return test_socket


def port_ready(port: int) -> bool:
    try:
        _get_test_socket().bind(("127.0.0.1", port))
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            return True

    return False


def next_available_port() -> int:
    for port in range(51842, 53842):
        if not port_ready(port):
            return port

    raise RuntimeError("No available ports")


async def wait_for_server_online(port: int):
    for i in range(100):
        if port_ready(port):
            break
        await asyncio.sleep(0.025)


class AsyncServiceBrowserStub:
    types = [
        "_hap._tcp.local.",
        "_hap._udp.local.",
    ]

    def __init__(self):
        self._handlers = []
        self.service_state_changed = SignalRegistrationInterface(self._handlers)


class MockedAsyncServiceInfo(AsyncServiceInfo):
    async def async_request(
        self,
        zc: "Zeroconf",
        timeout: float,
        question_type: Optional[DNSQuestionType] = None,
        addr: Optional[str] = None,
        port: Optional[int] = None,
    ) -> bool:
        success = self.load_from_cache(zc)
        assert (
            success
        ), f"Failed to load service info from cache {self.type=}, {self.name=}"
        return success


def _get_mock_service_info():
    desc = {
        b"c#": b"1",
        b"id": b"00:00:01:00:00:02",
        b"md": b"unittest",
        b"s#": b"1",
        b"ci": b"5",
        b"sf": b"0",
    }
    return MockedAsyncServiceInfo(
        HAP_TYPE_TCP,
        f"foo.{HAP_TYPE_TCP}",
        addresses=[socket.inet_aton("127.0.0.1")],
        port=1234,
        properties=desc,
        weight=0,
        priority=0,
    )


@contextlib.contextmanager
def _install_mock_service_info(
    mock_asynczeroconf: AsyncZeroconf, info: MockedAsyncServiceInfo
) -> Iterable:
    zeroconf: Zeroconf = mock_asynczeroconf.zeroconf

    zeroconf.cache.async_add_records(
        [*info.dns_addresses(), info.dns_pointer(), info.dns_service(), info.dns_text()]
    )

    assert (
        zeroconf.cache.get_all_by_details(HAP_TYPE_TCP, TYPE_PTR, CLASS_IN) is not None
    )

    yield


@pytest.fixture
def mock_asynczeroconf():
    """Mock zeroconf."""

    with (
        patch("zeroconf.asyncio.AsyncServiceBrowser", AsyncServiceBrowserStub),
        patch("zeroconf.asyncio.AsyncZeroconf") as mock_zc,
        patch(
            "aiohomekit.controller.zeroconf.controller.AsyncServiceInfo",
            MockedAsyncServiceInfo,
        ),
    ):  # patch where it’s used, not where it’s from, because the class is already imported in the module
        zc = mock_zc.return_value
        zc.register_service = AsyncMock()
        zc.async_close = AsyncMock()
        zeroconf = MagicMock(name="zeroconf_mock")
        zeroconf.cache = DNSCache()
        zeroconf.async_wait_for_start = AsyncMock()
        zeroconf.listeners = [AsyncServiceBrowserStub()]
        zc.zeroconf = zeroconf
        # with _install_mock_service_info(
        #     zc, _get_mock_service_info()
        # ):
        yield zc


@pytest.fixture
async def controller_and_unpaired_accessory(request, mock_asynczeroconf, id_factory):
    available_port = next_available_port()

    config_file = tempfile.NamedTemporaryFile(delete=False)
    config_file.write(
        b"""{
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
    }""".replace(
            b"%port%", str(available_port).encode("utf-8")
        )
    )
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

    # httpd.shutdown()
    # t.join()

    def _shutdown():
        httpd.shutdown()
        t.join()

    loop = asyncio.get_running_loop()
    asyncio.ensure_future(loop.run_in_executor(None, _shutdown))


@pytest.fixture
async def controller_and_paired_accessory(request, mock_asynczeroconf, id_factory):
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
    }""".replace(
        b"%port%", str(available_port).encode("utf-8")
    )

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
    controller_file.write(
        b"""{
        "alias": {
            "Connection": "IP",
            "iOSDeviceLTPK": "d708df2fbf4a8779669f0ccd43f4962d6d49e4274f88b1292f822edc3bcf8ed8",
            "iOSDeviceId": "decc6fa3-de3e-41c9-adba-ef7409821bfc",
            "AccessoryLTPK": "7986cf939de8986f428744e36ed72d86189bea46b4dcdc8d9d79a3e4fceb92b9",
            "AccessoryPairingID": "12:34:56:00:01:0A",
            "AccessoryPort": %port%,
            "AccessoryIP": "127.0.0.1",
            "iOSDeviceLTSK": "fa45f082ef87efc6c8c8d043d74084a3ea923a2253e323a7eb9917b4090c2fcc"
        }
    }""".replace(
            b"%port%", str(available_port).encode("utf-8")
        )
    )
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

    def _shutdown():
        httpd.shutdown()
        t.join()

    loop = asyncio.get_running_loop()
    asyncio.ensure_future(loop.run_in_executor(None, _shutdown))


@pytest.fixture
async def pairing(controller_and_paired_accessory):
    pairing = next(
        iter(controller_and_paired_accessory.pairings.values())
    )  # TODO: check
    yield pairing
    # try:
    await pairing.close()
    # except asyncio.CancelledError:
    #     pass


@pytest.fixture
async def pairings(request, controller_and_paired_accessory):
    """Returns a pairing of pairngs."""
    left = next(iter(controller_and_paired_accessory.pairings.values()))  # TODO: check

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

from collections.abc import Iterable
import contextlib
from contextlib import contextmanager
import socket
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from zeroconf import DNSCache, DNSQuestionType, SignalRegistrationInterface, Zeroconf
from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

HAP_TYPE_TCP = "_hap._tcp.local."
HAP_TYPE_UDP = "_hap._udp.local."
TYPE_PTR = 12
CLASS_IN = 1


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


def get_mock_service_info():
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
def install_mock_service_info(
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


@contextmanager
def mock_asynczeroconf():
    with (
        patch("zeroconf.asyncio.AsyncServiceBrowser", AsyncServiceBrowserStub),
        patch("zeroconf.asyncio.AsyncZeroconf") as mock_zc,
        patch(
            "aiohomekit.controller.zeroconf.controller.AsyncServiceInfo",
            MockedAsyncServiceInfo,
        ),
    ):
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

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Coroutine
from enum import Enum, auto
from typing import Any, cast, override

from zeroconf import (
    BadTypeInNameException,
    ServiceStateChange,
    Zeroconf,
    current_time_millis,
)
from zeroconf._dns import DNSPointer
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from aiohomekit.controller.abstract import (
    AbstractController,
    AbstractDiscovery,
    AbstractPairing,
)
from aiohomekit.exceptions import AccessoryNotFoundError
from aiohomekit.model.typed_dicts import HKDeviceID
from aiohomekit.storage.characteristics_storage import CharacteristicsStorageProtocol
from aiohomekit.storage.pairing_data_storage import PairingDataStorageProtocol
from aiohomekit.utils import async_create_task

from .protocol import _TIMEOUT_MS, CLASS_IN, TYPE_PTR, ZeroconfDiscoveryInfo, logger


class IpTransport(str, Enum):
    TCP = auto()
    UDP = auto()


class ZeroconfController[Discovery: AbstractDiscovery, Pairing: AbstractPairing](
    AbstractController[ZeroconfDiscoveryInfo, Discovery, Pairing], ABC
):
    """
    Base class for HAP protocols that rely on Zeroconf discovery.
    """

    @property
    @abstractmethod
    def _hap_type(self) -> str: ...

    def __init__(
        self,
        Discovery: type[Discovery],
        Pairing: type[Pairing],
        char_cache_storage: CharacteristicsStorageProtocol,
        pairing_data_storage: PairingDataStorageProtocol,
        zeroconf_instance: AsyncZeroconf,
    ):
        super().__init__(Discovery, Pairing, char_cache_storage, pairing_data_storage)
        self._async_zeroconf_instance = zeroconf_instance
        self._waiters: dict[str, list[asyncio.Future]] = {}
        self._resolve_later_queue: dict[str, asyncio.TimerHandle] = {}
        self._loop = asyncio.get_running_loop()
        self._running = True

    @override
    async def start(self):
        await super().start()
        zc = self._async_zeroconf_instance.zeroconf

        if browser := self._find_broswer_for_hap_type(self._hap_type):
            self._browser = browser
            self._browser.service_state_changed.register_handler(
                self._zeroconf_did_discover_service
            )
        else:
            self._browser = AsyncServiceBrowser(
                self._async_zeroconf_instance.zeroconf,
                [
                    self._hap_type,
                ],
                handlers=[self._zeroconf_did_discover_service],
            )

        await self._load_zeroconf_from_cache(zc)

    @override
    async def stop(self):
        await super().stop()
        self._running = False
        self._browser.service_state_changed.unregister_handler(
            self._zeroconf_did_discover_service
        )
        while self._resolve_later_queue:
            _, cancel = self._resolve_later_queue.popitem()
            cancel.cancel()

    @override
    async def find(
        self, device_id: HKDeviceID, timeout_sec: float = 10.0
    ) -> Discovery | None:
        device_id = device_id.lower()

        if discovery := self._discoveries.get(device_id):
            return discovery

        waiters = self._waiters.setdefault(device_id, [])
        waiter = self._loop.create_future()
        waiters.append(waiter)
        cancel_timeout = self._loop.call_later(
            timeout_sec, self._on_timeout, waiter
        )  # NOTE: asyncio.wait_for might be a better choice here

        try:
            if discovery := await waiter:
                return discovery
        except asyncio.TimeoutError:
            raise AccessoryNotFoundError(
                f"Accessory with device id {device_id} not found"
            )
        finally:
            cancel_timeout.cancel()

    @override
    async def is_reachable(
        self, device_id: HKDeviceID, timeout_sec: float = 10.0
    ) -> bool:
        """Check if a device is reachable.

        This method will return True if the device is reachable, False if it is not.

        Typically A/AAAA records have a TTL of 120 seconds which means we may
        see the device as reachable for up to 120 seconds after it has been
        removed from the network if it does not send a goodbye packet.
        """
        try:
            discovery = await self.find(device_id, timeout_sec)
        except AccessoryNotFoundError:
            return False

        if not discovery:
            return False

        alias = f"{discovery.description.name}.{self._hap_type}"
        info = AsyncServiceInfo(self._hap_type, alias)
        zc = self._async_zeroconf_instance.zeroconf
        return info.load_from_cache(zc) or await info.async_request(zc, _TIMEOUT_MS)

    async def discover(self, timeout_sec: float = 10) -> AsyncIterable[Discovery]:
        for device in self._discoveries.values():
            yield device

    # Private methods

    async def _load_zeroconf_from_cache(self, zc: Zeroconf | None = None):
        zc = zc or self._async_zeroconf_instance.zeroconf
        tasks: list[Coroutine[Any, Any, None]] = []
        now = current_time_millis()
        for record in self._get_ptr_records(zc):
            try:
                info = AsyncServiceInfo(
                    self._hap_type, record.alias
                )  # record.name was used before, restore in case of issues
                # In ptr, `name` is the same as `type` (e.g. _hap._tcp.local.), and `alias` is the fully qualified name (e.g. foo._hap._tcp.local.)
            except BadTypeInNameException as ex:
                logger.debug(
                    "Ignoring record with bad type in name: %s: %s", record.name, ex
                )
                continue
            if info.load_from_cache(zc, now):
                self._handle_loaded_discovery_info(info)
            else:
                tasks.append(self._handle_discovery_service(info))

        if tasks:
            await asyncio.gather(*tasks)

    def _get_ptr_records(self, zc: Zeroconf) -> list[DNSPointer]:
        """Return all PTR records for the HAP type."""
        return cast(
            list[DNSPointer],
            zc.cache.get_all_by_details(self._hap_type, TYPE_PTR, CLASS_IN),
        )

    def _zeroconf_did_discover_service(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ):
        if service_type != self._hap_type:
            return

        if state_change == ServiceStateChange.Removed:
            if cancel := self._resolve_later_queue.pop(name, None):
                cancel.cancel()
            return

        if name in self._resolve_later_queue:
            # We already have a timer to resolve this service, so ignore this
            # callback.
            return

        try:
            info = AsyncServiceInfo(service_type, name)
        except BadTypeInNameException as ex:
            logger.debug("Ignoring record with bad type in name: %s: %s", name, ex)
            return

        self._resolve_later_queue[name] = self._loop.call_at(
            self._loop.time() + 0.5, self._do_resolve_later, name, info
        )

    async def _do_resolve_later(self, name: str, info: AsyncServiceInfo) -> None:
        """Resolve a host later."""
        # As soon as we get a callback, we can remove the _resolve_later
        # so the next time we get a callback, we can resolve the service
        # again if needed which ensures the TTL is respected.
        self._resolve_later_queue.pop(name, None)

        if not self._running:
            return

        if info.load_from_cache(self._async_zeroconf_instance.zeroconf):
            self._handle_loaded_discovery_info(info)
        else:
            async_create_task(self._handle_discovery_service(info))

    async def _handle_discovery_service(self, info: AsyncServiceInfo):
        """Handle a device that became visible via zeroconf."""
        # AsyncServiceInfo already tries 3x
        await info.async_request(self._async_zeroconf_instance.zeroconf, _TIMEOUT_MS)
        self._handle_loaded_discovery_info(info)

    def _handle_loaded_discovery_info(self, info: AsyncServiceInfo):
        """Process loaded or discovered service"""
        try:
            description = ZeroconfDiscoveryInfo.from_service_info(info)
        except ValueError as e:
            logger.debug("%s: Not a valid homekit device: %s", info.name, e)
            return

        if discovery := self._discoveries.get(description.id):
            discovery._update_from_discovery(description)
        else:
            discovery = self._discoveries[description.id] = self._make_discovery(
                description
            )

        discovery = self._discoveries[description.id] = self._make_discovery(
            description
        )

        if pairing := self.pairings.get(description.id):
            logger.debug(
                "%s: Notifying pairing of description update: %s",
                description.id,
                description,
            )
            pairing.process_description_update(description)

        if waiters := self._waiters.pop(description.id, None):
            for waiter in waiters:
                if not waiter.cancelled() and not waiter.done():
                    waiter.set_result(discovery)

        if callback := self._on_discovery_callback:
            callback(self, discovery)

    def _on_timeout(self, future: asyncio.Future):
        if not future.done():
            future.set_exception(asyncio.TimeoutError())

    # Helpers

    def _find_broswer_for_hap_type(self, hap_type: str) -> AsyncServiceBrowser | None:
        for browser in self._async_zeroconf_instance.zeroconf.listeners:
            if not isinstance(browser, AsyncServiceBrowser):
                continue
            if hap_type not in browser.types:
                continue
            return browser

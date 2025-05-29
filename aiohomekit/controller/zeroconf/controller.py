



class IpTransport(str, Enum):
    TCP = auto()
    UDP = auto()

class ZeroconfController[
    Discovery: AbstractDiscovery,
    Pairing: AbstractPairing
](
    AbstractController[Discovery, Pairing],
    ABC
):
    """
    Base class for HAP protocols that rely on Zeroconf discovery.
    """

    @abstracemthod
    @property
    def _hap_type(self) -> IpTransport: ...

    # TODO: annotate all attributes

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
        self._resolve_later: dict[str, asyncio.TimerHandle] = {}
        self._loop = asyncio.get_running_loop()
        self._running = True

    async def start(self):
        zc = self._async_zeroconf_instance.zeroconf
        if not zc:
            return self

        self._browser = self._find_broswer_for_hap_type(
            self._async_zeroconf_instance, self.hap_type
        )
        self._browser.service_state_changed.register_handler(self._zeroconf_did_discover_service)
        await self._load_zeroconf_from_cache(zc)

        return self

    async def stop(self):
        """Stop the controller."""
        self._running = False
        self._browser.service_state_changed.unregister_handler(self._zeroconf_did_discover_service)
        while self._resolve_later:
            _, cancel = self._resolve_later.popitem()
            cancel.cancel()

    async def find(self, device_id: str, timeout_sec: float = 10.0) -> Discovery:
        device_id = device_id.lower()

        if discovery := self._discoveries.get(device_id):
            return discovery

        waiters = self._waiters.setdefault(device_id, [])
        waiter = self._loop.create_future()
        waiters.append(waiter)
        cancel_timeout = self._loop.call_later(timeout, self._on_timeout, waiter)

        try:
            if discovery := await waiter:
                return discovery
        except asyncio.TimeoutError:
            raise AccessoryNotFoundError(
                f"Accessory with device id {device_id} not found"
            )
        finally:
            cancel_timeout.cancel()

    async def is_reachable(self, device_id: str, timeout: float = 10.0) -> bool:
        """Check if a device is reachable.

        This method will return True if the device is reachable, False if it is not.

        Typically A/AAAA records have a TTL of 120 seconds which means we may
        see the device as reachable for up to 120 seconds after it has been
        removed from the network if it does not send a goodbye packet.
        """
        try:
            discovery = await self.find(device_id, timeout)
        except AccessoryNotFoundError:
            return False
        alias = f"{discovery.description.name}.{self.hap_type}"
        info = AsyncServiceInfo(self.hap_type, alias)
        zc = self._async_zeroconf_instance.zeroconf
        return info.load_from_cache(zc) or await info.async_request(zc, _TIMEOUT_MS)

    async def discover(self) -> AsyncIterable[Discovery]:
        for device in self._discoveries.values():
            yield device

    # Private methods

    async def _load_zeroconf_from_cache(self, zc: Zeroconf):
        tasks: list[asyncio.Task] = []
        now = current_time_millis()
        for record in self._async_get_ptr_records(zc):
            try:
                info = AsyncServiceInfo(self.hap_type, record.alias)
            except BadTypeInNameException as ex:
                logger.debug(
                    "Ignoring record with bad type in name: %s: %s", record.alias, ex
                )
                continue
            if info.load_from_cache(zc, now):
                self._handle_loaded_discovery_info(info)
            else:
                tasks.append(self._handle_discovery_service(info))

        if tasks:
            await asyncio.gather(*tasks)

    def _async_get_ptr_records(self, zc: Zeroconf) -> list[DNSPointer]:
        """Return all PTR records for the HAP type."""
        return zc.cache.async_all_by_details(self.hap_type, TYPE_PTR, CLASS_IN)

    def _zeroconf_did_discover_service(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ):
        if service_type != self.hap_type:
            return

        if state_change == ServiceStateChange.Removed:
            if cancel := self._resolve_later.pop(name, None):
                cancel.cancel()
            return

        if name in self._resolve_later:
            # We already have a timer to resolve this service, so ignore this
            # callback.
            return

        try:
            info = AsyncServiceInfo(service_type, name)
        except BadTypeInNameException as ex:
            logger.debug("Ignoring record with bad type in name: %s: %s", name, ex)
            return

        self._resolve_later[name] = self._loop.call_at(
            self._loop.time() + 0.5, self._resolve_later, name, info
        )

    async def _handle_discovery_service(self, info: AsyncServiceInfo):
        """Handle a device that became visible via zeroconf."""
        # AsyncServiceInfo already tries 3x
        await info.async_request(self._async_zeroconf_instance.zeroconf, _TIMEOUT_MS)
        self._handle_loaded_discovery_info(info)

    def _handle_loaded_discovery_info(self, info: AsyncServiceInfo):
        """Process loaded or discovered service"""
        try:
            description = HomeKitService.from_service_info(info)
        except ValueError as e:
            logger.debug("%s: Not a valid homekit device: %s", info.name, e)
            return

        if discovery := self._discoveries.get(description.id):
            discovery._update_from_discovery(description)
        else:
            discovery = self._discoveries[description.id] = self._make_discovery(
                description
            )

        discovery = self._discoveries[description.id] = self._make_discovery(description)

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

    def _find_broswer_for_hap_type(self, azc: AsyncZeroconf, hap_type: str) -> AsyncServiceBrowser:
        for browser in azc.zeroconf.listeners:
            if not isinstance(browser, AsyncServiceBrowser):
                continue
            if hap_type not in browser.types:
                continue
            return browser

        raise TransportNotSupportedError(f"There is no zeroconf browser for {hap_type}")

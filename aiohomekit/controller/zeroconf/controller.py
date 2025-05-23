
class ZeroconfController(AbstractController, ABC):
    """
    Base class for HAP protocols that rely on Zeroconf discovery.
    """

    hap_type: str
    # TODO: annotate all attributes

    def __init__(
        self,
        char_cache: CharacteristicCacheType,
        zeroconf_instance: AsyncZeroconf,
    ):
        super().__init__(char_cache)
        self._async_zeroconf_instance = zeroconf_instance
        self._waiters: dict[str, list[asyncio.Future]] = {}
        self._resolve_later: dict[str, asyncio.TimerHandle] = {}
        self._loop = asyncio.get_running_loop()
        self._running = True

    async def async_start(self):
        zc = self._async_zeroconf_instance.zeroconf
        if not zc:
            return self

        self._browser = self._find_broswer_for_hap_type(
            self._async_zeroconf_instance, self.hap_type
        )
        self._browser.service_state_changed.register_handler(self._handle_service)
        await self._async_update_from_cache(zc)

        return self

    async def _async_update_from_cache(self, zc: Zeroconf):
        """Load the records from the cache."""
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
                self._async_handle_loaded_service_info(info)
            else:
                tasks.append(self._async_handle_service(info))

        if tasks:
            await asyncio.gather(*tasks)

    def _async_get_ptr_records(self, zc: Zeroconf) -> list[DNSPointer]:
        """Return all PTR records for the HAP type."""
        return zc.cache.async_all_by_details(self.hap_type, TYPE_PTR, CLASS_IN)

    def _handle_service(
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
            self._loop.time() + 0.5, self._async_resolve_later, name, info
        )

    def _async_resolve_later(self, name: str, info: AsyncServiceInfo):
        """Resolve a host later."""
        # As soon as we get a callback, we can remove the _resolve_later
        # so the next time we get a callback, we can resolve the service
        # again if needed which ensures the TTL is respected.
        self._resolve_later.pop(name, None)

        if not self._running:
            return

        if info.load_from_cache(self._async_zeroconf_instance.zeroconf):
            self._async_handle_loaded_service_info(info)
        else:
            async_create_task(self._async_handle_service(info))

    async def async_stop(self):
        """Stop the controller."""
        self._running = False
        self._browser.service_state_changed.unregister_handler(self._handle_service)
        while self._resolve_later:
            _, cancel = self._resolve_later.popitem()
            cancel.cancel()

    async def async_find(
        self, device_id: str, timeout: float = 10.0
    ) -> ZeroconfDiscovery:
        device_id = device_id.lower()

        if discovery := self._discoveries.get(device_id):
            return discovery

        waiters = self._waiters.setdefault(device_id, [])
        waiter = self._loop.create_future()
        waiters.append(waiter)
        cancel_timeout = self._loop.call_later(timeout, self._async_on_timeout, waiter)

        try:
            if discovery := await waiter:
                return discovery
        except asyncio.TimeoutError:
            raise AccessoryNotFoundError(
                f"Accessory with device id {device_id} not found"
            )
        finally:
            cancel_timeout.cancel()

    async def async_reachable(self, device_id: str, timeout: float = 10.0) -> bool:
        """Check if a device is reachable.

        This method will return True if the device is reachable, False if it is not.

        Typically A/AAAA records have a TTL of 120 seconds which means we may
        see the device as reachable for up to 120 seconds after it has been
        removed from the network if it does not send a goodbye packet.
        """
        try:
            discovery = await self.async_find(device_id, timeout)
        except AccessoryNotFoundError:
            return False
        alias = f"{discovery.description.name}.{self.hap_type}"
        info = AsyncServiceInfo(self.hap_type, alias)
        zc = self._async_zeroconf_instance.zeroconf
        return info.load_from_cache(zc) or await info.async_request(zc, _TIMEOUT_MS)

    def _async_on_timeout(self, future: asyncio.Future):
        if not future.done():
            future.set_exception(asyncio.TimeoutError())

    async def async_discover(self) -> AsyncIterable[ZeroconfDiscovery]:
        for device in self._discoveries.values():
            yield device

    async def _async_handle_service(self, info: AsyncServiceInfo):
        """Add a device that became visible via zeroconf."""
        # AsyncServiceInfo already tries 3x
        await info.async_request(self._async_zeroconf_instance.zeroconf, _TIMEOUT_MS)
        self._async_handle_loaded_service_info(info)

    def _async_handle_loaded_service_info(self, info: AsyncServiceInfo):
        """Handle a service info that was discovered via zeroconf."""
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
            pairing._async_description_update(description)

        if waiters := self._waiters.pop(description.id, None):
            for waiter in waiters:
                if not waiter.cancelled() and not waiter.done():
                    waiter.set_result(discovery)

        if callback := self._on_discovery_callback:
            callback(self, discovery)

    @abstractmethod
    def _make_discovery(self, description: HomeKitService) -> AbstractDiscovery:
        pass

    # Helpers

    def _find_broswer_for_hap_type(self, azc: AsyncZeroconf, hap_type: str) -> AsyncServiceBrowser:
        for browser in azc.zeroconf.listeners:
            if not isinstance(browser, AsyncServiceBrowser):
                continue
            if hap_type not in browser.types:
                continue
            return browser

        raise TransportNotSupportedError(f"There is no zeroconf browser for {hap_type}")

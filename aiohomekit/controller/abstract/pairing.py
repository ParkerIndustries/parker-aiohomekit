from aiohomekit.model import Accessory



class AbstractPairing[Controller: AbstractController, DiscoveryInfo: AbstractDiscoveryInfo](metaclass=ABCMeta):
    # The current discovery information for this pairing.
    # This can be used to detect address changes, s# changes, c# changes, etc
    description: DiscoveryInfo | None = None

    # The normalised (lower case) form of the device id (as seen in zeroconf
    # and BLE advertisements), and also as AccessoryPairingID in pairing data.
    id: str

    def __init__(self, pairing_data: PairingData):
        self.id = pairing_data.AccessoryPairingID
        self.pairing_data = pairing_data

        self.listeners: set[Callable[[dict], None]] = set()
        self.subscriptions: set[tuple[int, int]] = set()
        self.availability_listeners: set[Callable[[bool], None]] = set()
        self.config_changed_listeners: set[Callable[[int], None]] = set()
        self._accessories_state: AccessoriesState | None = None # TODO: make public
        self._shutdown = False

    # Abstract methods

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Returns true if the device is currently connected."""

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Returns true if the device is currently available."""

    @property
    @abstractmethod
    def transport(self) -> Transport:
        """The transport used for the connection."""

    @property
    @abstractmethod
    def poll_interval(self) -> timedelta:
        """Returns how often the device should be polled."""

    @abstractmethod
    def _process_disconnected_events(self):
        """Process any disconnected events that are available."""

    @abstractmethod
    async def thread_provision(
        self,
        dataset: str,
    ):
        """Provision a device with Thread network credentials."""

    @abstractmethod
    async def async_populate_accessories_state(
        self, force_update: bool = False, attempts: int | None = None
    ):
        """Populate the state of all accessories.

        This method should try not to fetch all the accessories unless
        we know the config num is out of date or force_update is True
        """

    @abstractmethod
    async def close(self):
        """Close the connection."""

    @abstractmethod
    async def list_accessories_and_characteristics(self) -> AccessoriesState: # TODO: rename to fetch, return models instead. Add option to get model.as_dict to simulate old behavior
        """List all accessories and characteristics."""

    @abstractmethod
    async def list_pairings(self): # TODO: type annotations
        """List pairings."""

    @abstractmethod
    async def get_characteristics(
        self,
        characteristics: Iterable[tuple[int, int]],
        include_meta: bool = False,
        include_perms: bool = False,
        include_type: bool = False,
        include_events: bool = False,
    ) -> dict[tuple[int, int], dict[str, Any]]:
        """Get characteristics."""

    @abstractmethod
    async def put_characteristics(self, characteristics): # TODO: parse and annotate results
        """Put characteristics."""

    @abstractmethod
    async def identify(self):
        """Identify the device."""

    @abstractmethod
    async def remove_pairing(self, pairing_id: str): # TODO: why on earth does it need id of self
        """Remove a pairing."""

    @abstractmethod
    async def _process_config_changed(self, config_num: int):
        """Process a config change.

        This method is called when the config num changes.
        """

    # Public methods

    @property
    def accessories_state(self) -> AccessoriesState:
        """Return the current state of the accessories."""
        return self._accessories_state

    @property
    def accessories(self) -> Accessories | None:
        """Wrapper around the accessories state to make it easier to use."""
        if not self._accessories_state:
            return None
        return self._accessories_state.accessories

    @property
    def config_num(self) -> int:
        """Wrapper around the accessories state to make it easier to use."""
        if not self._accessories_state:
            return -1
        return self._accessories_state.config_num

    @property
    def name(self) -> str:
        """Return the name of the pairing."""
        if self.description:
            return f"{self.description.name} (id={self.id})"
        return f"(id={self.id})"

    @property
    def broadcast_key(self) -> bytes | None:
        """Returns the broadcast key."""
        if not self._accessories_state:
            return None
        return self._accessories_state.broadcast_key

    @property
    def state_num(self) -> bytes | None:
        """Returns gsn that is saved between restarts."""
        if not self._accessories_state:
            return None
        return self._accessories_state.state_num

    async def get_primary_name(self) -> str:
        """Return the primary name of the device."""
        if not self.accessories:
            accessories = await self.list_accessories_and_characteristics()
            parsed = Accessories.from_list(accessories)
        else:
            parsed = self.accessories

        accessory_info = parsed.aid(1).services.first(
            service_type=ServicesTypes.ACCESSORY_INFORMATION
        )
        return accessory_info.value(CharacteristicsTypes.NAME, "")

    async def shutdown(self):
        """Shutdown the pairing.

        This method is irreversible. It should be called when
        the pairing is removed or the controller is shutdown.
        """
        self._shutdown = True
        await self.close()

    async def subscribe(
        self, characteristics: Iterable[tuple[int, int]]
    ) -> set[tuple[int, int]]:  # TODO: parse and annotate results
        new_characteristics = set(characteristics) - self.subscriptions
        self.subscriptions.update(characteristics)
        return new_characteristics # that's not the actual response, the actual one has status and reason

    async def unsubscribe(self, characteristics: Iterable[tuple[int, int]]):
        self.subscriptions.difference_update(characteristics)

    def dispatcher_availability_changed(
        self, callback: Callable[[bool], None]
    ) -> Callable[[], None]:
        """Notify subscribers when availablity changes.

        Currently this only notifies when a device is seen as available and
        not when it is seen as unavailable.
        """
        self.availability_listeners.add(callback)

        def stop_listening():
            self.availability_listeners.discard(callback)

        return stop_listening

    def dispatcher_connect_config_changed(
        self, callback: Callable[[int], None]
    ) -> Callable[[], None]:
        """Notify subscribers of a new accessories state."""
        self.config_changed_listeners.add(callback)

        def stop_listening():
            self.config_changed_listeners.discard(callback)

        return stop_listening

    def dispatcher_connect(
        self, callback: Callable[[dict], None] # TODO: 1. pass the pairing or it's id; 2. type annotation for the dict
    ) -> Callable[[], None]:
        """
        Register an event handler to be called when a characteristic (or multiple characteristics) change.

        This function returns immediately. It returns a callable you can use to cancel the subscription.

        The callback is called in the event loop, but should not be a coroutine.
        """
        self.listeners.add(callback)

        def stop_listening():
            self.listeners.discard(callback)

        return stop_listening

    # Private methods

    def _callback_listeners(self, event):
        for listener in self.listeners:
            try:
                logger.debug("callback ev:%s", event)
                listener(event)
            except Exception:
                logger.exception("Unhandled error when processing event")

    def _async_description_update(
        self, description: DiscoveryDescription | None
    ):
        if self._shutdown:
            return

        if self.description != description:
            logger.debug(
                "%s: Description updated: old=%s new=%s",
                self.name,
                self.description,
                description,
            )

        repopulate_accessories = False
        if description:
            if description.config_num > self.config_num:
                logger.debug(
                    "%s: Config number has changed from %s to %s; char cache invalid",
                    self.name,
                    self.config_num,
                    description.config_num,
                )
                repopulate_accessories = True

            elif (
                not self.description
                or description.state_num != self.description.state_num
            ):
                # Only process disconnected events if the config number has
                # not also changed since we will do a full repopulation
                # of the accessories anyway when the config number changes.
                #
                # Otherwise, if only the state number we trigger a poll.
                #
                # The number will eventually roll over
                # so we don't want to use a > comparison here. Also, its
                # safer to poll the device again to get the latest state
                # as we don't want to miss events.
                logger.debug(
                    "%s: Disconnected event notification received; Triggering catch-up poll",
                    self.name,
                )
                self._process_disconnected_events()

        self.description = description

        if repopulate_accessories:
            async_create_task(self._process_config_changed(description.config_num))

    async def _shutdown_if_primary_pairing_removed(self, pairingId: str):
        """Shutdown the connection if the primary pairing was removed."""
        if pairingId == self._pairing_data.get("iOSPairingId"):
            await self.shutdown()

    def _callback_availability_changed(self, available: bool):
        """Notify availability changed listeners."""
        for callback in self.availability_listeners:
            callback(available)

    def _callback_and_save_config_changed(self, _config_num: int):
        """Notify config changed listeners and save the config."""
        for callback in self.config_changed_listeners:
            callback(self.config_num)

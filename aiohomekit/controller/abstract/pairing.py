from __future__ import annotations
from uuid import UUID
from typing import Awaitable
from aiohomekit.model import Accessory


class ResponseDict(TypedDict, total=False):
    value: Value | None
    status: int | None
    description: str | None

type Response = dict[CharacteristicKey, ResponseDict]

class AbstractPairing[
    DiscoveryInfo: AbstractDiscoveryInfo
](metaclass=ABCMeta):

    type PairingDataChangeCallback = Callable[[PairingData], None]

    # The current discovery information for this pairing.
    # This can be used to detect address changes, s# changes, c# changes, etc
    description: DiscoveryInfo | None = None
    id: UUID

    def __init__(self, pairing_data: PairingData, on_pairing_data_change: PairingDataChangeCallback | None = None):
        self.id = pairing_data.AccessoryPairingID
        self._pairing_data = pairing_data
        self._on_pairing_data_change = on_pairing_data_change

        self._config_changed_listeners: set[Callable[[int], None]] = set()
        self._characteristic_listeners: set[Callable[[dict], None]] = set()
        self._availability_listeners: set[Callable[[bool], None]] = set()
        self._observed_characteristics: set[CharacteristicKey] = set()

        self._accessories_state = None # has public read
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
    async def fetch_accessories_and_characteristics(self) -> AccessoriesState:
        """List all accessories and characteristics."""

    @abstractmethod
    async def list_pairings(self):
        """List pairings."""

    @abstractmethod
    async def get_characteristics(
        self,
        characteristics: Iterable[CharacteristicKey],
        include_meta: bool = False,
        include_perms: bool = False,
        include_type: bool = False,
        include_events: bool = False,
    ) -> -> Response:
        """Get characteristics."""

    @abstractmethod
    async def put_characteristics(self, characteristics: Iterable[CharacteristicKeyValue]) -> Response:
        """Put characteristics."""

    @abstractmethod
    async def identify(self):
        """Identify the device."""

    @abstractmethod
    async def remove_pairing(self, pairingId: UUID):
        """Remove an accessory pairing to some controller (not necessarily this one)."""

    @abstractmethod
    async def _process_config_changed(self, config_num: int):
        """Process a config change.

        This method is called when the config num changes.
        """

    # Public methods

    @property
    def accessories_state(self) -> AccessoriesState:
        return self._accessories_state

    @property
    def accessories(self) -> Accessories | None:
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
        '''Return the name from discovery description.'''
        if self.description:
            return f"{self.description.name} (id={self.id})"
        return f"(id={self.id})"

    @property
    def broadcast_key(self) -> bytes | None:
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
        """Return the primary name of the device from the accessory information service."""
        if not self.accessories:
            accessories = await self.fetch_accessories_and_characteristics()
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
        self, characteristics: Iterable[CharacteristicKey]
    ) -> set[CharacteristicKey]:
        new_characteristics = set(characteristics) - self._observed_characteristics
        self._observed_characteristics.update(characteristics)
        return new_characteristics # that's not the actual response, the actual one has status and reason

    async def unsubscribe(self, characteristics: Iterable[CharacteristicKey]):
        self._observed_characteristics.difference_update(characteristics)

    def dispatcher_availability_changed(
        self, callback: Callable[[bool], None]
    ) -> Callable[[], None]:
        """Notify subscribers when availablity changes.

        Currently this only notifies when a device is seen as available and
        not when it is seen as unavailable.
        """
        self._availability_listeners.add(callback)

        def stop_listening():
            self._availability_listeners.discard(callback)

        return stop_listening

    def dispatcher_connect_config_changed(
        self, callback: Callable[[int], None]
    ) -> Callable[[], None]:
        """Notify subscribers of a new accessories state."""
        self._config_changed_listeners.add(callback)

        def stop_listening():
            self._config_changed_listeners.discard(callback)

        return stop_listening

    def dispatcher_connect(
        self, callback: Callable[[UUID, dict[CharacteristicKey, Value]], None]
    ) -> Callable[[], None]:
        """
        Register an event handler to be called when a characteristic (or multiple characteristics) change.

        This function returns immediately. It returns a callable you can use to cancel the subscription.

        The callback is called in the event loop, but should not be a coroutine.
        """
        self._characteristic_listeners.add(callback)

        def stop_listening():
            self._characteristic_listeners.discard(callback)

        return stop_listening

    # Private methods

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
        if pairingId == self._pairing_data.iOSDeviceId:
            await self.shutdown()

    def _callback_availability_changed(self, available: bool):
        for callback in self._availability_listeners:
            callback(available)

    def _callback_config_changed(self, _config_num: int):
        for callback in self._config_changed_listeners:
            callback(self.config_num)

    def _callback_characteristic_listeners(self, event):
        for listener in self._characteristic_listeners:
            try:
                logger.debug("callback ev:%s", event)
                listener(self.id, event)
            except Exception:
                logger.exception("Unhandled error when processing event")

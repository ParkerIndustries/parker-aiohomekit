from __future__ import annotations
from abc import abstractmethod
from uuid import UUID
from typing import Callable

from aiohomekit.model.accessories.accessory_state import AccessoriesState


class AbstractPairing[DiscoveryInfo: AbstractDiscoveryInfo](metaclass=ABCMeta):

    type PairingDataChangeCallback = Callable[[PairingData], None]

    # The current discovery information for this pairing.
    # This can be used to detect address changes, s# changes, c# changes, etc
    description: DiscoveryInfo | None = None
    id: UUID

    def __init__(self, pairing_data: PairingData):
        self.id = pairing_data.AccessoryPairingID
        self.pairing_data = pairing_data

        self._availability_observers: list[Callable[[bool], None]] = list()
        self._pairing_data_observers: list[Callable[[PairingData], None]] = list()
        self._config_observers: list[Callable[[int], None]] = list()
        self._characteristic_observers: list[Callable[[dict], None]] = list()
        self._observed_characteristics: set[CharacteristicKey] = set()

        self._accessories_state: AccessoriesState | None = None # has public read
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
    def transport(self) -> TransportType:
        """The transport used for the connection."""

    @property
    @abstractmethod
    def poll_interval(self) -> timedelta:
        """Returns how often the device should be polled."""

    # @abstractmethod
    # async def thread_provision( # TODO: review; shouldn't be implemented in discovery? how is wifi provisioned?
    #     self,
    #     dataset: str,
    # ):
    #     """Provision a device with Thread network credentials."""

    @abstractmethod
    async def close(self):
        """Close the connection."""

    @abstractmethod
    async def list_pairings(self):
        """List pairings."""

    @abstractmethod
    async def identify(self):
        """Identify the device."""

    @abstractmethod
    async def get_characteristics(
        self,
        characteristics: Iterable[CharacteristicKey],
        include_meta: bool = False,
        include_perms: bool = False,
        include_type: bool = False,
        include_events: bool = False,
    ) -> Response:
        """Get characteristics."""

    @abstractmethod
    async def put_characteristics(self, characteristics: Iterable[CharacteristicKeyValue]) -> Response:
        """Put characteristics."""

    @abstractmethod
    async def subscribe_characteristics(
        self, characteristics: Iterable[CharacteristicKey]
    ) -> set[CharacteristicKey]:
        new_characteristics = set(characteristics) - self._observed_characteristics
        self._observed_characteristics.update(characteristics)
        return new_characteristics # that's not the actual response, the actual one has status and reason

    @abstractmethod
    async def unsubscribe_characteristics(self, characteristics: Iterable[CharacteristicKey]):
        self._observed_characteristics.difference_update(characteristics)

    @abstractmethod
    async def remove_pairing(self, pairingId: UUID | None = None):
        """Remove an accessory pairing to some controller (not necessarily this one)."""

    @abstractmethod
    def _process_disconnected_events(self):
        """Process any disconnected events that are available."""

    @abstractmethod
    async def _do_fetch_accessories_and_characteristics(self) -> AccessoriesState:
        """Direct internal implementation of fetching accessories and characteristics to be used by `fetch_accessories_and_characteristics`"""

    # Public properties

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

    # Public methods

    async def fetch_accessories_and_characteristics(
        self, force_update: bool = False, attempts: int | None = None
    ) -> AccessoriesState:
        """Populate the state of all accessories.

        This method should try not to fetch all the accessories unless
        we know the config num is out of date or force_update is True
        """
        if not self.accessories or force_update:
            return await self.fetch_accessories_and_characteristics()
        return self.accessories

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
        """
        This method should be called from the controller, otherwise cache and storage cleanup will not happen.
        This method is irreversible. It should be called when the pairing is removed or the controller is shutdown.
        """
        self._shutdown = True
        await self.close()

    def process_description_update(
        self, description: DiscoveryDescription | None
    ):
        '''Called from outside on each discovery'''

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
                # not also changed since we will do  a full repopulation
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

    # Observers

    def add_observer_for_availability(
        self, callback: Callable[[bool], None]
    ) -> Callable[[], None]:
        """Notify observers when availability changes.

        Currently this only notifies when a device is seen as available and
        not when it is seen as unavailable.
        """
        self._availability_observers.append(callback)

        def stop_observing():
            self._availability_observers.remove(callback)

        return stop_observing

    def add_observer_for_pairing_data(
        self, callback: Callable[[PairingData], None]
    ) -> Callable[[], None]:
        """Register an event handler to be called when pairing data is updated.

        This function returns immediately. It returns a callable you can use to cancel the subscription.
        """
        self._pairing_data_observers.append(callback)

        def stop_observing():
            self._pairing_data_observers.remove(callback)

        return stop_observing

    def add_observer_for_config(
        self, callback: Callable[[int], None]
    ) -> Callable[[], None]:
        """
        Register an event handler to be called when config (services and characteristics model) changes. Tipically, after a firmware update.
        """
        self._config_observers.append(callback)

        def stop_observing():
            self._config_observers.remove(callback)

        return stop_observing

    def add_observer_for_characteristics(
        self, callback: Callable[[UUID, dict[CharacteristicKey, Value]], None]
    ) -> Callable[[], None]:
        """
        Register an event handler to be called when a characteristic (or multiple characteristics) changes.

        Each characteristics must be subscribed using `subscribe`, otherwise the callback will not be called.

        This function returns immediately. It returns a callable you can use to cancel the subscription.

        The callback is called in the event loop, but should not be a coroutine.
        """
        self._characteristic_observers.append(callback)

        def stop_observing():
            self._characteristic_observers.remove(callback)

        return stop_observing

    # Callbacks for observers

    def _callback_availability_changed(self, available: bool):
        for callback in self._availability_observers:
            callback(available)

    def _callback_config_changed(self, _config_num: int):
        for callback in self._config_observers:
            callback(self.config_num)

    def _callback_characteristic_changed(self, event):
        for observer in self._characteristic_observers:
            try:
                logger.debug("callback ev:%s", event)
                observer(self.id, event)
            except Exception:
                logger.exception("Unhandled error when processing event")

    def _callback_pairing_data_changed(self, pairing_data: PairingData):
        for observer in self._pairing_data_observers:
            try:
                observer(pairing_data)
            except Exception:
                logger.exception("Unhandled error when processing pairing data change")

    # Private implementations

    async def _process_config_changed(self, config_num: int):
        await self.fetch_accessories_and_characteristics(force_update=True)
        self._accessories_state.config_num = config_num
        self._callback_config_changed(self.config_num)

    async def _shutdown_if_primary_pairing_removed(self, pairingId: str):
        if pairingId == self.pairing_data.iOSDeviceId:
            await self.shutdown()

    def update_pairing_data(self, pairing_data: PairingData):
        """Update the pairing data and notify listeners."""
        self.pairing_data = pairing_data
        self._callback_pairing_data_changed(pairing_data)

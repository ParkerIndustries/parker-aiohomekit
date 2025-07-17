from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable
from typing import Callable, final

from aiohomekit.model.discovery_info import AbstractDiscoveryInfo
from aiohomekit.model.status_flags import StatusFlags
from aiohomekit.model.typed_dicts import PairingData

type FinishPairing = Callable[[str], Awaitable[PairingData]]
type DiscoveryDidFinishPairingCallback = Callable[[PairingData], None]


class AbstractDiscovery[DiscoveryDescription: AbstractDiscoveryInfo](ABC):

    description: DiscoveryDescription
    _pairing_finished_callback: DiscoveryDidFinishPairingCallback

    def __init__(
        self,
        description: DiscoveryDescription,
        pairing_finished_callback: DiscoveryDidFinishPairingCallback,
    ):
        self.description = description
        self._pairing_finished_callback = pairing_finished_callback
        self.setup()

    # Abstract

    @abstractmethod
    def setup(self):
        """Setup the discovery here to avoid init overrides."""

    @abstractmethod
    async def start_pairing(self) -> FinishPairing:
        """Start pairing."""

    @abstractmethod
    async def identify(self):
        """Do an unpaired identify."""

    # Public

    @final
    @property
    def paired(self) -> bool:
        return not (self.description.status_flags & StatusFlags.UNPAIRED)

    # Private

    def _update_from_discovery(self, description: DiscoveryDescription):
        self.description = description

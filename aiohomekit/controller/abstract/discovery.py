from __future__ import annotations
from uuid import UUID
from typing import Awaitable, Callable
from abc import ABC, abstractmethod


class AbstractDiscovery[PairingDescription: AbstractDescription](ABC):

    type FinishPairing = Callable[[str], Awaitable[PairingData]]
    type DiscoveryDidFinishPairingCallback = Callable[[PairingData], None]

    description: Description
    _pairing_finished_callback: DiscoveryDidFinishPairingCallback

    def __init__(self, description: Description, pairing_finished_callback: DiscoveryDidFinishPairingCallback):
        self.description = description
        self._pairing_finished_callback = pairing_finished_callback
        self.setup()

    # Abstract

    @abstractmethod
    def setup(self):
        """Setup the discovery here to avoid init overrides."""

    @abstractmethod
    async def start_pairing(self, id: UUID) -> FinishPairing:
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

    def _update_from_discovery(self, description: Description):
        self.description = description

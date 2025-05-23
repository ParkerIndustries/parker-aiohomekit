from abc import ABC, abstractmethod


class AbstractDiscovery[Pairing: AbstractPairing](ABC):
    description: AbstractDescription

    FinishPairing = Callable[[str], Awaitable[Pairing]]

    @final
    @property
    def paired(self) -> bool:
        return not (self.description.status_flags & StatusFlags.UNPAIRED)

    @abstractmethod
    async def async_start_pairing(self, id: UUID) -> FinishPairing:
        """Start pairing."""

    @abstractmethod
    async def async_identify(self):
        """Do an unpaired identify."""

import logging
from typing import override

from ..abstract.pairing import AbstractPairing
from .protocol import ZeroconfDiscoveryInfo

logger = logging.getLogger(__name__)


class ZeroconfPairing(AbstractPairing[ZeroconfDiscoveryInfo]):
    @override
    def process_description_update(self, description: ZeroconfDiscoveryInfo):
        old_description = self.description
        super().process_description_update(description)

        endpoint_changed = False
        if not old_description:
            logger.debug("%s: Device rediscovered", self.id)
            endpoint_changed = True
        elif old_description.address != description.address:
            logger.debug(
                "%s: Device IP changed from %s to %s",
                self.id,
                old_description.address,
                description.address,
            )
            endpoint_changed = True
        elif old_description.port != description.port:
            logger.debug(
                "%s: Device port changed from %s to %s",
                self.id,
                old_description.port,
                description.port,
            )
            endpoint_changed = True

        if endpoint_changed:
            self._endpoint_changed()

    def _endpoint_changed(self):
        """The IP and/or port of the accessory has changed."""
        if not self.pairing_data or not self.description:
            return

        self.pairing_data["AccessoryIP"] = self.description.address
        self.pairing_data["AccessoryIPs"] = self.description.addresses

        self._callback_pairing_data_changed(self.pairing_data)

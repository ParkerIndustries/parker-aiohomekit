class ZeroconfPairing(AbstractPairing):
    description: HomeKitService

    def _async_description_update(self, description: HomeKitService | None):
        old_description = self.description

        super()._async_description_update(description)

        if not description:
            return

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
            self._async_endpoint_changed()

    def _async_endpoint_changed(self):
        """The IP and/or port of the accessory has changed."""
        # Update cache so it can be saved later
        # TODO: check for the same bug in other transports, consider moving it to a parent class
        self.pairing_data['AccessoryIP'] = self.description.address
        self.pairing_data['AccessoryIPs'] = self.description.addresses

        # TODO: call controller.save_data or better controler.update_pairing(id, self.pairing_data) to fix the ip change bug
        # currently client must call save_data manually as a workaround

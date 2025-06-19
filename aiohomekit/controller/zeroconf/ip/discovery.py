#
# Copyright 2019 aiohomekit team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from typing import Any, override
import uuid

from aiohomekit.controller.abstract.discovery import AbstractDiscovery, FinishPairing
from aiohomekit.controller.zeroconf.protocol import ZeroconfDiscoveryInfo
from aiohomekit.exceptions import AlreadyPairedError
from aiohomekit.model.typed_dicts import PairingData
from aiohomekit.protocol import perform_pair_setup_part1, perform_pair_setup_part2
from aiohomekit.protocol.statuscodes import to_status_code
from aiohomekit.utils import check_pin_format, pair_with_auth

from .connection import HomeKitConnection


class IpDiscovery(AbstractDiscovery[ZeroconfDiscoveryInfo]):
    """
    A discovered IP HAP device that is unpaired.
    """

    @override
    def setup(self):
        self.connection = HomeKitConnection(
            self, self.description.addresses, self.description.port
        )

    @override
    async def start_pairing(self) -> FinishPairing:
        await self._ensure_connected()

        state_machine = perform_pair_setup_part1(
            pair_with_auth(self.description.feature_flags)
        )
        request, expected = state_machine.send(None)
        while True:
            try:
                response = await self.connection.post_tlv(
                    "/pair-setup",
                    body=request,
                    expected=expected,
                )
                request, expected = state_machine.send(response)
            except StopIteration as result:
                # If the state machine raises a StopIteration then we have XXX
                salt, pub_key = result.value
                break

        async def finish_pairing(pin: str) -> PairingData:
            check_pin_format(pin)

            state_machine = perform_pair_setup_part2(
                pin, str(uuid.uuid4()), salt, pub_key
            )
            request, expected = state_machine.send(None)

            while True:
                try:
                    response = await self.connection.post_tlv(
                        "/pair-setup",
                        body=request,
                        expected=expected,
                    )
                    request, expected = state_machine.send(response)
                except StopIteration as result:
                    # If the state machine raises a StopIteration then we have XXX
                    pairing_data = result.value
                    break

            pairing_data["AccessoryIP"] = self.description.address
            pairing_data["AccessoryIPs"] = self.description.addresses
            pairing_data["AccessoryPort"] = self.description.port
            pairing_data["Connection"] = "IP"

            self._pairing_finished_callback(pairing_data)

            await self.connection.close()  # discovery connection is no longer needed, the pairing connection will be used instead

            return pairing_data

        return finish_pairing

    @override
    async def identify(self):
        await self._ensure_connected()

        response = await self.connection.post_json("/identify", {})

        if not response:
            return True  # empty response means success (no error)

        code = to_status_code(response["code"])

        raise AlreadyPairedError(
            "Identify failed because: {reason} ({code}).".format(
                reason=code.description,
                code=code.value,
            )
        )

    async def close(self):
        await self.connection.close()

    async def _ensure_connected(self):
        await self.connection.ensure_connection()

    def __repr__(self):
        return f"IPDiscovery(host={self.description.address}, port={self.description.port})"

    # ConnectionDelegate Protocol

    async def connection_made(self, is_secure: bool):
        pass

    def event_received(self, event: dict[str, Any]):
        pass  # no events are received during discovery

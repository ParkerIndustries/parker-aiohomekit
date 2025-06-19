#
# Copyright 2022 aiohomekit team
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

from aiohomekit.controller.abstract import (
    AbstractDiscovery,
    DiscoveryDidFinishPairingCallback,
    FinishPairing,
)
from aiohomekit.controller.zeroconf.protocol import ZeroconfDiscoveryInfo
from aiohomekit.model.typed_dicts import PairingData
from aiohomekit.utils import check_pin_format, pair_with_auth

from .connection import CoAPHomeKitConnection


class CoAPDiscovery(AbstractDiscovery):
    """
    A discovered CoAP HAP device that is unpaired.
    """

    def __init__(
        self,
        description: ZeroconfDiscoveryInfo,
        pairing_finished_callback: DiscoveryDidFinishPairingCallback,
    ):
        super().__init__(description, pairing_finished_callback)
        self.connection = CoAPHomeKitConnection(
            None, description.address, description.port
        )

    def __repr__(self):
        return f"CoAPDiscovery(host={self.description.address}, port={self.description.port})"

    async def _ensure_connected(self):
        """
        No preparation needs to be done for pair setup over CoAP.
        """
        return

    async def close(self):
        """
        No teardown needs to be done for pair setup over CoAP.
        """
        return

    async def identify(self):
        return await self.connection.do_identify()

    async def start_pairing(self) -> FinishPairing:
        salt, srpB = await self.connection.do_pair_setup(
            pair_with_auth(self.description.feature_flags)
        )

        async def finish_pairing(pin: str) -> PairingData:
            check_pin_format(pin)

            pairing_data = await self.connection.do_pair_setup_finish(pin, salt, srpB)
            pairing_data["AccessoryIP"] = self.description.address
            pairing_data["AccessoryPort"] = self.description.port
            pairing_data["Connection"] = "CoAP"

            self._pairing_finished_callback(pairing_data)

            return pairing_data

        return finish_pairing

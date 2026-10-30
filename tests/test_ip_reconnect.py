import asyncio
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from aiohomekit.controller.relay import Controller
from aiohomekit.controller.zeroconf.ip import IpPairing
from aiohomekit.controller.zeroconf.ip.connection import SecureHomeKitConnection
from aiohomekit.exceptions import AuthenticationError
from aiohomekit.model.characteristics.characteristic_key import CharacteristicKey

UNKNOWN_CONTROLLER_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def connect_attempts() -> Iterator[list[float]]:
    """The reconnect backoff at every secure connect attempt."""
    attempts = []
    connect_once = SecureHomeKitConnection._connect_once

    async def counting_connect_once(self: SecureHomeKitConnection):
        attempts.append(self._reconnect_backoff)
        await connect_once(self)

    with patch.object(SecureHomeKitConnection, "_connect_once", counting_connect_once):
        yield attempts


def rejected_pairing(controller: Controller) -> IpPairing:
    """A pairing the accessory rejects at pair-verify; it then closes the socket."""
    paired = next(iter(controller.pairings.values()))
    return IpPairing({**paired.pairing_data, "iOSDeviceId": UNKNOWN_CONTROLLER_ID})


async def test_rejected_pairing_backs_off_between_reconnects(
    controller_and_paired_accessory: Controller, connect_attempts: list[float]
):
    pairing = rejected_pairing(controller_and_paired_accessory)

    with pytest.raises(AuthenticationError):
        await pairing.get_characteristics([(1, 9)])
    await asyncio.sleep(1.5)
    await pairing.close()

    # at 0, 0.5 and 1.25 s with a backoff of 0.5 s growing 1.5x; a tight loop makes hundreds
    assert connect_attempts == [0.0, 0.5, 0.75]


async def test_successful_connection_resets_the_backoff(
    controller_and_paired_accessory: Controller, connect_attempts: list[float]
):
    pairing = rejected_pairing(controller_and_paired_accessory)
    with pytest.raises(AuthenticationError):
        await pairing.get_characteristics([(1, 9)])
    await asyncio.sleep(0.8)  # the second attempt, at 0.5 s, fails too
    assert len(connect_attempts) == 2

    # The accessory accepts us again (e.g. re-paired); the next attempt connects
    paired = next(iter(controller_and_paired_accessory.pairings.values()))
    pairing.pairing_data["iOSDeviceId"] = paired.pairing_data["iOSDeviceId"]
    await pairing.get_characteristics([(1, 9)])

    # A dropped session reconnects at once instead of waiting out the old backoff
    attempts_before_drop = len(connect_attempts)
    pairing.connection.transport.close()
    async with asyncio.timeout(0.3):
        while len(connect_attempts) == attempts_before_drop or not pairing.is_connected:
            await asyncio.sleep(0.01)
    await pairing.close()


async def test_reconnect_soon_cuts_the_backoff_short(
    controller_and_paired_accessory: Controller, connect_attempts: list[float]
):
    pairing = rejected_pairing(controller_and_paired_accessory)
    pairing.connection._reconnect_backoff = 30  # as after a dozen rejected loops
    pairing.connection._connection_lost(ConnectionResetError())  # the next loop waits
    await asyncio.sleep(0.1)
    assert connect_attempts == []

    pairing.connection.reconnect_soon()  # e.g. zeroconf saw the accessory again
    await asyncio.sleep(0.1)

    assert connect_attempts == [30]
    await pairing.close()


@pytest.mark.parametrize("loop_waiting", [True, False])
async def test_call_during_the_backoff_fails_fast(controller_and_paired_accessory: Controller, loop_waiting: bool):
    pairing = rejected_pairing(controller_and_paired_accessory)
    pairing.connection._reconnect_backoff = 30  # as after a dozen rejected loops
    if loop_waiting:
        pairing.connection._connection_lost(ConnectionResetError())
        await asyncio.sleep(0.1)

    # It tries at once, as before the backoff, instead of timing out after 10 s
    async with asyncio.timeout(2):
        with pytest.raises(AuthenticationError):
            await pairing.get_characteristics([CharacteristicKey(1, 9)])
    await pairing.close()

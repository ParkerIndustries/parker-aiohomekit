import pytest

from aiohomekit.exceptions import InvalidError
from aiohomekit.protocol import handle_state_step
from aiohomekit.protocol.tlv import TLV


def test_state_mismatch_names_both_states_as_numbers():
    with pytest.raises(InvalidError) as exc_info:
        handle_state_step({TLV.kTLVType_State: TLV.M4}, TLV.M2)

    assert exc_info.value.stage == "Expected state 2 but got 4"


def test_empty_state_is_a_state_mismatch():
    with pytest.raises(InvalidError):
        handle_state_step({TLV.kTLVType_State: bytearray()}, TLV.M2)

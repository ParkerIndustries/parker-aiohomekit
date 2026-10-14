"""Test status codes."""

from aiohomekit.protocol.statuscodes import HapStatusCode, to_status_code


async def test_normalized_statuscodes():
    """Verify we account for quirks in HAP implementations."""
    assert to_status_code(70411) == HapStatusCode.INSUFFICIENT_AUTH
    assert to_status_code(-70411) == HapStatusCode.INSUFFICIENT_AUTH


def test_unknown_statuscodes():
    """Vendor-specific or undefined codes must not raise."""
    assert to_status_code(-6) == HapStatusCode.UNKNOWN
    assert to_status_code(6) == HapStatusCode.UNKNOWN
    assert to_status_code(-99999) == HapStatusCode.UNKNOWN

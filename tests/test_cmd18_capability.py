"""Tests for enhanced CMD18 firmware detection and payload compatibility."""

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.linktap.const import PAUSE_CMD
from custom_components.linktap.linktap_local import (
    LinktapLocal,
    parse_gateway_firmware_version,
    supports_enhanced_cmd18,
)
from tests.conftest import MOCK_GW_ID, MOCK_GW_IP, MOCK_TAP_ID


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("S0609502609181404I", 60950),
        ("S0609512609181404I", 60951),
        ("G0609512609181404I", 60951),
        ("W123456future", 123456),
        (None, None),
        ("", None),
        ("S06095", None),
        ("S06A9512609181404I", None),
    ],
)
def test_parse_gateway_firmware_version(version, expected):
    assert parse_gateway_firmware_version(version) == expected


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("S0609502609181404I", False),
        ("S0609512609181404I", True),
        ("G0609512609181404I", True),
        ("W060952future", True),
        (None, False),
        ("malformed", False),
    ],
)
def test_supports_enhanced_cmd18(version, expected):
    assert supports_enhanced_cmd18(version) is expected


@pytest.fixture
def linktap():
    client = LinktapLocal()
    client.set_ip(MOCK_GW_IP)
    return client


async def test_cmd16_caches_enhanced_capability(linktap):
    config = {"ret": 0, "ver": "S0609512609181404I"}
    with patch.object(linktap, "_request", AsyncMock(return_value=config)):
        result = await linktap.get_gw_config(MOCK_GW_ID)

    assert result == config
    assert linktap.gateway_version == "S0609512609181404I"
    assert linktap.enhanced_cmd18 is True


@pytest.mark.parametrize("version", ["S0609502609181404I", "4.38", None])
async def test_cmd16_defaults_old_or_unknown_firmware_to_legacy(linktap, version):
    config = {"ret": 0, "ver": version}
    with patch.object(linktap, "_request", AsyncMock(return_value=config)):
        await linktap.get_gw_config(MOCK_GW_ID)

    assert linktap.gateway_version == version
    assert linktap.enhanced_cmd18 is False


async def test_legacy_pause_payload_omits_option(linktap):
    request = AsyncMock(return_value={"ret": 0})
    with patch.object(linktap, "_request", request):
        result = await linktap.pause_tap(MOCK_GW_ID, MOCK_TAP_ID, 3)

    assert result is True
    request.assert_awaited_once_with(
        {
            "cmd": PAUSE_CMD,
            "gw_id": MOCK_GW_ID,
            "dev_id": MOCK_TAP_ID,
            "duration": 3,
        }
    )


@pytest.mark.parametrize("option", [0, 1])
async def test_enhanced_pause_payload_includes_option(linktap, option):
    request = AsyncMock(return_value={"ret": 0})
    with patch.object(linktap, "_request", request):
        result = await linktap.pause_tap(MOCK_GW_ID, MOCK_TAP_ID, 0.1, option=option)

    assert result is True
    request.assert_awaited_once_with(
        {
            "cmd": PAUSE_CMD,
            "gw_id": MOCK_GW_ID,
            "dev_id": MOCK_TAP_ID,
            "duration": 0.1,
            "option": option,
        }
    )


async def test_resume_can_include_option_for_enhanced_firmware(linktap):
    request = AsyncMock(return_value={"ret": 0})
    with patch.object(linktap, "_request", request):
        result = await linktap.pause_tap(MOCK_GW_ID, MOCK_TAP_ID, 0, option=1)

    assert result is True
    payload = request.await_args.args[0]
    assert payload["duration"] == 0
    assert payload["option"] == 1

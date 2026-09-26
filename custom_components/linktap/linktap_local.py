import json
import logging
import re
from json.decoder import JSONDecodeError

import aiohttp
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .const import (
    CONFIG_CMD,
    DEFAULT_TIME,
    DISMISS_ALERT_CMD,
    PAUSE_CMD,
    START_CMD,
    STATUS_CMD,
    STOP_CMD,
)

_LOGGER = logging.getLogger(__name__)

ENHANCED_CMD18_MIN_VERSION = 60951


def parse_gateway_firmware_version(version):
    """Return the six-digit LinkTap firmware number, or None if invalid.

    LinkTap defines the capability version as the six characters immediately
    following the gateway-generation prefix (for example S060951... -> 60951).
    """
    if not isinstance(version, str) or len(version) < 7:
        return None
    numeric_version = version[1:7]
    if not numeric_version.isdigit():
        return None
    return int(numeric_version)


def supports_enhanced_cmd18(version):
    """Return whether a gateway firmware supports enhanced CMD18 semantics."""
    numeric_version = parse_gateway_firmware_version(version)
    return (
        numeric_version is not None
        and numeric_version >= ENHANCED_CMD18_MIN_VERSION
    )


class LinktapLocal:

    ip = False
    gw_id = False

    def __init__(self):
        # Keep capability unknown/legacy-safe until CMD16 config is read.
        self.gateway_version = None
        self.enhanced_cmd18 = False
        print("Hello, its me!")

    def set_ip(self, ip):
        self.ip = ip

    def get_ip(self, ip):
        return self.ip

    def set_gw_id(self, gw_id):
        self.gw_id = gw_id

    def get_gw_id(self):
        return self.gw_id

    def clean_response(self, text):
        """Remove html tags from a string"""
        text = text.replace("api", "")
        clean = re.compile("<.*?>")
        cleaned_text = re.sub(clean, "", text)
        cleaned_text = cleaned_text.replace("api", "")
        return cleaned_text.strip()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(JSONDecodeError),
    )
    async def _request(self, data):

        headers = {"content-type": "application/json; charset=UTF-8"}

        url = "http://" + self.ip + "/api.shtml"

        async with aiohttp.ClientSession() as session:
            async with await session.post(url, json=data, headers=headers) as resp:
                status = resp.status
                try:
                    """Check if it's JSON formatted"""
                    response = await resp.json()
                except aiohttp.client_exceptions.ContentTypeError:
                    """Fallback to html wrapped"""
                    response = json.loads(self.clean_response(await resp.text()))

        if status == 404:
            _LOGGER.debug("Got a 404 issue: Wait and try again")
            raise JSONDecodeError("404 Not Found", "", 0)
        return response

    async def fetch_data(self, gw_id, dev_id):
        status = await self.get_tap_status(gw_id, dev_id)
        return status

    async def get_tap_status(self, gw_id, dev_id):
        data = {
            "cmd": STATUS_CMD,
            "gw_id": gw_id,
            "dev_id": dev_id,
        }
        status = await self._request(data)
        return status

    async def turn_on(self, gw_id, dev_id, seconds=None, volume=None):
        if (not seconds or seconds == 0) and not volume:
            seconds = DEFAULT_TIME * 60
        data = {
            "cmd": START_CMD,
            "gw_id": gw_id,
            "dev_id": dev_id,
            "duration": int(float(seconds)),
        }
        if volume and volume != 0:
            data["volume"] = volume
        _LOGGER.debug(f"Data to Turn ON: {data}")
        status = await self._request(data)
        _LOGGER.debug(f"Response: {status}")
        return status["ret"] == 0

    async def turn_off(self, gw_id, dev_id):
        data = {
            "cmd": STOP_CMD,
            "gw_id": gw_id,
            "dev_id": dev_id,
        }
        status = await self._request(data)
        return status["ret"] == 0

    async def pause_tap(self, gw_id, dev_id, hours, option=None):
        """Send CMD18, optionally including the enhanced-firmware option field."""
        data = {
            "cmd": PAUSE_CMD,
            "gw_id": gw_id,
            "dev_id": dev_id,
            "duration": hours,
        }
        if option is not None:
            data["option"] = option
        _LOGGER.debug(f"Pause Payload: {data}")
        status = await self._request(data)
        _LOGGER.debug(f"Pause Response: {status}")
        return status["ret"] == 0

    async def get_gw_config(self, gw_id):
        data = {"cmd": CONFIG_CMD, "gw_id": gw_id}
        status = await self._request(data)
        # async_setup_entry already reads CMD16 once at startup. Cache the
        # capability on this shared API object so every tap coordinator can use
        # the same gateway-level result without another HTTP request.
        self.gateway_version = status.get("ver")
        self.enhanced_cmd18 = supports_enhanced_cmd18(self.gateway_version)
        _LOGGER.debug(
            "LinkTap gateway firmware %r enhanced CMD18 support: %s",
            self.gateway_version,
            self.enhanced_cmd18,
        )
        return status

    async def get_vol_unit(self, gw_id):
        config = await self.get_gw_config(gw_id)
        return config["vol_unit"]

    async def get_version(self, gw_id):
        config = await self.get_gw_config(gw_id)
        return config["ver"]

    async def get_end_devs(self, gw_id):
        config = await self.get_gw_config(gw_id)
        return {
            "devs": config["end_dev"],
            "names": config["dev_name"],
        }

    async def get_gw_id(self):
        data = {"cmd": STATUS_CMD}
        status = await self._request(data)
        return status["gw_id"]

    async def dismiss_alert(self, gw_id, dev_id, alert_id=False):
        if not alert_id:
            alert_id = 0
        data = {
            "cmd": DISMISS_ALERT_CMD,
            "gw_id": gw_id,
            "dev_id": dev_id,
            "alert": alert_id,
            "enable": True,
        }
        status = await self._request(data)
        return status["ret"] == 0
        return status["ret"] == 0

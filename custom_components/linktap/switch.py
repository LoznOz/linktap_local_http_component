import asyncio
import json
import logging
import random
import re

import aiohttp
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import service
from homeassistant.helpers.entity import *
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (CoordinatorEntity,
                                                      DataUpdateCoordinator)
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)

from .const import (ATTR_DEFAULT_TIME, ATTR_DURATION, ATTR_STATE, ATTR_VOL,
                    ATTR_VOLUME, DEFAULT_TIME, DEFAULT_VOL, DOMAIN, GW_ID,
                    GW_IP, MANUFACTURER, NAME, TAP_ID)


def _number_entity_id(hass, tap_id, suffix):
    """Resolve a LinkTap number entity by its stable unique ID.

    Do not construct an entity_id from the tap name. Home Assistant entity IDs
    can include area/device components and can also be renamed by the user.
    The unique ID is stable and is the correct registry key for sibling lookup.
    """
    unique_id = slugify(f"{DOMAIN}_number_{tap_id}_{suffix}")
    return er.async_get(hass).async_get_entity_id(
        NUMBER_DOMAIN, DOMAIN, unique_id
    )


async def async_setup_entry(
    hass, config, async_add_entities, discovery_info=None
):
    """Setup the switch platform."""
    taps = hass.data[DOMAIN][config.entry_id]["conf"]["taps"]
    switches = []
    for tap in taps:
        coordinator = tap["coordinator"]
        _LOGGER.debug(f"Configuring switch for tap {tap}")
        switches.append(LinktapSwitch(coordinator, hass, tap))
        switches.append(LinktapPauseSwitch(coordinator, hass, tap))
    async_add_entities(switches, True)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service("pause",
        {vol.Required("hours", default=1): vol.Coerce(int)},
        "_pause_tap"
        )


class LinktapSwitch(CoordinatorEntity, SwitchEntity):
    # Modern HA naming: this is a main feature of the device.
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: DataUpdateCoordinator, hass, tap):
        super().__init__(coordinator)
        self._state = None
        self._name = tap[NAME]
        self._id = tap[TAP_ID]
        self.tap_id = tap[TAP_ID]
        self.tap_api = coordinator.tap_api
        self.platform = "switch"
        self.hass = hass
        self._attr_unique_id = slugify(f"{DOMAIN}_{self.platform}_{self.tap_id}")
        self._attr_icon = "mdi:water-pump"
        self._attrs = {
            "data": self.coordinator.data,
        }
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, tap[TAP_ID])
            },
            name=tap[NAME],
            manufacturer=MANUFACTURER,
            configuration_url="http://" + tap[GW_IP] + "/"
        )

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def duration_entity(self):
        return _number_entity_id(self.hass, self.tap_id, "watering_duration")

    @property
    def volume_entity(self):
        return _number_entity_id(self.hass, self.tap_id, "watering_volume")

    async def async_turn_on(self, **kwargs):
        duration = self.get_watering_duration()
        seconds = int(float(duration)) * 60
        gw_id = self.coordinator.get_gw_id()
        attributes = await self.tap_api.turn_on(
            gw_id, self.tap_id, seconds, self.get_watering_volume()
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        gw_id = self.coordinator.get_gw_id()
        attributes = await self.tap_api.turn_off(gw_id, self.tap_id)
        await self.coordinator.async_request_refresh()

    def get_watering_duration(self):
        entity_id = self.duration_entity
        entity = self.hass.states.get(entity_id) if entity_id else None
        if not entity:
            _LOGGER.debug(
                "Watering duration entity could not be resolved -- setting default"
            )
            duration = DEFAULT_TIME
            self._attrs[ATTR_DEFAULT_TIME] = True
        elif entity.state == STATE_UNKNOWN:
            _LOGGER.debug(
                f"Entity {entity_id} state unknown -- setting default"
            )
            duration = DEFAULT_TIME
            self._attrs[ATTR_DEFAULT_TIME] = True
        else:
            duration = entity.state
            self._attrs[ATTR_DEFAULT_TIME] = False
        self._attrs[ATTR_DURATION] = duration
        return duration

    def get_watering_volume(self):
        entity_id = self.volume_entity
        entity = self.hass.states.get(entity_id) if entity_id else None
        if not entity:
            volume = DEFAULT_VOL
            _LOGGER.debug(
                "Watering volume entity could not be resolved -- setting default"
            )
            self._attrs[ATTR_VOL] = False
        elif entity.state == STATE_UNKNOWN:
            volume = DEFAULT_VOL
            _LOGGER.debug(
                f"Entity {entity_id} state unknown -- setting default"
            )
            self._attrs[ATTR_VOL] = False
        elif int(float(entity.state)) == 0:
            volume = entity.state
            _LOGGER.debug(f"Entity {entity_id} set to 0 -- ignore")
            self._attrs[ATTR_VOL] = False
        else:
            volume = entity.state
            self._attrs[ATTR_VOL] = True
        self._attrs[ATTR_VOLUME] = volume
        return float(volume)

    @property
    def extra_state_attributes(self):
        # Resolve dynamically so HA/user entity-id renames are followed.
        self._attrs["duration_entity"] = self.duration_entity
        self._attrs["volume_entity"] = self.volume_entity
        return self._attrs

    @property
    def state(self):
        status = self.coordinator.data
        self._attrs["data"] = status
        _LOGGER.debug(f"Switch Status: {status}")
        duration = self.get_watering_duration()
        _LOGGER.debug(f"Set duration:{duration}")
        volume = self.get_watering_volume()
        _LOGGER.debug(f"Set volume:{volume}")
        self._attrs[ATTR_STATE] = status[ATTR_STATE]
        state = "unknown"
        if status[ATTR_STATE]:
            state = "on"
        elif not status[ATTR_STATE]:
            state = "off"
            _LOGGER.debug(f"Switch {self.entity_id} state {state}")
        return state

    @property
    def is_on(self):
        return self.state == "on"

    @property
    def device_info(self) -> DeviceInfo:
        return self._attr_device_info

    async def _pause_tap(self, hours=None):
        if hours is None:
            hours = 1
        _LOGGER.debug(f"Pausing {self.entity_id} for {hours} hours")
        gw_id = self.coordinator.get_gw_id()
        await self.tap_api.pause_tap(gw_id, self.tap_id, hours)
        await self.coordinator.async_request_refresh()


class LinktapPauseSwitch(CoordinatorEntity, SwitchEntity):
    # Modern HA naming: entity name is relative to the device name.
    _attr_has_entity_name = True
    _attr_name = "Pause"

    def __init__(self, coordinator: DataUpdateCoordinator, hass, tap):
        super().__init__(coordinator)
        self._name = f"Pause {tap[NAME]}"
        self.tap_name = tap[NAME]
        self.tap_id = tap[TAP_ID]
        self.platform = "switch"
        self.hass = hass
        self._attr_unique_id = slugify(f"{DOMAIN}_{self.platform}_{self.tap_id}_pause")
        self._attr_icon = "mdi:pause-circle"
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, tap[TAP_ID])
            },
            name=tap[NAME],
            manufacturer=MANUFACTURER,
            configuration_url="http://" + tap[GW_IP] + "/"
        )
        self.coordinator = coordinator
        self._attrs = {}

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def pause_duration_entity(self):
        return _number_entity_id(self.hass, self.tap_id, "pause_duration")

    @property
    def is_on(self):
        status = self.coordinator.data
        return bool(status.get("is_paused", False))

    @property
    def extra_state_attributes(self):
        self._attrs["pause_duration_entity"] = self.pause_duration_entity
        return self._attrs

    async def async_turn_on(self, **kwargs):
        hours = 24
        entity_id = self.pause_duration_entity
        _LOGGER.debug(f"PauseSwitch: Looking for {entity_id}")
        entity = self.hass.states.get(entity_id) if entity_id else None
        if entity and entity.state not in (None, "unknown"):
            _LOGGER.debug(
                f"PauseSwitch: Found pause duration entity {entity_id} "
                f"with state {entity.state}"
            )
            try:
                hours = int(float(entity.state))
            except Exception as e:
                _LOGGER.warning(
                    f"PauseSwitch: Could not parse pause duration, using default 24: {e}"
                )
        await self._pause_tap(hours=hours)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self._pause_tap(hours=0)
        await self.coordinator.async_request_refresh()

    async def _pause_tap(self, hours):
        _LOGGER.debug(f"PauseSwitch: Pausing {self.entity_id} for {hours} hours")
        gw_id = self.coordinator.get_gw_id()
        await self.coordinator.tap_api.pause_tap(gw_id, self.tap_id, hours)

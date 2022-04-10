"""Support for lights through the Lumic API."""
from __future__ import annotations

from collections.abc import Sequence

import logging
import colorsys
import asyncio

from homeassistant.components.switch import (
    SwitchEntity
)
import homeassistant.util.color as color_util
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import (
    aiohttp_client,
    config_entry_oauth2_flow,
    config_validation as cv,
)
from homeassistant.util import Throttle
from datetime import timedelta

from .api import OAuth2Client, LumicAPI
from .const import ATTR_DEVICE_TYPE_SWITCH, DOMAIN


_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the WiZ Light platform from legacy config."""

    try:
        auth = OAuth2Client(hass, config)
        api = LumicAPI(auth, hass, config)
        devices = await api.getHomeDevices(ATTR_DEVICE_TYPE_SWITCH)
        for i in devices:
            try:
                async_add_entities(
                    [LumicSwitch(api, i["id"], i["uuid"], i["room"]["name"] + " " + i["name"])],
                    update_before_add=True,
                )
            except Exception as e:
                _LOGGER.error("Can't add Lumic Light with ID %s.", i["uuid"])
                _LOGGER.error(e)
    except Exception as e:
        _LOGGER.error("Can't add Lumic Lights:")
        _LOGGER.error(e)
        return False

    return True


async def async_setup_entry(hass, config_entry, async_add_devices):
    try:
        auth = OAuth2Client(hass, config_entry.data)
        api = LumicAPI(auth, hass, config_entry.data)
        device_registry = await hass.helpers.device_registry.async_get_registry()
        
        devices = await api.getHomeDevices(ATTR_DEVICE_TYPE_SWITCH)
        for i in devices:
            try:
                async_add_devices(
                    [LumicSwitch(api, i["id"], i["uuid"], i["room"]["name"] + " " + i["name"])],
                    update_before_add=True,
                )
                device_registry.async_get_or_create(
                    config_entry_id=config_entry.entry_id,
                    connections={(dr.CONNECTION_NETWORK_MAC, i["hardwareAddress"])},
                    identifiers={(DOMAIN, i["id"])},
                    manufacturer="Cedgetec",
                    name=i["room"]["name"] + " " + i["name"],
                    model="Switch V1.0",
                    sw_version=0.2,
                )
            except Exception as e:
                _LOGGER.error("Can't add Lumic Switch with ID %s.", i["uuid"])
                _LOGGER.error(e)
    except Exception as e:
        _LOGGER.error("Can't add Lumic Switches:")
        _LOGGER.error(e)
        return False

    return True


def get_capabilities(capabilities: Sequence[str]) -> Sequence[str] | None:
    """Return all capabilities supported if minimum required are present."""
    supported = [
        Capability.switch,
    ]
    return supported


class LumicSwitch(SwitchEntity):
    """Define a Lumict light."""

    def __init__(self, api, device_id, device_uuid, name):
        """Initialize a Lumic light."""
        self._lock = asyncio.Lock()
        self._api = api
        self._device_id = device_id
        self._device_uuid = device_uuid
        self._name = name
        self._mac = None
        self._brightness = 0
        self._hs_color = [0, 0]
        self._state = False
        self._supported_features = self._determine_features()
        self._logger = logging.getLogger(
            ("%s:%s:<%s>") % (__name__, self.__class__.__name__, self._device_uuid)
        )

    def _determine_features(self):
        """Get features supported by the device."""
        return None

    def scale(self, value, max, target_max):
        return value * target_max / max

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        try:
            await self._lock.acquire()
            self._logger.info("On")
            if not self._state:
                await self._api.setDeviceParameter(self._device_uuid, "STATE", "1")
                self._state = True
            self.async_schedule_update_ha_state(True)
        finally:
            self._lock.release()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        try:
            await self._lock.acquire()
            self._logger.info("Off")
            self._state = False
            await self._api.setDeviceParameter(self._device_uuid, "STATE", "0")
            self.async_schedule_update_ha_state(True)
        finally:
            self._lock.release()

    async def async_update(self):
        """Update entity attributes when the device status has changed."""
        self._logger.info(
            "HIER PASSIERT FIESES ZEUGS! Diesmal mit jenem Lumic Switch: %s",
            self._device_uuid,
        )

        result = await self._api.getDeviceById(self._device_id)

        self._mac = result["hardwareAddress"]

        color = None
        color_white = None

        for i in result["deviceParameters"]:
            # State
            if i["type"] == "STATE" and i["valueNumeric"] == 1:
                self._state = True
            elif i["type"] == "STATE":
                self._state = False
            
    async def async_set_color(self, hs_color):
        """Set the color of the device."""

    async def async_set_level(self, brightness: int, transition: int):
        """Set the brightness of the light over transition."""

    @property
    def device_info(self):
        return {
            "identifiers": {
                (DOMAIN, self.unique_id)
            },
            "connections": {(dr.CONNECTION_NETWORK_MAC, self._mac)},
            "name": self.name,
            "manufacturer": "Cedgetec",
            "model": "Lumic",
            "sw_version": 0.2,
        }

    @property
    def unique_id(self):
        """Return light unique_id."""
        return self._device_id

    @property
    def name(self):
        """Return the ip as name of the device if any."""
        return self._name

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        return self._brightness

    @property
    def color_temp(self):
        """Return the CT color value in mireds."""
        return self._color_temp

    @property
    def hs_color(self):
        """Return the hue and saturation color value [float, float]."""
        return self._hs_color

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._state

    @property
    def max_mireds(self):
        """Return the warmest color_temp that this light supports."""
        return 255

    @property
    def min_mireds(self):
        """Return the coldest color_temp that this light supports."""
        return 0

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return self._supported_features

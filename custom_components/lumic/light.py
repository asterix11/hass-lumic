"""Support for lights through the Lumic API."""
from __future__ import annotations

from collections.abc import Sequence

import logging
import colorsys
import asyncio

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_HS_COLOR,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    LightEntity,
)
import homeassistant.util.color as color_util
from homeassistant.helpers import (
    aiohttp_client,
    config_entry_oauth2_flow,
    config_validation as cv,
    device_registry as dr,
)
from homeassistant.util import Throttle
from datetime import timedelta

from .api import OAuth2Client, LumicAPI
from .const import ATTR_DEVICE_TYPE_LIGHT, DOMAIN


_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the WiZ Light platform from legacy config."""

    try:
        auth = OAuth2Client(hass, config)
        api = LumicAPI(auth, hass, config)
        device_registry = await hass.helpers.device_registry.async_get_registry()
        
        devices = await api.getHomeDevices(ATTR_DEVICE_TYPE_LIGHT)
        for i in devices:
            try:
                async_add_entities(
                    [LumicLight(api, i["id"], i["uuid"], i["room"]["name"] + " " + i["name"])],
                    update_before_add=True,
                )
                device_registry.async_get_or_create(
                    config_entry_id=i["id"],
                    connections={(dr.CONNECTION_NETWORK_MAC, i["hardwareAddress"])},
                    identifiers={(DOMAIN, i["id"])},
                    manufacturer="Lumic",
                    name=i["room"]["name"] + " " + i["name"],
                    model="Light V1.0",
                    sw_version=0.2,
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
        
        devices = await api.getHomeDevices(ATTR_DEVICE_TYPE_LIGHT)
        for i in devices:
            try:
                async_add_devices(
                    [LumicLight(api, i["id"], i["uuid"], i["room"]["name"] + " " + i["name"])],
                    update_before_add=True,
                )
                device_registry.async_get_or_create(
                    config_entry_id=config_entry.entry_id,
                    connections={(dr.CONNECTION_NETWORK_MAC, i["hardwareAddress"])},
                    identifiers={(DOMAIN, i["id"])},
                    manufacturer="Lumic",
                    name=i["room"]["name"] + " " + i["name"],
                    model="Light V1.0",
                    sw_version=0.2,
                )
            except Exception as e:
                _LOGGER.error("Can't add Lumic Light with ID %s.", i["uuid"])
                _LOGGER.error(e)
    except Exception as e:
        _LOGGER.error("Can't add Lumic Lights:")
        _LOGGER.error(e)
        return False

    return True

def get_capabilities(capabilities: Sequence[str]) -> Sequence[str] | None:
    """Return all capabilities supported if minimum required are present."""
    supported = [
        Capability.switch,
        Capability.switch_level,
        Capability.color_control,
        Capability.color_rgbw,
    ]
    return supported


class LumicLight(LightEntity):
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
        features = SUPPORT_BRIGHTNESS | SUPPORT_COLOR

        return features

    def scale(self, value, max, target_max):
        return value * target_max / max

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        try:
            await self._lock.acquire()
            self._logger.info("On")
            if "brightness" in kwargs:
                self._logger.info("Found brightness attribute: %i", kwargs["brightness"])
                brightness = kwargs["brightness"]
                await self._api.setDeviceParameter(
                    self._device_uuid, "BRIGHTNESS", str(brightness)
                )
            if "hs_color" in kwargs:
                hs_color = kwargs["hs_color"]
                color_rgb = colorsys.hsv_to_rgb(self.scale(hs_color[0], 360, 1), 1.0, 255)
                color_rgb_str = '#%02x%02x%02x' % (int(color_rgb[0]), int(color_rgb[1]), int(color_rgb[2]))
                color_white = int(255 - self.scale(int(hs_color[1]), 100, 255))
                if (color_white == 255):
                    color_rgb_str = "#000000"

                await self._api.setDeviceParameter(
                    self._device_uuid, "COLOR", str(color_rgb_str)
                )
                await self._api.sleep(0.5)
                await self._api.setDeviceParameter(
                    self._device_uuid, "COLOR_WHITE", str(color_white)
                )
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
            "HIER PASSIERT FIESES ZEUGS! Diesmal mit jenem Lumic Light: %s",
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

            # Brightness
            if (
                self._supported_features & SUPPORT_BRIGHTNESS
                and i["type"] == "BRIGHTNESS"
            ):
                self._brightness = i["valueNumeric"]

            # Color
            if self._supported_features & SUPPORT_COLOR and i["type"] == "COLOR":
                color = i["value"]
            if self._supported_features & SUPPORT_COLOR and i["type"] == "COLOR_WHITE":
                color_white = i["valueNumeric"]
        
        if (color != None and color_white != None):
            r, g, b = int("0x%s" % color[1:3], base=16), int("0x%s" % color[3:5], base=16), int("0x%s" % color[5:7], base=16)
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            scaled_hue = int(self.scale(h, 1, 360))
            scaled_cw = int(self.scale(255-color_white, 255, 100))
            self._hs_color = [scaled_hue, scaled_cw]
            
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

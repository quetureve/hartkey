"""Button platform for Hartkey integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import async_timeout

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, API_URL_OPEN, DEVICE_TYPE_INTERCOM, DEVICE_TYPE_GATE

_LOGGER = logging.getLogger(__name__)


def _is_valid_intercom(device: dict) -> bool:
    """Check if device is a valid intercom with open door capability."""
    if device.get('device_type') not in [DEVICE_TYPE_INTERCOM, DEVICE_TYPE_GATE]:
        return False
        
    capabilities = device.get('capabilities', [])
    for capability in capabilities:
        if capability.get('name') == 'open_door' and capability.get('setup') is True:
            return True
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hartkey buttons from config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    _LOGGER.debug("Setting up buttons with coordinator data: %s", coordinator.data)
    
    buttons = []
    
    if not coordinator.data or "devices" not in coordinator.data:
        _LOGGER.warning("No devices found in coordinator data")
        return
    
    devices = coordinator.data["devices"]
    
    if not devices:
        _LOGGER.warning("Devices list is empty")
        return
    
    _LOGGER.info("Processing %d devices for buttons", len(devices))
    
    for device in devices:
        if not isinstance(device, dict):
            _LOGGER.warning("Unexpected device type: %s, value: %s", type(device), device)
            continue
            
        device_id = device.get('id')
        device_name = device.get('description') or device.get('name_by_user') or device.get('name_by_company') or f'Домофон {device_id}'
        
        if _is_valid_intercom(device):
            _LOGGER.debug("Creating button for valid device: %s (ID: %s, Type: %s)", device_name, device_id, device.get('device_type'))
            buttons.append(HartkeyOpenButton(coordinator, device))
        else:
            _LOGGER.debug("Skipping device %s - not a valid intercom/gate or no open capability", device_id)
    
    _LOGGER.info("Created %d button entities", len(buttons))
    async_add_entities(buttons, update_before_add=True)


class HartkeyOpenButton(CoordinatorEntity, ButtonEntity):
    """Representation of a Hartkey Open Door button."""

    def __init__(self, coordinator, device: dict) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.device = device
        
        self.device_id = device.get('id')
        if not self.device_id:
            _LOGGER.error("Device ID is missing for device: %s", device)
            return
            
        device_name = device.get('description')
        if not device_name:
            device_name = device.get('name_by_user') or device.get('name_by_company') or f'Домофон {self.device_id}'
        
        device_type = device.get('device_type', 'intercom')
        
        if device_type == 'gate':
            self._attr_icon = "mdi:gate"
            self._attr_name = f"{device_name} - Открыть ворота"
        else:
            self._attr_icon = "mdi:door-open"
            self._attr_name = f"{device_name} - Открыть дверь"
        
        self._attr_unique_id = f"{self.device_id}_open"
        
        _LOGGER.debug("Creating button: %s (%s)", device_name, self.device_id)
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self.device_id))},
            name=device_name,
            manufacturer="Hartkey",
            model=self._get_device_model_name(),
            sw_version=device.get("firmware_version"),
            serial_number=device.get("serial_number"),
        )

    def _get_device_model_name(self):
        """Get human readable device model name."""
        device_type = self.device.get('device_type')
        if device_type == 'intercom':
            return "Домофон"
        elif device_type == 'gate':
            return "Ворота"
        else:
            return device_type or "Устройство"

    async def async_press(self, **kwargs: Any) -> None:
        """Handle the button press."""
        if not self.device_id:
            _LOGGER.error("Device ID is missing")
            return
            
        headers = {
            "Authorization": f"Bearer {self.coordinator.bearer_token}",
            "Content-Type": "application/json"
        }
        
        url = API_URL_OPEN.format(intercom_id=self.device_id)
        _LOGGER.info("Sending POST command to: %s", url)
        
        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json={}) as response:
                        if response.status == 200:
                            _LOGGER.info(
                                "Successfully sent open command for %s",
                                self._attr_name
                            )
                            await self.coordinator.async_request_refresh()
                        else:
                            text = await response.text()
                            _LOGGER.error(
                                "Error sending command for %s: %s - %s",
                                self._attr_name, response.status, text
                            )
        except aiohttp.ClientError as err:
            _LOGGER.error("Client error sending command: %s", err)
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout sending command for %s", self._attr_name)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.device_id is not None
            and self.coordinator.data is not None
        )
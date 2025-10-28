"""Sensor platform for Hartkey integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN, ATTR_EVENT_TYPE, ATTR_RAISED_AT, ATTR_DEVICE_ID, 
    DEVICE_TYPE_INTERCOM, DEVICE_TYPE_GATE, ATTR_EVENT_TYPE_NAME, 
    ATTR_EVENT_MESSAGE, ATTR_USER_ID, ATTR_USER_AGENT, ATTR_RFID,
    EVENT_TYPE_NAMES
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hartkey sensors from config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    _LOGGER.debug("Setting up sensors with coordinator data: %s", coordinator.data)
    
    sensors = []
    
    if not coordinator.data or "devices" not in coordinator.data:
        _LOGGER.warning("No devices found in coordinator data")
        return
    
    devices = coordinator.data["devices"]
    
    if not devices:
        _LOGGER.warning("Devices list is empty")
        return
        
    _LOGGER.info("Processing %d devices for sensors", len(devices))
    
    for device in devices:
        if not isinstance(device, dict):
            _LOGGER.warning("Unexpected device type: %s, value: %s", type(device), device)
            continue
            
        device_id = device.get('id')
        if device_id and device.get('device_type') in [DEVICE_TYPE_INTERCOM, DEVICE_TYPE_GATE]:
            _LOGGER.debug("Creating sensor for device: %s (type: %s)", device_id, device.get('device_type'))
            sensors.append(HartkeyEventSensor(coordinator, device))
    
    _LOGGER.info("Created %d sensor entities", len(sensors))
    async_add_entities(sensors, update_before_add=True)


class HartkeyEventSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Hartkey Door Event sensor."""

    def __init__(self, coordinator, device: dict) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.device = device
        self.device_id = device.get('id')
        self.device_type = device.get('device_type', DEVICE_TYPE_INTERCOM)
        
        if not self.device_id:
            _LOGGER.error("Device ID is missing for device: %s", device)
            return

        device_name = device.get('description') or device.get('name_by_user') or device.get('name_by_company') or f'Домофон {self.device_id}'
        
        if self.device_type == DEVICE_TYPE_GATE:
            self._attr_name = f"{device_name} - Открытие ворот"
        else:
            self._attr_name = f"{device_name} - Открытие двери"
            
        self._attr_unique_id = f"{self.device_id}_last_open"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self.device_id))},
            name=device_name,
            manufacturer="Hartkey",
            model=self._get_device_model_name(),
            sw_version=device.get("firmware_version"),
            serial_number=device.get("serial_number"),
        )

        self._attr_icon = "mdi:key"
        self._state = "Никогда не открывалась"
        self._event_data = None
        self._last_updated = None

        self._update_state()

    def _get_device_model_name(self):
        """Get human readable device model name."""
        device_type = self.device.get('device_type')
        if device_type == DEVICE_TYPE_INTERCOM:
            return "Домофон"
        elif device_type == DEVICE_TYPE_GATE:
            return "Ворота"
        else:
            return device_type or "Устройство"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        attrs = {
            "last_updated": self._last_updated,
            "device_type": self.device_type,
        }
        
        if self._event_data:
            event_type = self._event_data.get("event_type")
            event_type_name = EVENT_TYPE_NAMES.get(event_type, event_type)
            
            attrs.update({
                ATTR_EVENT_TYPE: event_type,
                ATTR_EVENT_TYPE_NAME: event_type_name,
                ATTR_RAISED_AT: self._event_data.get("raised_at"),
                ATTR_DEVICE_ID: self._event_data.get("device_id"),
                ATTR_USER_ID: self._event_data.get("user_id"),
            })
            
            user_agent = self._event_data.get("user_agent")
            if user_agent:
                attrs[ATTR_USER_AGENT] = self._parse_user_agent(user_agent)
            
            if event_type == "rfid_open_local":
                rfid = self._event_data.get("rfid")
                if rfid:
                    attrs[ATTR_RFID] = rfid
            
            room_number = self._event_data.get("room_number")
            if room_number:
                attrs["room_number"] = room_number
                
        return attrs

    def _parse_user_agent(self, user_agent: str) -> str:
        """Parse user agent to human readable format."""
        if not user_agent:
            return "Неизвестно"
        
        if "Python" in user_agent and "aiohttp" in user_agent:
            return "Кнопка Home Assistant"
        
        if "android" in user_agent.lower():
            if "Key" in user_agent:
                return "Мобильное приложение Ключ"
            return "Мобильное приложение"
        
        if "ios" in user_agent.lower() or "iphone" in user_agent.lower():
            if "Key" in user_agent:
                return "Мобильное приложение Ключ (iOS)"
            return "Мобильное приложение (iOS)"
        
        return user_agent

    def _get_event_description(self, event_data: dict) -> str:
        """Get human readable description of the event."""
        event_type = event_data.get("event_type")
        user_agent = event_data.get("user_agent", "")
        
        if event_type == "api_open_remote":
            if "Python" in user_agent and "aiohttp" in user_agent:
                return "открыто кнопкой"
            elif "android" in user_agent.lower() or "ios" in user_agent.lower():
                return "открыто приложением"
            else:
                return "открыто удаленно"
        elif event_type == "rfid_open_local":
            return "открыто ключом"
        elif event_type == "face_open_remote":
            return "открыто по лицу"
        elif event_type == "pin_code_open_remote":
            return "открыто пин-кодом"
        elif event_type == "code_open_local":
            return "открыто кодом"
        elif event_type == "dtmf_open_local":
            return "открыто DTMF"
        else:
            return EVENT_TYPE_NAMES.get(event_type, "открыто")

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Updating sensor %s with new coordinator data", self.device_id)
        self._update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._update_state()
        _LOGGER.debug("Sensor %s added to HA", self.device_id)

    def _update_state(self):
        """Update sensor state from coordinator data."""
        self._last_updated = dt_util.now().strftime("%d.%m.%Y %H:%M:%S")
        
        if not self.coordinator.data or "events" not in self.coordinator.data:
            _LOGGER.debug("No events data in coordinator for sensor %s", self.device_id)
            return
            
        events_data = self.coordinator.data["events"]
        device_id_str = str(self.device_id)
        device_events = events_data.get(device_id_str, [])
        
        _LOGGER.debug("Found %d events for device %s", len(device_events), device_id_str)
        
        if not device_events:
            if events_data:
                self._state = "Никогда не открывалась"
                self._event_data = None
            return
            
        latest_event = None
        latest_time = None
        
        for event in device_events:
            if not isinstance(event, dict):
                continue
                
            event_time = self._parse_datetime(event.get("raised_at"))
            if not event_time:
                _LOGGER.debug("Could not parse time for event: %s", event)
                continue
                
            if latest_time is None or event_time > latest_time:
                latest_time = event_time
                latest_event = event
        
        if latest_event and latest_time:
            local_time = dt_util.as_local(latest_time)
            event_description = self._get_event_description(latest_event)
            
            self._state = f"{local_time.strftime('%d.%m.%Y %H:%M')} {event_description}"
            self._event_data = latest_event
            _LOGGER.info("Updated sensor %s: %s", self.device_id, self._state)
        else:
            self._state = "Никогда не открывалась"
            self._event_data = None
            _LOGGER.debug("No valid events found for device %s", device_id_str)

    def _parse_datetime(self, date_string):
        """Parse datetime string from API."""
        if not date_string:
            return None
            
        try:
            parsed = dt_util.parse_datetime(date_string)
            if parsed:
                return parsed.replace(tzinfo=dt_util.UTC)
                
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    dt = datetime.strptime(date_string, fmt)
                    return dt.replace(tzinfo=dt_util.UTC)
                except ValueError:
                    continue
                    
            _LOGGER.warning("Failed to parse datetime: %s", date_string)
            return None
                
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Failed to parse datetime %s: %s", date_string, err)
            return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.device_id is not None
            and self.coordinator.data is not None
        )
"""Data update coordinator for Hartkey."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import API_URL_DEVICES, API_URL_EVENTS, EVENT_TYPES, DEVICE_TYPE_INTERCOM, DEVICE_TYPE_GATE, DEFAULT_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class HartkeyDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Hartkey data."""

    def __init__(self, hass: HomeAssistant, bearer_token: str, update_interval: int = DEFAULT_UPDATE_INTERVAL) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Hartkey",
            update_interval=timedelta(minutes=update_interval),
        )
        self.bearer_token = bearer_token
        self.devices = []
        self._update_interval = update_interval
        self._last_successful_data = None

    async def _async_update_data(self):
        """Fetch data from API."""
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        
        _LOGGER.debug("Starting data update for Hartkey")
        
        try:
            devices = await self._fetch_devices(headers)
            self.devices = devices
            events = await self._fetch_events(headers, devices)
            
            result = {
                "devices": devices,
                "events": events
            }
            
            self._last_successful_data = result
            _LOGGER.debug("Coordinator update completed. Devices: %d, Events for devices: %d", 
                         len(devices), len(events))
                
            return result
                
        except aiohttp.ClientError as err:
            _LOGGER.warning("Network error during update: %s", err)
            if self._last_successful_data:
                _LOGGER.info("Using last successful data due to network error")
                return self._last_successful_data
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout during data update")
            if self._last_successful_data:
                _LOGGER.info("Using last successful data due to timeout")
                return self._last_successful_data
            raise UpdateFailed("Timeout communicating with API")
        except Exception as err:
            _LOGGER.exception("Unexpected error in coordinator")
            if self._last_successful_data:
                _LOGGER.info("Using last successful data due to unexpected error")
                return self._last_successful_data
            raise UpdateFailed(f"Unexpected error: {err}") from err

    async def _fetch_devices(self, headers):
        """Fetch devices from API."""
        async with async_timeout.timeout(10):
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL_DEVICES, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        _LOGGER.debug("Successfully fetched devices data")
                        return self._parse_devices(data)
                    elif response.status == 401:
                        raise UpdateFailed("Invalid authentication")
                    else:
                        text = await response.text()
                        _LOGGER.error("API error response: %s", text)
                        raise UpdateFailed(f"API error: {response.status}")

    async def _fetch_events(self, headers, devices):
        """Fetch events from API."""
        if not devices:
            _LOGGER.debug("No devices to fetch events for")
            return {}
            
        device_ids = []
        for device in devices:
            device_id = device.get('id')
            if device_id and device.get('device_type') in [DEVICE_TYPE_INTERCOM, DEVICE_TYPE_GATE]:
                device_ids.append(str(device_id))
                
        if not device_ids:
            _LOGGER.debug("No valid device IDs found for events")
            return {}
            
        _LOGGER.debug("Fetching events for %d device IDs", len(device_ids))
        
        end_time = dt_util.utcnow()
        start_time = end_time - timedelta(days=7)
        
        params = {
            "begin_raised_at": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_raised_at": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "device_ids": ",".join(device_ids),
            "event_types": ",".join(EVENT_TYPES),
            "sort_by": "raised_at",
            "sort_order": "desc",
            "offset": 0,
            "limit": 100
        }
        
        try:
            async with async_timeout.timeout(15):
                async with aiohttp.ClientSession() as session:
                    async with session.get(API_URL_EVENTS, headers=headers, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            _LOGGER.debug("Successfully fetched events data")
                            parsed_events = self._parse_events(data)
                            _LOGGER.debug("Parsed events for %d devices", len(parsed_events))
                            return parsed_events
                        elif response.status == 400:
                            error_data = await response.json()
                            _LOGGER.warning("API validation error for events: %s", error_data)
                            return {}
                        else:
                            text = await response.text()
                            _LOGGER.warning("Failed to fetch events: %s - %s", response.status, text)
                            return {}
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout fetching events")
            return {}
        except Exception as err:
            _LOGGER.warning("Error fetching events: %s", err)
            return {}

    def _parse_devices(self, data):
        """Parse devices from API response."""
        if not isinstance(data, dict):
            raise UpdateFailed(f"Expected dictionary response, got {type(data)}")
        
        devices = []
        
        if "data" in data and isinstance(data["data"], dict):
            data_content = data["data"]
            if "devices" in data_content and isinstance(data_content["devices"], list):
                devices = data_content["devices"]
        
        valid_devices = [
            device for device in devices 
            if isinstance(device, dict) and device.get('device_type') in [DEVICE_TYPE_INTERCOM, DEVICE_TYPE_GATE]
        ]
        
        _LOGGER.info("Found %d valid devices (intercom/gate)", len(valid_devices))
        return valid_devices

    def _parse_events(self, data):
        """Parse events from API response."""
        if not isinstance(data, dict):
            _LOGGER.warning("Expected dictionary for events, got %s", type(data))
            return {}
            
        events_by_device = {}
        
        try:
            events_list = []
            
            if "data" in data and isinstance(data["data"], dict):
                if "items" in data["data"] and isinstance(data["data"]["items"], list):
                    events_list = data["data"]["items"]
            
            _LOGGER.debug("Total events found in response: %d", len(events_list))
            
            event_count = 0
            for event in events_list:
                if isinstance(event, dict):
                    device_id = event.get("device_id")
                    if device_id:
                        device_id_str = str(device_id)
                        if device_id_str not in events_by_device:
                            events_by_device[device_id_str] = []
                        events_by_device[device_id_str].append(event)
                        event_count += 1
                        
            _LOGGER.debug("Successfully parsed %d events for %d devices", event_count, len(events_by_device))
                        
        except Exception as err:
            _LOGGER.error("Error parsing events: %s", err)
            
        return events_by_device
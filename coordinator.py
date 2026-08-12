"""Data update coordinator for Hartkey."""
from __future__ import annotations

import asyncio
import logging
import time
import json
import base64
from datetime import timedelta
from urllib.parse import urlparse

import aiohttp
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntryAuthFailed

from .const import (
    API_URL_DEVICES_INTERCOM, API_URL_DEVICES_BARRIER, API_URL_EVENTS, API_URL_CAMERAS,
    EVENT_TYPES, DEVICE_TYPE_INTERCOM, DEVICE_TYPE_GATE,
    DEFAULT_UPDATE_INTERVAL, TOKEN_REFRESH_BUFFER, CAMERAS_CACHE_TTL
)

_LOGGER = logging.getLogger(__name__)


class HartkeyDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Hartkey data."""

    def __init__(self, hass: HomeAssistant, bearer_token: str,
                 config_entry_id: str,
                 update_interval: int = DEFAULT_UPDATE_INTERVAL) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Hartkey",
            update_interval=timedelta(minutes=update_interval),
        )
        self.bearer_token = bearer_token
        self.config_entry_id = config_entry_id
        self.devices = []
        self._update_interval = update_interval
        self._last_successful_data = None

        # Camera caching
        self._cached_cameras_info = None
        self._cameras_last_update = None
        self._cameras_lock = asyncio.Lock()

        # Mapping from camera_id to device_id, device_name and device_type
        self.camera_to_device_id = {}
        self.camera_to_device_name = {}
        self.camera_to_device_type = {}

    async def _async_update_data(self):
        """Fetch data from API."""
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        _LOGGER.debug("Starting data update for Hartkey")
        try:
            devices = await self._fetch_devices(headers)
            self.devices = devices
            events = await self._fetch_events(headers, devices)
            result = {"devices": devices, "events": events}
            self._last_successful_data = result
            _LOGGER.debug("Coordinator update completed. Devices: %d, Events for devices: %d",
                         len(devices), len(events))
            return result
        except ConfigEntryAuthFailed:
            raise
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
        """Fetch intercoms and gates/barriers from API, merge, and update camera mapping."""
        intercoms = await self._fetch_device_list(headers, API_URL_DEVICES_INTERCOM, DEVICE_TYPE_INTERCOM)

        try:
            barriers = await self._fetch_device_list(headers, API_URL_DEVICES_BARRIER, DEVICE_TYPE_GATE)
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            # Ворота/шлагбаумы — не у всех аккаунтов, не роняем интеграцию из-за этого списка
            _LOGGER.warning("Could not fetch gates/barriers, continuing with intercoms only: %s", err)
            barriers = []

        devices = intercoms + barriers

        # Update mapping from camera_id to device_id, device_name and device_type
        for device in devices:
            camera_id = device.get("camera_id")
            device_id = device.get("id")
            if camera_id and device_id:
                self.camera_to_device_id[camera_id] = str(device_id)
                device_name = device.get("description") or device.get("name_by_user") or device.get("name_by_company") or f"Device {device_id}"
                self.camera_to_device_name[camera_id] = device_name
                self.camera_to_device_type[camera_id] = device.get("device_type", DEVICE_TYPE_INTERCOM)

        return devices

    async def _fetch_device_list(self, headers, url, device_type):
        """Fetch a single device list (intercoms or gates/barriers).

        device_type is force-applied to every returned item instead of trusting
        the API's own field: пешеходные калитки, например, приходят с /intercom
        как device_type=intercom, хотя это тоже вид ворот. Какой это тип
        устройства, надёжнее определяется тем, какой endpoint мы вызвали,
        а не значением из ответа.
        """
        async with async_timeout.timeout(10):
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        _LOGGER.debug("Successfully fetched device list from %s", url)
                        return self._parse_devices(data, device_type)
                    elif response.status == 401:
                        raise ConfigEntryAuthFailed("Invalid authentication")
                    else:
                        text = await response.text()
                        _LOGGER.error("API error response from %s: %s - %s", url, response.status, text)
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
                        elif response.status == 401:
                            raise ConfigEntryAuthFailed("Invalid authentication")
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
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            _LOGGER.warning("Error fetching events: %s", err)
            return {}

    def _parse_devices(self, data, device_type):
        """Parse devices from API response and tag them with device_type."""
        if not isinstance(data, dict):
            raise UpdateFailed(f"Expected dictionary response, got {type(data)}")

        devices = []

        if "data" in data and isinstance(data["data"], dict):
            data_content = data["data"]
            if "devices" in data_content and isinstance(data_content["devices"], list):
                devices = data_content["devices"]

        valid_devices = []
        for device in devices:
            if not isinstance(device, dict):
                continue
            device["device_type"] = device_type
            valid_devices.append(device)

        _LOGGER.info("Found %d valid %s devices", len(valid_devices), device_type)
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

    # --- Camera methods -------------------------------------------------

    def _decode_jwt_payload(self, token: str) -> dict:
        """Decode JWT payload without signature verification."""
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return {}
            payload = parts[1]
            # Add padding if needed
            payload += '=' * (4 - len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload)
            return json.loads(decoded)
        except Exception as err:
            _LOGGER.debug("Failed to decode JWT: %s", err)
            return {}

    async def _fetch_cameras(self) -> list[dict]:
        """Fetch cameras from API, extract tokens."""
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        params = {"limit": 100, "offset": 0}
        async with async_timeout.timeout(15):
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL_CAMERAS, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        _LOGGER.debug("Cameras API response type: %s", type(data))

                        cameras = []
                        if isinstance(data, dict):
                            inner = data.get("data")
                            if isinstance(inner, dict):
                                items = inner.get("items", [])
                            elif isinstance(inner, list):
                                items = inner
                            else:
                                items = data.get("items", [])
                        elif isinstance(data, list):
                            items = data
                        else:
                            items = []

                        for cam in items:
                            if not isinstance(cam, dict):
                                continue
                            streamer_token = cam.get("streamer_token")
                            if streamer_token:
                                payload = self._decode_jwt_payload(streamer_token)
                                cam["streamer_token_exp"] = payload.get("exp")
                            # Screenshot токен больше не нужен, но сохраняем без обработки
                            cameras.append(cam)
                        return cameras
                    elif response.status == 401:
                        raise ConfigEntryAuthFailed("Invalid authentication")
                    else:
                        text = await response.text()
                        raise UpdateFailed(f"Error fetching cameras: {response.status} - {text}")

    async def get_cameras_info(self) -> list[dict]:
        """Get cached camera info, refresh if stale."""
        async with self._cameras_lock:
            now = time.time()
            if (self._cached_cameras_info is not None and
                self._cameras_last_update is not None and
                (now - self._cameras_last_update) < CAMERAS_CACHE_TTL):
                return self._cached_cameras_info

            try:
                self._cached_cameras_info = await self._fetch_cameras()
                self._cameras_last_update = now
            except Exception as err:
                _LOGGER.error("Error fetching cameras: %s", err)
                if self._cached_cameras_info is None:
                    self._cached_cameras_info = []
                    self._cameras_last_update = now

            return self._cached_cameras_info

    def clear_cached_cameras_info(self):
        """Force refresh of camera info on next request."""
        self._cached_cameras_info = None
        self._cameras_last_update = None

    async def get_camera_stream_url(self, camera_id: str) -> str | None:
        """Generate streaming URL for a camera with buffering params."""
        cameras = await self.get_cameras_info()
        for cam in cameras:
            if cam.get("id") == camera_id:
                streamer_token = cam.get("streamer_token")
                streamer_url = cam.get("streamer_url")
                if not streamer_token or not streamer_url:
                    return None

                # Проверка срока действия токена
                exp = cam.get("streamer_token_exp")
                if exp and (exp - time.time()) < TOKEN_REFRESH_BUFFER:
                    self.clear_cached_cameras_info()
                    cameras = await self.get_cameras_info()
                    for cam2 in cameras:
                        if cam2.get("id") == camera_id:
                            streamer_token = cam2.get("streamer_token")
                            streamer_url = cam2.get("streamer_url")
                            break
                    if not streamer_token:
                        return None

                parsed = urlparse(streamer_url)
                netloc = parsed.netloc
                # Добавляем параметры для плавного HLS
                url = (
                    f"https://{netloc}/stream/{camera_id}/live.mp4"
                    "?mp4-fragment-length=1&mp4-use-speed=1&mp4-afiller=1"
                    f"&token={streamer_token}"
                )
                return url
        return None

    def get_device_id_for_camera(self, camera_id: str) -> str | None:
        """Return device ID associated with given camera ID."""
        return self.camera_to_device_id.get(camera_id)

    def get_device_name_for_camera(self, camera_id: str) -> str | None:
        """Return device name associated with given camera ID."""
        return self.camera_to_device_name.get(camera_id)

    def get_device_type_for_camera(self, camera_id: str) -> str | None:
        """Return device type associated with given camera ID."""
        return self.camera_to_device_type.get(camera_id)
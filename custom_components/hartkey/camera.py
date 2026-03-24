"""Camera platform for Hartkey integration."""
from __future__ import annotations

import logging

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DEVICE_TYPE_INTERCOM, DEVICE_TYPE_GATE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hartkey cameras from config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Get cameras
    cameras = await coordinator.get_cameras_info()
    if not cameras:
        _LOGGER.debug("No cameras found")
        return

    # Get devices to find mapping
    devices = coordinator.data.get("devices", []) if coordinator.data else []
    # Build mapping from camera_id to device
    camera_to_device = {}
    for device in devices:
        camera_id = device.get("camera_id")
        if camera_id:
            camera_to_device[camera_id] = device

    entities = []
    for camera in cameras:
        camera_id = camera.get("id")
        if not camera_id:
            continue

        device = camera_to_device.get(camera_id)
        if not device:
            _LOGGER.warning("No device found for camera %s, skipping", camera_id)
            continue

        device_id = device.get("id")
        device_name = device.get("description") or device.get("name_by_user") or device.get("name_by_company") or f"Device {device_id}"
        device_type = device.get("device_type", DEVICE_TYPE_INTERCOM)

        entities.append(HartkeyCamera(coordinator, camera, device_id, device_name, device_type))

    async_add_entities(entities)
    _LOGGER.info("Added %d camera entities", len(entities))


class HartkeyCamera(CoordinatorEntity, Camera):
    """Representation of a Hartkey camera."""

    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, coordinator, camera_info: dict, device_id: str, device_name: str, device_type: str) -> None:
        """Initialize the camera."""
        super().__init__(coordinator)
        Camera.__init__(self)
        self.camera_id = camera_info.get("id")
        self.camera_title = camera_info.get("title", f"Camera {self.camera_id}")

        self._attr_name = device_name
        self._attr_unique_id = f"{self.camera_id}_camera"

        # Determine model and icon based on device type
        if device_type == DEVICE_TYPE_GATE:
            model = "Ворота"
            self._attr_icon = "mdi:gate"
        else:
            model = "Домофон"
            self._attr_icon = "mdi:doorbell-video"

        # Use the same identifiers as button/sensor to group under one device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_id))},
            name=device_name,
            manufacturer="Hartkey",
            model=model,
        )
        _LOGGER.debug("Initialized camera: %s (device_id: %s, model: %s)", device_name, device_id, model)

    async def stream_source(self) -> str | None:
        """Return the stream source."""
        url = await self.coordinator.get_camera_stream_url(self.camera_id)
        if url:
            _LOGGER.debug("Stream URL for %s: %s", self.camera_title, url)
        else:
            _LOGGER.warning("Could not get stream URL for camera %s", self.camera_title)
        return url

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.data is not None
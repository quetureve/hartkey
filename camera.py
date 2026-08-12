"""Camera platform for Hartkey integration."""
from __future__ import annotations

import asyncio
import logging
import time

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

    cameras = await coordinator.get_cameras_info()
    if not cameras:
        _LOGGER.debug("No cameras found")
        return

    entities = []
    for camera in cameras:
        camera_id = camera.get("id")
        if not camera_id:
            continue

        device_id = coordinator.get_device_id_for_camera(camera_id)
        if not device_id:
            _LOGGER.warning("No device found for camera %s, skipping", camera_id)
            continue

        device_name = coordinator.get_device_name_for_camera(camera_id) or f"Device {device_id}"
        device_type = coordinator.get_device_type_for_camera(camera_id) or DEVICE_TYPE_INTERCOM

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

        # Кэш для превью
        self._cached_image: bytes | None = None
        self._cached_image_time: float | None = None

        self._attr_name = device_name
        self._attr_unique_id = f"{self.camera_id}_camera"

        if device_type == DEVICE_TYPE_GATE:
            model = "Ворота"
            self._attr_icon = "mdi:gate"
        else:
            model = "Домофон"
            self._attr_icon = "mdi:doorbell-video"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_id))},
            name=device_name,
            manufacturer="Hartkey",
            model=model,
        )
        _LOGGER.debug("Initialized camera: %s (device: %s, model: %s)", device_name, device_id, model)

    async def stream_source(self) -> str | None:
        """Return the stream source (MP4)."""
        url = await self.coordinator.get_camera_stream_url(self.camera_id)
        if url:
            _LOGGER.debug("Stream URL for %s: %s", self.camera_title, url)
        else:
            _LOGGER.warning("Could not get stream URL for camera %s", self.camera_title)
        return url

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        """Return a still image from the live stream, cached for 30 seconds."""
        # Если уже есть свежий кэш – отдаём его
        now = time.time()
        if self._cached_image and self._cached_image_time and (now - self._cached_image_time < 30):
            return self._cached_image

        stream_url = await self.stream_source()
        if not stream_url:
            return None

        # Захват одного кадра с помощью ffmpeg
        cmd = [
            "ffmpeg",
            "-y",                     # overwrite output
            "-i", stream_url,
            "-vframes", "1",          # только один кадр
            "-f", "image2pipe",
            "-vcodec", "mjpeg",       # JPEG в stdout
            "-"
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

            if proc.returncode == 0 and stdout:
                self._cached_image = stdout
                self._cached_image_time = now
                _LOGGER.debug("Captured preview frame for %s (%d bytes)", self.camera_title, len(stdout))
                return self._cached_image
            else:
                _LOGGER.warning("ffmpeg failed for %s: %s", self.camera_title, stderr.decode()[:200] if stderr else "no output")
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout capturing preview for %s", self.camera_title)
        except Exception as err:
            _LOGGER.warning("Error capturing preview for %s: %s", self.camera_title, err)

        # Возвращаем последний удачный кадр, даже если устарел
        return self._cached_image

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.data is not None
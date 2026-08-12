"""The Hartkey integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, SERVICE_REFRESH_DATA
from .coordinator import HartkeyDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR, Platform.CAMERA]   # <-- добавлен Camera

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hartkey from a config entry."""
    
    _LOGGER.info("Setting up Hartkey integration")
    
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    _LOGGER.info("Using update interval: %d minutes", update_interval)
    
    coordinator = HartkeyDataUpdateCoordinator(
        hass, 
        bearer_token=entry.data["bearer_token"],
        update_interval=update_interval,
        config_entry_id=entry.entry_id
    )
    
    await coordinator.async_config_entry_first_refresh()
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    entry.async_on_unload(entry.add_update_listener(update_listener))

    async def async_handle_refresh_data(call: ServiceCall) -> None:
        """Force-refresh one Hartkey account (by entity_id) or all of them."""
        entity_id = call.data.get("entity_id")

        if not entity_id:
            for coord in hass.data.get(DOMAIN, {}).values():
                await coord.async_request_refresh()
            return

        ent_reg = er.async_get(hass)
        entity_entry = ent_reg.async_get(entity_id)
        target = None
        if entity_entry and entity_entry.config_entry_id:
            target = hass.data.get(DOMAIN, {}).get(entity_entry.config_entry_id)

        if target is None:
            _LOGGER.warning("refresh_data: не найден координатор Hartkey для %s", entity_id)
            return

        await target.async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_DATA):
        hass.services.async_register(DOMAIN, SERVICE_REFRESH_DATA, async_handle_refresh_data)
    
    _LOGGER.info("Hartkey integration setup completed successfully")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Hartkey integration")
    
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH_DATA)
        
    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    _LOGGER.info("Updating Hartkey integration options")
    await hass.config_entries.async_reload(entry.entry_id)
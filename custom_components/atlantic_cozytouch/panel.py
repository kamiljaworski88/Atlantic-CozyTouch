"""Auto-registered read-only Atlantic monitor panel, no YAML or HA file writes."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

PANEL_PATH = "atlantic-monitor"
ASSET_URL = "/atlantic-cozytouch-assets/panel.js"


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Expose bundled frontend panel; do not mutate Lovelace dashboards."""
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(ASSET_URL, str(Path(__file__).parent / "www" / "panel.js"), False)]
        )
    except ValueError:
        # A previously registered static path survives a config-entry reload.
        pass
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="atlantic-cozytouch-monitor",
        frontend_url_path=PANEL_PATH,
        module_url=ASSET_URL,
        sidebar_title="PC Atlantic",
        sidebar_icon="mdi:heat-pump",
        require_admin=False,
        config_panel_domain="atlantic_cozytouch",
    )


def async_remove_panel(hass: HomeAssistant) -> None:
    """Remove only our own sidebar panel."""
    frontend.async_remove_panel(hass, PANEL_PATH)

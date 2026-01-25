"""
Settings routes for NomadNet WebUI

Provides a form-based settings interface instead of raw config file editing.
Settings are grouped by section and indicate whether they require a restart.
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

import RNS
from RNS.vendor.configobj import ConfigObj

router = APIRouter()


def _get_current_settings(nomad_app):
    """Extract current settings from the app and config"""
    config = nomad_app.config
    peer_settings = nomad_app.peer_settings

    settings = {
        # Runtime settings (can change without restart)
        "runtime": {
            "display_name": peer_settings.get("display_name", "Anonymous Peer"),
            "propagation_node": peer_settings.get("propagation_node"),
            "last_announce": peer_settings.get("last_announce"),
            "last_lxmf_sync": peer_settings.get("last_lxmf_sync", 0),
        },

        # Client settings
        "client": {
            "enable_client": config.get("client", {}).get("enable_client", "yes"),
            "downloads_path": config.get("client", {}).get("downloads_path", "~/Downloads"),
            "announce_at_start": config.get("client", {}).get("announce_at_start", "yes"),
            "try_propagation_on_send_fail": config.get("client", {}).get("try_propagation_on_send_fail", "yes"),
            "periodic_lxmf_sync": config.get("client", {}).get("periodic_lxmf_sync", "yes"),
            "lxmf_sync_interval": config.get("client", {}).get("lxmf_sync_interval", "360"),
            "lxmf_sync_limit": config.get("client", {}).get("lxmf_sync_limit", "8"),
            "required_stamp_cost": config.get("client", {}).get("required_stamp_cost", "None"),
            "accept_invalid_stamps": config.get("client", {}).get("accept_invalid_stamps", "False"),
            "max_accepted_size": config.get("client", {}).get("max_accepted_size", "500"),
            "compact_announce_stream": config.get("client", {}).get("compact_announce_stream", "yes"),
            "notify_on_new_message": config.get("client", {}).get("notify_on_new_message", "yes"),
        },

        # Node settings
        "node": {
            "enable_node": config.get("node", {}).get("enable_node", "no"),
            "node_name": config.get("node", {}).get("node_name", "None"),
            "disable_propagation": config.get("node", {}).get("disable_propagation", "yes"),
            "announce_interval": config.get("node", {}).get("announce_interval", "360"),
            "announce_at_start": config.get("node", {}).get("announce_at_start", "yes"),
            "propagation_cost": config.get("node", {}).get("propagation_cost", "16"),
            "max_transfer_size": config.get("node", {}).get("max_transfer_size", "256"),
            "max_sync_size": config.get("node", {}).get("max_sync_size", "10240"),
            "message_storage_limit": config.get("node", {}).get("message_storage_limit", "2000"),
            "max_peers": config.get("node", {}).get("max_peers", ""),
            "pages_path": config.get("node", {}).get("pages_path", ""),
            "files_path": config.get("node", {}).get("files_path", ""),
        },

        # Logging settings
        "logging": {
            "loglevel": config.get("logging", {}).get("loglevel", "4"),
            "destination": config.get("logging", {}).get("destination", "file"),
        },

        # WebUI settings
        "webui": {
            "bind": config.get("webui", {}).get("bind", "127.0.0.1"),
            "port": config.get("webui", {}).get("port", "8282"),
            "password": config.get("webui", {}).get("password", ""),
        },
    }

    return settings


def _save_config_value(nomad_app, section, key, value):
    """Save a single config value to the config file"""
    if section not in nomad_app.config:
        nomad_app.config[section] = {}

    nomad_app.config[section][key] = value
    nomad_app.config.write()
    RNS.log(f"WebUI: Saved config [{section}] {key} = {value}", RNS.LOG_NOTICE)


@router.get("/", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Main settings page"""
    templates = request.app.state.templates
    nomad_app = request.app.state.nomad_app

    settings = _get_current_settings(nomad_app)

    # Get propagation node info for display
    pn_hash = nomad_app.get_default_propagation_node()
    pn_display = None
    if pn_hash:
        pn_display = {
            "hash": pn_hash.hex(),
            "name": nomad_app.directory.display_name(pn_hash)
        }

    # Get stats
    stats = {
        "node_connects": nomad_app.peer_settings.get("node_connects", 0),
        "served_page_requests": nomad_app.peer_settings.get("served_page_requests", 0),
        "served_file_requests": nomad_app.peer_settings.get("served_file_requests", 0),
    }

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings,
        "propagation_node": pn_display,
        "stats": stats,
        "config_path": nomad_app.configpath,
        "identity_hash": nomad_app.identity.hexhash if nomad_app.identity else None,
        "lxmf_hash": nomad_app.lxmf_destination.hexhash if nomad_app.lxmf_destination else None,
    })


@router.post("/runtime/display_name")
async def update_display_name(request: Request, display_name: str = Form(...)):
    """Update display name (runtime, no restart needed)"""
    nomad_app = request.app.state.nomad_app

    try:
        new_name = display_name.strip()
        if new_name:
            nomad_app.set_display_name(new_name)
            RNS.log(f"WebUI: Updated display name to '{new_name}'", RNS.LOG_NOTICE)
    except Exception as e:
        RNS.log(f"WebUI: Error updating display name: {e}", RNS.LOG_ERROR)

    return RedirectResponse("/settings?saved=display_name", status_code=302)


@router.post("/runtime/announce")
async def trigger_announce(request: Request):
    """Trigger an immediate peer announce"""
    nomad_app = request.app.state.nomad_app

    try:
        nomad_app.announce_now()
        RNS.log("WebUI: Triggered peer announce", RNS.LOG_NOTICE)
    except Exception as e:
        RNS.log(f"WebUI: Error triggering announce: {e}", RNS.LOG_ERROR)

    return RedirectResponse("/settings?announced=1", status_code=302)


@router.post("/client")
async def update_client_settings(
    request: Request,
    announce_at_start: str = Form("no"),
    try_propagation_on_send_fail: str = Form("no"),
    periodic_lxmf_sync: str = Form("no"),
    lxmf_sync_interval: str = Form("360"),
    lxmf_sync_limit: str = Form("8"),
    compact_announce_stream: str = Form("no"),
    notify_on_new_message: str = Form("no"),
    max_accepted_size: str = Form("500"),
    required_stamp_cost: str = Form("None"),
):
    """Update client settings (requires restart)"""
    nomad_app = request.app.state.nomad_app

    try:
        if "client" not in nomad_app.config:
            nomad_app.config["client"] = {}

        nomad_app.config["client"]["announce_at_start"] = announce_at_start
        nomad_app.config["client"]["try_propagation_on_send_fail"] = try_propagation_on_send_fail
        nomad_app.config["client"]["periodic_lxmf_sync"] = periodic_lxmf_sync
        nomad_app.config["client"]["lxmf_sync_interval"] = lxmf_sync_interval
        nomad_app.config["client"]["lxmf_sync_limit"] = lxmf_sync_limit
        nomad_app.config["client"]["compact_announce_stream"] = compact_announce_stream
        nomad_app.config["client"]["notify_on_new_message"] = notify_on_new_message
        nomad_app.config["client"]["max_accepted_size"] = max_accepted_size
        nomad_app.config["client"]["required_stamp_cost"] = required_stamp_cost

        nomad_app.config.write()
        RNS.log("WebUI: Saved client settings", RNS.LOG_NOTICE)

    except Exception as e:
        RNS.log(f"WebUI: Error saving client settings: {e}", RNS.LOG_ERROR)

    return RedirectResponse("/settings?saved=client&restart=1", status_code=302)


@router.post("/node")
async def update_node_settings(
    request: Request,
    enable_node: str = Form("no"),
    node_name: str = Form("None"),
    disable_propagation: str = Form("yes"),
    announce_interval: str = Form("360"),
    node_announce_at_start: str = Form("yes"),
    propagation_cost: str = Form("16"),
    max_transfer_size: str = Form("256"),
    max_sync_size: str = Form("10240"),
    message_storage_limit: str = Form("2000"),
):
    """Update node settings (requires restart)"""
    nomad_app = request.app.state.nomad_app

    try:
        if "node" not in nomad_app.config:
            nomad_app.config["node"] = {}

        nomad_app.config["node"]["enable_node"] = enable_node
        nomad_app.config["node"]["node_name"] = node_name if node_name.strip() else "None"
        nomad_app.config["node"]["disable_propagation"] = disable_propagation
        nomad_app.config["node"]["announce_interval"] = announce_interval
        nomad_app.config["node"]["announce_at_start"] = node_announce_at_start
        nomad_app.config["node"]["propagation_cost"] = propagation_cost
        nomad_app.config["node"]["max_transfer_size"] = max_transfer_size
        nomad_app.config["node"]["max_sync_size"] = max_sync_size
        nomad_app.config["node"]["message_storage_limit"] = message_storage_limit

        nomad_app.config.write()
        RNS.log("WebUI: Saved node settings", RNS.LOG_NOTICE)

    except Exception as e:
        RNS.log(f"WebUI: Error saving node settings: {e}", RNS.LOG_ERROR)

    return RedirectResponse("/settings?saved=node&restart=1", status_code=302)


@router.post("/logging")
async def update_logging_settings(
    request: Request,
    loglevel: str = Form("4"),
):
    """Update logging settings (requires restart)"""
    nomad_app = request.app.state.nomad_app

    try:
        if "logging" not in nomad_app.config:
            nomad_app.config["logging"] = {}

        nomad_app.config["logging"]["loglevel"] = loglevel
        nomad_app.config.write()
        RNS.log(f"WebUI: Saved logging settings (loglevel={loglevel})", RNS.LOG_NOTICE)

    except Exception as e:
        RNS.log(f"WebUI: Error saving logging settings: {e}", RNS.LOG_ERROR)

    return RedirectResponse("/settings?saved=logging&restart=1", status_code=302)


@router.post("/webui")
async def update_webui_settings(
    request: Request,
    bind: str = Form("127.0.0.1"),
    port: str = Form("8282"),
    password: str = Form(""),
):
    """Update WebUI settings (requires restart)"""
    nomad_app = request.app.state.nomad_app

    try:
        if "webui" not in nomad_app.config:
            nomad_app.config["webui"] = {}

        nomad_app.config["webui"]["bind"] = bind
        nomad_app.config["webui"]["port"] = port
        if password:
            nomad_app.config["webui"]["password"] = password

        nomad_app.config.write()
        RNS.log("WebUI: Saved webui settings", RNS.LOG_NOTICE)

    except Exception as e:
        RNS.log(f"WebUI: Error saving webui settings: {e}", RNS.LOG_ERROR)

    return RedirectResponse("/settings?saved=webui&restart=1", status_code=302)

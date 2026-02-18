import logging

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse

import RNS
import LXMF
from nomadnet.Directory import DirectoryEntry

router = APIRouter()
logger = logging.getLogger(__name__)


def _normalize_hash(source_hash):
    """Ensure source_hash is bytes for directory lookups"""
    if isinstance(source_hash, bytes):
        return source_hash
    if isinstance(source_hash, str):
        try:
            return bytes.fromhex(source_hash)
        except ValueError:
            return source_hash.encode('latin-1')
    return source_hash


def _resolve_display_name(app_data, source_hash, directory=None):
    """Try multiple strategies to resolve a display name from announce data"""
    # Strategy 1: Check directory entries directly (most reliable)
    if directory:
        try:
            hash_bytes = _normalize_hash(source_hash)
            entry = directory.directory_entries.get(hash_bytes)
            if entry and entry.display_name:
                return entry.display_name
        except Exception:
            pass

    # Strategy 2: Parse LXMF app_data
    if app_data:
        try:
            if isinstance(app_data, str):
                app_data = app_data.encode('utf-8')
            name = LXMF.display_name_from_app_data(app_data)
            if name:
                return name
        except Exception:
            pass

    return None


def _get_csrf_token(request: Request) -> str:
    """Get CSRF token for the current session"""
    session_manager = request.app.state.session_manager
    session_token = request.cookies.get("webui_session")
    csrf_token = session_manager.get_csrf_token(session_token)
    return csrf_token or ""


@router.get("/", response_class=HTMLResponse)
async def network_index(request: Request):
    """Network status and announce stream"""
    templates = request.app.state.templates
    nomad_app = request.app.state.nomad_app

    # Get current announce stream
    announces = []
    if hasattr(nomad_app, 'directory') and nomad_app.directory:
        for entry in nomad_app.directory.announce_stream[:100]:
            timestamp, source_hash, app_data, announce_type = entry
            display_name = _resolve_display_name(app_data, source_hash, nomad_app.directory)

            # Use the announce hash directly - Conversation class handles LXMF internally
            hash_hex = source_hash.hex() if isinstance(source_hash, bytes) else source_hash

            announces.append({
                "timestamp": timestamp,
                "hash": hash_hex,
                "name": display_name,
                "type": announce_type
            })

    # Get interface stats if available
    interfaces = []
    try:
        import RNS
        for interface in RNS.Transport.interfaces:
            interfaces.append({
                "name": str(interface),
                "status": "Online" if interface.online else "Offline",
                "type": interface.__class__.__name__
            })
    except:
        pass

    return templates.TemplateResponse("network.html", {
        "request": request,
        "announces": announces,
        "interfaces": interfaces,
        "identity": nomad_app.identity.hexhash if nomad_app.identity else None,
        "csrf_token": _get_csrf_token(request),
    })


@router.get("/node/{node_hash}")
async def get_node_info(request: Request, node_hash: str):
    """Get detailed information about a node"""
    nomad_app = request.app.state.nomad_app

    try:
        # Convert hex hash to bytes
        hash_bytes = bytes.fromhex(node_hash)

        # Get info from directory
        directory = nomad_app.directory
        entry = directory.directory_entries.get(hash_bytes)

        # Check announce stream for display name if not in directory
        display_name = None
        node_type = "unknown"
        if entry:
            display_name = entry.display_name
            node_type = "node" if entry.hosts_node else "peer"

        # Look in announce stream for more info
        for announce in directory.announce_stream:
            timestamp, source_hash, app_data, announce_type = announce
            if source_hash == hash_bytes:
                if app_data and not display_name:
                    display_name = _resolve_display_name(app_data, source_hash, directory)
                node_type = announce_type
                break

        # Get identify setting
        identify_on_connect = directory.should_identify_on_connect(hash_bytes)

        # Get trust level
        trust_level = "unknown"
        if entry:
            if entry.trust_level == DirectoryEntry.TRUSTED:
                trust_level = "trusted"
            elif entry.trust_level == DirectoryEntry.UNTRUSTED:
                trust_level = "untrusted"
            else:
                trust_level = "unknown"

        # Get hops
        hops = RNS.Transport.hops_to(hash_bytes)
        if hops == RNS.Transport.PATHFINDER_M:
            hops_str = "Unknown"
        else:
            hops_str = f"{hops} hop{'s' if hops != 1 else ''}"

        return JSONResponse({
            "hash": node_hash,
            "display_name": display_name,
            "type": node_type,
            "identify_on_connect": identify_on_connect,
            "trust_level": trust_level,
            "hops": hops_str,
            "in_directory": entry is not None
        })

    except Exception as e:
        # Log full error server-side, return generic message to client
        logger.error(f"Error getting node info for {node_hash}: {e}", exc_info=True)
        return JSONResponse({"error": "Failed to retrieve node information"}, status_code=400)


@router.post("/node/{node_hash}/settings")
async def update_node_settings(request: Request, node_hash: str):
    """Update node settings (identify on connect, trust level, etc.)"""
    nomad_app = request.app.state.nomad_app

    try:
        # Parse JSON body
        body = await request.json()
        hash_bytes = bytes.fromhex(node_hash)
        directory = nomad_app.directory

        # Get or create directory entry
        entry = directory.directory_entries.get(hash_bytes)

        # Get display name from announce stream if needed
        display_name = body.get("display_name")
        if not display_name:
            for announce in directory.announce_stream:
                timestamp, source_hash, app_data, announce_type = announce
                if source_hash == hash_bytes and app_data:
                    display_name = _resolve_display_name(app_data, source_hash, directory)
                    break

        # Determine if this is a node (hosts pages) based on announce type
        hosts_node = False
        for announce in directory.announce_stream:
            timestamp, source_hash, app_data, announce_type = announce
            if source_hash == hash_bytes:
                hosts_node = announce_type in ("node", "pn")
                break

        # Get trust level from body or existing entry
        trust_level = DirectoryEntry.UNKNOWN
        if "trust_level" in body:
            tl = body["trust_level"]
            if tl == "trusted":
                trust_level = DirectoryEntry.TRUSTED
            elif tl == "untrusted":
                trust_level = DirectoryEntry.UNTRUSTED
        elif entry:
            trust_level = entry.trust_level

        # Get identify setting
        identify_on_connect = body.get("identify_on_connect", False)

        # Create or update entry
        new_entry = DirectoryEntry(
            hash_bytes,
            display_name=display_name,
            trust_level=trust_level,
            hosts_node=hosts_node,
            identify_on_connect=identify_on_connect
        )
        directory.remember(new_entry)

        RNS.log(f"WebUI: Updated node settings for {node_hash[:16]}... (identify={identify_on_connect})", RNS.LOG_NOTICE)

        return JSONResponse({
            "success": True,
            "identify_on_connect": identify_on_connect
        })

    except Exception as e:
        # Log full error server-side, return generic message to client
        RNS.log(f"WebUI: Error updating node settings: {e}", RNS.LOG_ERROR)
        logger.error(f"Error updating node settings for {node_hash}: {e}", exc_info=True)
        return JSONResponse({"error": "Failed to update node settings"}, status_code=400)

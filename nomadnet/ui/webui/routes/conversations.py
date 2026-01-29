import os
import logging
from datetime import datetime

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

import LXMF
from nomadnet.Directory import DirectoryEntry

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_csrf_token(request: Request) -> str:
    """Get CSRF token for the current session"""
    session_manager = request.app.state.session_manager
    session_token = request.cookies.get("webui_session")
    csrf_token = session_manager.get_csrf_token(session_token)
    return csrf_token or ""

# Expected hash length for RNS destination hashes (16 bytes = 32 hex chars)
HASH_LENGTH = 32


def _validate_hash(hash_str: str) -> bool:
    """
    Validate that a string is a valid RNS hash.

    Args:
        hash_str: Hex string to validate

    Returns:
        True if valid, False otherwise
    """
    if not hash_str or len(hash_str) != HASH_LENGTH:
        return False
    try:
        bytes.fromhex(hash_str)
        return True
    except ValueError:
        return False


# Trust level constants match DirectoryEntry
TRUST_ICONS = {
    DirectoryEntry.UNTRUSTED: ("✗", "untrusted"),
    DirectoryEntry.UNKNOWN: ("?", "unknown"),
    DirectoryEntry.TRUSTED: ("✓", "trusted"),
    DirectoryEntry.WARNING: ("⚠", "warning"),
}

# Message state icons
STATE_ICONS = {
    LXMF.LXMessage.DELIVERED: ("✓", "delivered"),
    LXMF.LXMessage.SENT: ("→", "sent"),
    LXMF.LXMessage.FAILED: ("✗", "failed"),
}


def _build_conversation_list(nomad_app, selected_hash=None):
    """Build conversation list with trust indicators"""
    import RNS
    from nomadnet.Conversation import Conversation

    conversations = []

    try:
        conv_list = Conversation.conversation_list(nomad_app)
    except Exception as e:
        RNS.log(f"WebUI: Error getting conversation list: {e}", RNS.LOG_ERROR)
        return conversations

    for source_hash, display_name, trust_level, sort_name, unread in conv_list:
        try:
            icon, trust_class = TRUST_ICONS.get(trust_level, ("?", "unknown"))
            is_selected = source_hash == selected_hash

            # Try to get a proper name, handling "Undefined" from old directory entries
            name = None

            # First check if we have a valid name from the conversation list
            if display_name and display_name != "Undefined":
                name = display_name

            # If no valid name, try to look it up from various sources
            if not name:
                try:
                    source_hash_bytes = bytes.fromhex(source_hash)

                    # Try 1: Identity app_data
                    app_data = RNS.Identity.recall_app_data(source_hash_bytes)
                    if app_data:
                        try:
                            name = LXMF.display_name_from_app_data(app_data)
                        except:
                            try:
                                name = app_data.decode('utf-8')
                            except:
                                pass

                    # Try 2: Check announce stream for this hash
                    if not name and hasattr(nomad_app, 'directory') and nomad_app.directory:
                        for entry in nomad_app.directory.announce_stream:
                            try:
                                timestamp, ann_hash, ann_data, ann_type = entry
                                ann_hash_hex = ann_hash.hex() if isinstance(ann_hash, bytes) else ann_hash
                                if ann_hash_hex == source_hash and ann_data:
                                    try:
                                        name = LXMF.display_name_from_app_data(ann_data)
                                    except:
                                        try:
                                            name = ann_data.decode('utf-8')
                                        except:
                                            pass
                                    if name:
                                        break
                            except:
                                continue

                    # If we found a name and the directory has "Undefined", update it
                    if name and (display_name == "Undefined" or not display_name):
                        existing_entry = nomad_app.directory.find(source_hash_bytes)
                        if existing_entry:
                            if existing_entry.display_name == "Undefined" or not existing_entry.display_name:
                                existing_entry.display_name = name
                                nomad_app.directory.save_to_disk()
                except:
                    pass

            # Final fallback to hash
            if not name:
                name = source_hash[:16] + "..."

            conversations.append({
                "hash": source_hash,
                "name": name,
                "unread": unread,
                "selected": is_selected,
                "trust_icon": icon,
                "trust_class": trust_class,
                "trust_level": trust_level,
            })
        except Exception as e:
            RNS.log(f"WebUI: Error processing conversation {source_hash[:16] if source_hash else 'unknown'}...: {e}", RNS.LOG_ERROR)
            continue

    return conversations


def _load_messages(nomad_app, conv_hash):
    """Load messages from a conversation"""
    import time
    import RNS
    from nomadnet.Conversation import Conversation

    messages = []

    # First try to recall identity directly
    source_hash_bytes = bytes.fromhex(conv_hash)
    identity = RNS.Identity.recall(source_hash_bytes)

    # If no identity, check if we have a path and try requesting
    if not identity:
        try:
            RNS.Transport.request_path(source_hash_bytes)
            # Wait up to 3 seconds for identity to become available
            wait_until = time.time() + 3.0
            while time.time() < wait_until:
                identity = RNS.Identity.recall(source_hash_bytes)
                if identity:
                    break
                time.sleep(0.2)
        except Exception:
            pass

    # Create the conversation - use initiator=True to create directory if needed
    conversation = Conversation(conv_hash, nomad_app, initiator=True)

    # Check if we can send (identity known)
    can_send = conversation.source_known

    for msg in conversation.messages:
        try:
            # Force load the message first
            if not msg.loaded:
                msg.load()

            if not msg.lxm:
                continue

            # Determine if outgoing (we sent it)
            is_outgoing = nomad_app.lxmf_destination.hash == msg.lxm.source_hash

            # Get delivery state for outgoing messages
            state_icon, state_class = "", ""
            if is_outgoing:
                state = msg.lxm.state
                state_icon, state_class = STATE_ICONS.get(state, ("", ""))

            # Format timestamp - use lxm timestamp for display, file mtime for sorting
            display_timestamp = msg.get_timestamp()
            timestamp = datetime.fromtimestamp(display_timestamp)
            # sort_timestamp is file modification time - unique and stable
            file_mtime = msg.sort_timestamp if hasattr(msg, 'sort_timestamp') else display_timestamp

            messages.append({
                "content": msg.get_content(),
                "title": msg.get_title(),
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M"),
                "sort_timestamp": file_mtime,
                "outgoing": is_outgoing,
                "state_icon": state_icon,
                "state_class": state_class,
                "hash": msg.get_hash().hex() if msg.get_hash() else "",
            })
        except Exception as e:
            RNS.log(f"WebUI: Error loading message: {e}", RNS.LOG_ERROR)
            continue

    # Sort by timestamp (oldest first) - use raw timestamp for stable ordering
    messages.sort(key=lambda m: m["sort_timestamp"])

    return messages, conversation, can_send


@router.get("/", response_class=HTMLResponse)
async def conversations_list(request: Request):
    """List all conversations"""
    import RNS

    templates = request.app.state.templates
    nomad_app = request.app.state.nomad_app

    conversations = []
    try:
        conversations = _build_conversation_list(nomad_app)
    except Exception as e:
        RNS.log(f"WebUI: Error building conversation list: {e}", RNS.LOG_ERROR)

    return templates.TemplateResponse("conversations.html", {
        "request": request,
        "conversations": conversations,
        "selected": None,
        "messages": [],
        "can_send": False,
        "csrf_token": _get_csrf_token(request),
    })


def _get_known_peers(nomad_app):
    """Get list of known peers from directory and announce stream"""
    known_peers = []
    seen_hashes = set()

    # Get from directory
    try:
        for entry in nomad_app.directory.directory_entries():
            hash_hex = entry.source_hash.hex()
            if hash_hex not in seen_hashes:
                seen_hashes.add(hash_hex)
                known_peers.append({
                    "hash": hash_hex,
                    "name": entry.display_name or hash_hex[:16] + "...",
                    "type": "directory"
                })
    except Exception:
        pass

    # Get from announce stream
    try:
        if hasattr(nomad_app, 'directory') and nomad_app.directory:
            for entry in nomad_app.directory.announce_stream[:50]:
                timestamp, source_hash, app_data, announce_type = entry
                hash_hex = source_hash.hex() if isinstance(source_hash, bytes) else source_hash

                if hash_hex not in seen_hashes:
                    seen_hashes.add(hash_hex)
                    display_name = None
                    if app_data:
                        try:
                            display_name = app_data.decode('utf-8')
                        except Exception:
                            pass
                    known_peers.append({
                        "hash": hash_hex,
                        "name": display_name or hash_hex[:16] + "...",
                        "type": announce_type
                    })
    except Exception:
        pass

    return known_peers


@router.get("/new", response_class=HTMLResponse)
async def new_conversation_form(request: Request):
    """Show new conversation form"""
    templates = request.app.state.templates
    nomad_app = request.app.state.nomad_app

    conversations = []
    known_peers = []
    try:
        conversations = _build_conversation_list(nomad_app)
        known_peers = _get_known_peers(nomad_app)
    except Exception:
        pass

    return templates.TemplateResponse("conversations.html", {
        "request": request,
        "conversations": conversations,
        "selected": None,
        "messages": [],
        "can_send": False,
        "show_new_form": True,
        "known_peers": known_peers,
        "csrf_token": _get_csrf_token(request),
    })


@router.post("/new")
async def create_conversation(
    request: Request,
    address: str = Form(...),
    name: str = Form("")
):
    """Create a new conversation"""
    from nomadnet.Conversation import Conversation

    nomad_app = request.app.state.nomad_app

    try:
        # Normalize address
        address = address.strip().lower()

        # Validate hash format and length
        if not _validate_hash(address):
            raise ValueError("Invalid hash format or length")

        # Add to directory if name provided
        if name.strip():
            entry = DirectoryEntry(
                bytes.fromhex(address),
                name.strip(),
                DirectoryEntry.UNKNOWN
            )
            nomad_app.directory.remember(entry)

        # Create conversation (initiator=True creates the directory)
        Conversation(address, nomad_app, initiator=True)

        # Broadcast new conversation event via WebSocket
        display_name = name.strip() if name.strip() else None
        if not display_name:
            # Try to get name from directory
            try:
                dir_entry = nomad_app.directory.find(bytes.fromhex(address))
                if dir_entry and dir_entry.display_name:
                    display_name = dir_entry.display_name
            except Exception:
                pass

        ws_manager = request.app.state.ws_manager
        ws_manager.broadcast_sync("conversation_created", {
            "hash": address,
            "display_name": display_name or address[:16] + "...",
        })

        return RedirectResponse(f"/conversations/{address}", status_code=302)

    except ValueError:
        # Invalid hex
        templates = request.app.state.templates
        conversations = _build_conversation_list(nomad_app)
        return templates.TemplateResponse("conversations.html", {
            "request": request,
            "conversations": conversations,
            "selected": None,
            "messages": [],
            "can_send": False,
            "show_new_form": True,
            "error": "Invalid address format. Must be a hex string.",
            "csrf_token": _get_csrf_token(request),
        })


@router.get("/{conv_hash}", response_class=HTMLResponse)
async def conversation_detail(request: Request, conv_hash: str):
    """View a specific conversation"""
    import RNS
    from fastapi.responses import JSONResponse

    # Handle "new" explicitly in case route ordering doesn't work
    if conv_hash == "new":
        return await new_conversation_form(request)

    templates = request.app.state.templates
    nomad_app = request.app.state.nomad_app

    # Validate hash parameter
    if not _validate_hash(conv_hash):
        return templates.TemplateResponse("conversations.html", {
            "request": request,
            "conversations": _build_conversation_list(nomad_app),
            "selected": None,
            "messages": [],
            "can_send": False,
            "error": "Invalid conversation hash format",
            "csrf_token": _get_csrf_token(request),
        })

    conversations = []
    messages = []
    selected_name = conv_hash[:16] + "..."
    trust_level = DirectoryEntry.UNKNOWN
    can_send = False

    try:
        from nomadnet.Conversation import Conversation as Conv

        # Check if this is a new conversation (doesn't exist yet)
        existing_convs = {c[0] for c in Conv.conversation_list(nomad_app)}
        is_new_conversation = conv_hash not in existing_convs

        # Load messages FIRST - this creates the conversation if it doesn't exist
        messages, conversation, can_send = _load_messages(nomad_app, conv_hash)

        # If this was a new conversation, broadcast WebSocket event
        if is_new_conversation:
            display_name = None
            try:
                dir_entry = nomad_app.directory.find(bytes.fromhex(conv_hash))
                if dir_entry and dir_entry.display_name:
                    display_name = dir_entry.display_name
            except Exception:
                pass

            ws_manager = request.app.state.ws_manager
            ws_manager.broadcast_sync("conversation_created", {
                "hash": conv_hash,
                "display_name": display_name or conv_hash[:16] + "...",
            })

        # Mark as read (after conversation exists)
        if nomad_app.conversation_is_unread(conv_hash):
            nomad_app.mark_conversation_read(conv_hash)
            # Remove unread file
            unread_path = nomad_app.conversationpath + "/" + conv_hash + "/unread"
            if os.path.isfile(unread_path):
                os.unlink(unread_path)
            # Update callback tracking so future messages are detected as new
            if hasattr(request.app.state, 'conversations_display'):
                request.app.state.conversations_display.mark_conversation_read(conv_hash)
            # Broadcast read status update via WebSocket
            ws_manager = request.app.state.ws_manager
            ws_manager.broadcast_sync("conversation_read", {
                "conversation_hash": conv_hash
            })
            # Also update unread count
            conv_list = Conv.conversation_list(nomad_app)
            unread_count = sum(1 for c in conv_list if c[4])
            ws_manager.broadcast_sync("unread_count", {"count": unread_count})

        # Now build conversation list (after conversation is created)
        conversations = _build_conversation_list(nomad_app, selected_hash=conv_hash)

        # Get selected conversation info
        for conv in conversations:
            if conv["selected"]:
                selected_name = conv["name"]
                trust_level = conv["trust_level"]
                break

    except Exception as e:
        RNS.log(f"WebUI: Error loading conversation {conv_hash[:16]}...: {e}", RNS.LOG_ERROR)

    return templates.TemplateResponse("conversations.html", {
        "request": request,
        "conversations": conversations,
        "selected": conv_hash,
        "selected_name": selected_name,
        "messages": messages,
        "can_send": can_send,
        "trust_level": trust_level,
        "csrf_token": _get_csrf_token(request),
    })


@router.post("/{conv_hash}/send")
async def send_message(
    request: Request,
    conv_hash: str,
    message: str = Form(...),
    title: str = Form("")
):
    """Send a message in a conversation"""
    import RNS
    from nomadnet.Conversation import Conversation

    nomad_app = request.app.state.nomad_app

    try:
        conversation = Conversation(conv_hash, nomad_app)
        content = message.strip()

        if content:
            result = conversation.send(content, title.strip())
            RNS.log(f"WebUI: Send message to {conv_hash[:16]}... result: {result}, source_known: {conversation.source_known}", RNS.LOG_NOTICE)

    except Exception as e:
        import RNS
        RNS.log(f"WebUI: Error sending message: {e}", RNS.LOG_ERROR)

    return RedirectResponse(f"/conversations/{conv_hash}", status_code=302)


@router.post("/sync")
async def trigger_sync(
    request: Request,
    limit: int = Form(5)
):
    """Trigger LXMF sync from propagation node"""
    import RNS
    import LXMF

    nomad_app = request.app.state.nomad_app

    try:
        # Check if sync is already in progress
        state = nomad_app.message_router.propagation_transfer_state
        if state != LXMF.LXMRouter.PR_IDLE and state < LXMF.LXMRouter.PR_COMPLETE:
            RNS.log("WebUI: Sync already in progress", RNS.LOG_DEBUG)
        else:
            nomad_app.request_lxmf_sync(limit=limit if limit > 0 else None)
            RNS.log(f"WebUI: Initiated LXMF sync with limit={limit}", RNS.LOG_NOTICE)
    except Exception as e:
        RNS.log(f"WebUI: Error triggering sync: {e}", RNS.LOG_ERROR)

    return RedirectResponse("/conversations", status_code=302)


@router.post("/sync/cancel")
async def cancel_sync(request: Request):
    """Cancel ongoing LXMF sync"""
    import RNS

    nomad_app = request.app.state.nomad_app

    try:
        nomad_app.cancel_lxmf_sync()
        RNS.log("WebUI: Cancelled LXMF sync", RNS.LOG_NOTICE)
    except Exception as e:
        RNS.log(f"WebUI: Error cancelling sync: {e}", RNS.LOG_ERROR)

    return RedirectResponse("/conversations", status_code=302)


@router.get("/sync/status")
async def sync_status(request: Request):
    """Get current sync status"""
    import LXMF
    from fastapi.responses import JSONResponse

    nomad_app = request.app.state.nomad_app

    try:
        status = nomad_app.get_sync_status()
        progress = nomad_app.get_sync_progress()
        state = nomad_app.message_router.propagation_transfer_state

        # Determine if sync is active
        is_syncing = state != LXMF.LXMRouter.PR_IDLE and state < LXMF.LXMRouter.PR_COMPLETE

        # Get propagation node info
        pn_hash = nomad_app.get_default_propagation_node()
        pn_name = None
        if pn_hash:
            pn_name = nomad_app.directory.display_name(pn_hash)

        return JSONResponse({
            "status": status,
            "progress": progress,
            "is_syncing": is_syncing,
            "propagation_node": pn_hash.hex() if pn_hash else None,
            "propagation_node_name": pn_name,
        })
    except Exception as e:
        # Log full error server-side, return generic message to client
        logger.error(f"Error getting sync status: {e}", exc_info=True)
        return JSONResponse({"status": "Error", "error": "Failed to retrieve sync status"}, status_code=500)


@router.post("/{conv_hash}/name")
async def update_display_name(
    request: Request,
    conv_hash: str,
    name: str = Form("")
):
    """Update display name for a conversation peer"""
    import RNS

    nomad_app = request.app.state.nomad_app

    try:
        source_hash_bytes = bytes.fromhex(conv_hash)
        new_name = name.strip() if name else None

        # Get or create directory entry
        existing_entry = nomad_app.directory.find(source_hash_bytes)

        if existing_entry:
            existing_entry.display_name = new_name if new_name else f"Peer {conv_hash[:8]}"
            nomad_app.directory.save_to_disk()
        else:
            # Create new entry with UNKNOWN trust
            entry = DirectoryEntry(
                source_hash_bytes,
                new_name if new_name else f"Peer {conv_hash[:8]}",
                DirectoryEntry.UNKNOWN
            )
            nomad_app.directory.remember(entry)

        RNS.log(f"WebUI: Updated display name for {conv_hash[:16]}... to '{new_name}'", RNS.LOG_NOTICE)

    except Exception as e:
        RNS.log(f"WebUI: Error updating display name: {e}", RNS.LOG_ERROR)

    return RedirectResponse(f"/conversations/{conv_hash}", status_code=302)


@router.post("/{conv_hash}/trust")
async def update_trust_level(
    request: Request,
    conv_hash: str,
    trust_level: int = Form(...)
):
    """Update trust level for a conversation peer"""
    import RNS

    nomad_app = request.app.state.nomad_app

    try:
        source_hash_bytes = bytes.fromhex(conv_hash)

        # Validate trust level
        valid_levels = [
            DirectoryEntry.UNTRUSTED,
            DirectoryEntry.UNKNOWN,
            DirectoryEntry.TRUSTED,
        ]
        if trust_level not in valid_levels:
            RNS.log(f"WebUI: Invalid trust level {trust_level}", RNS.LOG_ERROR)
            return RedirectResponse(f"/conversations/{conv_hash}", status_code=302)

        # Check if entry already exists
        existing_entry = nomad_app.directory.find(source_hash_bytes)

        RNS.log(f"WebUI: Trust update for {conv_hash[:16]}... existing={existing_entry is not None}, new_level={trust_level}", RNS.LOG_NOTICE)

        if existing_entry:
            # Update only the trust level on existing entry directly
            old_level = existing_entry.trust_level
            existing_entry.trust_level = trust_level
            # Save without calling remember() to avoid potential issues
            nomad_app.directory.save_to_disk()
            RNS.log(f"WebUI: Updated trust level for {conv_hash[:16]}... from {old_level} to {trust_level}", RNS.LOG_NOTICE)
        else:
            # Get display name - try from identity app_data first
            display_name = None
            app_data = RNS.Identity.recall_app_data(source_hash_bytes)
            if app_data:
                try:
                    import LXMF
                    display_name = LXMF.display_name_from_app_data(app_data)
                except:
                    try:
                        display_name = app_data.decode('utf-8')
                    except:
                        pass

            # Fallback to directory lookup
            if not display_name:
                display_name = nomad_app.directory.display_name(source_hash_bytes)

            # If still no name, use a placeholder that isn't "Undefined"
            if not display_name:
                display_name = f"Peer {conv_hash[:8]}"

            RNS.log(f"WebUI: Creating new directory entry for {conv_hash[:16]}... name={display_name}", RNS.LOG_NOTICE)

            entry = DirectoryEntry(
                source_hash_bytes,
                display_name,
                trust_level
            )
            nomad_app.directory.remember(entry)
            RNS.log(f"WebUI: Created directory entry for {conv_hash[:16]}...", RNS.LOG_NOTICE)

    except Exception as e:
        import traceback
        RNS.log(f"WebUI: Error updating trust level: {e}", RNS.LOG_ERROR)
        RNS.log(f"WebUI: Traceback: {traceback.format_exc()}", RNS.LOG_DEBUG)

    return RedirectResponse(f"/conversations/{conv_hash}", status_code=302)


@router.post("/{conv_hash}/delete")
async def delete_conversation(
    request: Request,
    conv_hash: str
):
    """Delete a conversation"""
    import RNS
    from nomadnet.Conversation import Conversation

    nomad_app = request.app.state.nomad_app

    try:
        # Remove from cached conversations if present
        if conv_hash in Conversation.cached_conversations:
            del Conversation.cached_conversations[conv_hash]

        # Remove from unread tracking
        source_hash_bytes = bytes.fromhex(conv_hash)
        if source_hash_bytes in Conversation.unread_conversations:
            del Conversation.unread_conversations[source_hash_bytes]

        # Delete the conversation directory
        Conversation.delete_conversation(conv_hash, nomad_app)

        RNS.log(f"WebUI: Deleted conversation {conv_hash[:16]}...", RNS.LOG_NOTICE)

        # Update unread count via WebSocket
        ws_manager = request.app.state.ws_manager
        conv_list = Conversation.conversation_list(nomad_app)
        unread_count = sum(1 for c in conv_list if c[4])
        ws_manager.broadcast_sync("unread_count", {"count": unread_count})

    except Exception as e:
        RNS.log(f"WebUI: Error deleting conversation: {e}", RNS.LOG_ERROR)

    return RedirectResponse("/conversations", status_code=302)


@router.post("/clear-all")
async def clear_all_conversations(request: Request):
    """Delete all conversations"""
    import RNS
    from nomadnet.Conversation import Conversation

    nomad_app = request.app.state.nomad_app
    deleted_count = 0

    try:
        # Get all conversations
        conv_list = Conversation.conversation_list(nomad_app)

        for source_hash, display_name, trust_level, sort_name, unread in conv_list:
            try:
                # Remove from cached conversations if present
                if source_hash in Conversation.cached_conversations:
                    del Conversation.cached_conversations[source_hash]

                # Remove from unread tracking
                source_hash_bytes = bytes.fromhex(source_hash)
                if source_hash_bytes in Conversation.unread_conversations:
                    del Conversation.unread_conversations[source_hash_bytes]

                # Delete the conversation directory
                Conversation.delete_conversation(source_hash, nomad_app)
                deleted_count += 1

            except Exception as e:
                RNS.log(f"WebUI: Error deleting conversation {source_hash[:16]}...: {e}", RNS.LOG_ERROR)

        RNS.log(f"WebUI: Cleared {deleted_count} conversations", RNS.LOG_NOTICE)

        # Update unread count via WebSocket
        ws_manager = request.app.state.ws_manager
        ws_manager.broadcast_sync("unread_count", {"count": 0})

    except Exception as e:
        RNS.log(f"WebUI: Error clearing conversations: {e}", RNS.LOG_ERROR)

    return RedirectResponse("/conversations", status_code=302)

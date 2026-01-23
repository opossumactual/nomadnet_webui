import os
from datetime import datetime

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

import LXMF
from nomadnet.Directory import DirectoryEntry

router = APIRouter()

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
    from nomadnet.Conversation import Conversation

    conversations = []
    conv_list = Conversation.conversation_list(nomad_app)

    for source_hash, display_name, trust_level, sort_name, unread in conv_list:
        icon, trust_class = TRUST_ICONS.get(trust_level, ("?", "unknown"))
        is_selected = source_hash == selected_hash

        conversations.append({
            "hash": source_hash,
            "name": display_name or source_hash[:16] + "...",
            "unread": unread,
            "selected": is_selected,
            "trust_icon": icon,
            "trust_class": trust_class,
            "trust_level": trust_level,
        })

    return conversations


def _load_messages(nomad_app, conv_hash):
    """Load messages from a conversation"""
    import RNS
    from nomadnet.Conversation import Conversation

    messages = []
    conversation = Conversation(conv_hash, nomad_app)

    # Check if we can send (identity known) - use conversation's own check
    can_send = conversation.source_known
    RNS.log(f"WebUI: Loading conversation {conv_hash[:16]}... source_known={can_send}, messages={len(conversation.messages)}", RNS.LOG_NOTICE)

    # If identity not known, request it from the network
    if not can_send:
        try:
            RNS.Transport.request_path(bytes.fromhex(conv_hash))
            RNS.log(f"WebUI: Requested path for {conv_hash[:16]}...", RNS.LOG_NOTICE)
        except Exception:
            pass

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

            # Format timestamp
            timestamp = datetime.fromtimestamp(msg.get_timestamp())

            messages.append({
                "content": msg.get_content(),
                "title": msg.get_title(),
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M"),
                "outgoing": is_outgoing,
                "state_icon": state_icon,
                "state_class": state_class,
                "hash": msg.get_hash().hex() if msg.get_hash() else "",
            })
        except Exception as e:
            RNS.log(f"WebUI: Error loading message: {e}", RNS.LOG_ERROR)
            continue

    # Sort by timestamp (oldest first)
    messages.sort(key=lambda m: m["timestamp"])

    return messages, conversation, can_send


@router.get("/", response_class=HTMLResponse)
async def conversations_list(request: Request):
    """List all conversations"""
    templates = request.app.state.templates
    nomad_app = request.app.state.nomad_app

    conversations = []
    try:
        conversations = _build_conversation_list(nomad_app)
    except Exception:
        pass

    return templates.TemplateResponse("conversations.html", {
        "request": request,
        "conversations": conversations,
        "selected": None,
        "messages": [],
        "can_send": False,
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

        # Validate hex format
        bytes.fromhex(address)

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
        })


@router.get("/{conv_hash}", response_class=HTMLResponse)
async def conversation_detail(request: Request, conv_hash: str):
    """View a specific conversation"""
    # Handle "new" explicitly in case route ordering doesn't work
    if conv_hash == "new":
        return await new_conversation_form(request)

    templates = request.app.state.templates
    nomad_app = request.app.state.nomad_app

    conversations = []
    messages = []
    selected_name = conv_hash[:16] + "..."
    trust_level = DirectoryEntry.UNKNOWN
    can_send = False

    try:
        conversations = _build_conversation_list(nomad_app, selected_hash=conv_hash)

        # Get selected conversation info
        for conv in conversations:
            if conv["selected"]:
                selected_name = conv["name"]
                trust_level = conv["trust_level"]
                break

        # Load messages
        messages, conversation, can_send = _load_messages(nomad_app, conv_hash)

        # Mark as read
        if nomad_app.conversation_is_unread(conv_hash):
            nomad_app.mark_conversation_read(conv_hash)
            # Remove unread file
            unread_path = nomad_app.conversationpath + "/" + conv_hash + "/unread"
            if os.path.isfile(unread_path):
                os.unlink(unread_path)

    except Exception as e:
        pass

    return templates.TemplateResponse("conversations.html", {
        "request": request,
        "conversations": conversations,
        "selected": conv_hash,
        "selected_name": selected_name,
        "messages": messages,
        "can_send": can_send,
        "trust_level": trust_level,
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

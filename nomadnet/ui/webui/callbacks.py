"""
Callback bridge for WebUI - mimics the TextUI callback interface
so that NomadNet's core components can notify the WebUI of events.
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING, Set, Optional

if TYPE_CHECKING:
    from .routes.api import ConnectionManager


# Global reference to store the original lxmf_delivery function
_original_lxmf_delivery = None
_webui_message_callback = None


class NetworkDisplay:
    """Mimics textui.Network.NetworkDisplay for callback compatibility"""

    def __init__(self, manager: "ConnectionManager", app):
        self.manager = manager
        self.app = app

    def directory_change_callback(self):
        """Called when the announce stream changes"""
        # Get the latest announces
        announces = []
        if hasattr(self.app, 'directory') and self.app.directory:
            for entry in self.app.directory.announce_stream[:50]:
                timestamp, source_hash, app_data, announce_type = entry
                display_name = None
                if app_data:
                    try:
                        display_name = app_data.decode('utf-8')
                    except:
                        pass

                hash_hex = source_hash.hex() if isinstance(source_hash, bytes) else source_hash

                announces.append({
                    "timestamp": timestamp,
                    "hash": hash_hex,
                    "name": display_name,
                    "type": announce_type
                })

        # Broadcast to all WebSocket clients
        self.manager.broadcast_sync("announce_stream", {"announces": announces})


class ConversationsDisplay:
    """Mimics textui.Conversations.ConversationsDisplay for callback compatibility"""

    def __init__(self, manager: "ConnectionManager", app):
        self.manager = manager
        self.app = app
        self._previous_unread: Set[str] = set()
        self._initialize_unread_tracking()

    def _initialize_unread_tracking(self):
        """Initialize tracking of which conversations are unread"""
        try:
            from nomadnet.Conversation import Conversation
            conv_list = Conversation.conversation_list(self.app)
            self._previous_unread = {c[0] for c in conv_list if c[4]}
        except Exception:
            pass

    def update_conversation_list(self):
        """Called when conversations change"""
        try:
            from nomadnet.Conversation import Conversation
            conv_list = Conversation.conversation_list(self.app)

            # Find which conversations are now unread
            current_unread = {c[0] for c in conv_list if c[4]}

            # Find newly unread conversations (new messages)
            newly_unread = current_unread - self._previous_unread

            # Update tracking
            self._previous_unread = current_unread

            # Get conversation names for the changed ones
            conv_names = {c[0]: c[1] for c in conv_list}

            # Broadcast specific change info
            for conv_hash in newly_unread:
                conv_name = conv_names.get(conv_hash) or conv_hash[:16] + "..."
                self.manager.broadcast_sync("new_message", {
                    "conversation_hash": conv_hash,
                    "conversation_name": conv_name,
                })

            # Always send updated count
            unread_count = len(current_unread)
            self.manager.broadcast_sync("unread_count", {"count": unread_count})

            # Also send generic update for conversation list refresh
            self.manager.broadcast_sync("conversations_updated", {
                "changed_conversations": list(newly_unread)
            })

        except Exception:
            # Fallback to simple broadcast
            self.manager.broadcast_sync("conversations_updated", {})

    def notify_message_received(self, source_hash: str, content_preview: str,
                                 title: Optional[str], timestamp: float, sender_name: Optional[str]):
        """Called when a new message is received with full details"""
        self.manager.broadcast_sync("new_message_detail", {
            "conversation_hash": source_hash,
            "sender_name": sender_name or source_hash[:16] + "...",
            "content_preview": content_preview[:100] if content_preview else "",
            "title": title or "",
            "timestamp": datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M"),
        })


class SubDisplays:
    """Container for sub-display callback handlers"""

    def __init__(self, manager: "ConnectionManager", app):
        self.network_display = NetworkDisplay(manager, app)
        self.conversations_display = ConversationsDisplay(manager, app)


class MainDisplay:
    """Mimics textui.Main.MainDisplay for callback compatibility"""

    def __init__(self, manager: "ConnectionManager", app):
        self.sub_displays = SubDisplays(manager, app)


def setup_callbacks(webui, manager: "ConnectionManager"):
    """
    Set up the callback interface on the WebUI instance.
    This creates the main_display attribute that NomadNet's core
    components expect to find on app.ui
    """
    import nomadnet
    import RNS

    global _original_lxmf_delivery, _webui_message_callback

    # Create the callback bridge
    webui.main_display = MainDisplay(manager, webui.app)

    # Register conversation created callback
    nomadnet.Conversation.created_callback = webui.main_display.sub_displays.conversations_display.update_conversation_list

    # Store reference to conversations display for message notifications
    conversations_display = webui.main_display.sub_displays.conversations_display

    # Wrap the lxmf_delivery function to capture message details
    if _original_lxmf_delivery is None and hasattr(webui.app, 'lxmf_delivery'):
        _original_lxmf_delivery = webui.app.lxmf_delivery

        def wrapped_lxmf_delivery(message):
            RNS.log(f"WebUI: lxmf_delivery called for message from {RNS.prettyhexrep(message.source_hash)}", RNS.LOG_NOTICE)

            # Call original handler first
            _original_lxmf_delivery(message)

            # Then send detailed notification
            try:
                source_hash = RNS.hexrep(message.source_hash, delimit=False)
                content = message.content.decode('utf-8') if message.content else ""
                title = message.title.decode('utf-8') if message.title else None

                # Get sender name from directory
                sender_name = webui.app.directory.display_name(message.source_hash)

                RNS.log(f"WebUI: Broadcasting new_message_detail for {source_hash[:16]}...", RNS.LOG_NOTICE)

                conversations_display.notify_message_received(
                    source_hash=source_hash,
                    content_preview=content,
                    title=title,
                    timestamp=message.timestamp,
                    sender_name=sender_name
                )
            except Exception as e:
                RNS.log(f"WebUI: Error in message notification: {e}", RNS.LOG_ERROR)
                import traceback
                RNS.log(f"WebUI: Traceback: {traceback.format_exc()}", RNS.LOG_ERROR)

        webui.app.lxmf_delivery = wrapped_lxmf_delivery

        # Re-register the wrapped callback with the message router
        # The router stores a reference to the callback, so we must update it
        webui.app.message_router.register_delivery_callback(wrapped_lxmf_delivery)
        RNS.log("WebUI: Re-registered wrapped lxmf_delivery with message router", RNS.LOG_DEBUG)

    return webui.main_display

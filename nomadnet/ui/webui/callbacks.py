"""
Callback bridge for WebUI - mimics the TextUI callback interface
so that NomadNet's core components can notify the WebUI of events.
"""

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .routes.api import ConnectionManager


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

    def update_conversation_list(self):
        """Called when conversations change"""
        self.manager.broadcast_sync("conversations_updated", {})

        # Also send unread count
        try:
            from nomadnet.Conversation import Conversation
            conv_list = Conversation.conversation_list(self.app)
            # conv_list is [(hash, name, trust, sort_name, unread), ...]
            unread = sum(1 for c in conv_list if c[4])  # index 4 is unread flag
            self.manager.broadcast_sync("unread_count", {"count": unread})
        except Exception:
            pass


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

    # Create the callback bridge
    webui.main_display = MainDisplay(manager, webui.app)

    # Register conversation created callback
    nomadnet.Conversation.created_callback = webui.main_display.sub_displays.conversations_display.update_conversation_list

    return webui.main_display

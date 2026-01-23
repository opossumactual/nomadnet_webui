import json
import asyncio
from typing import Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.active_connections.discard(websocket)

    async def broadcast(self, event_type: str, data: dict):
        """Broadcast an event to all connected clients"""
        message = json.dumps({"type": event_type, **data})
        async with self._lock:
            dead_connections = set()
            for connection in self.active_connections:
                try:
                    await connection.send_text(message)
                except Exception:
                    dead_connections.add(connection)

            # Clean up dead connections
            self.active_connections -= dead_connections

    def broadcast_sync(self, event_type: str, data: dict):
        """Synchronous wrapper for broadcasting (called from non-async code)"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.broadcast(event_type, data))
            else:
                loop.run_until_complete(self.broadcast(event_type, data))
        except RuntimeError:
            # No event loop running, create a new one
            asyncio.run(self.broadcast(event_type, data))


# Global connection manager instance
manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)

    # Send initial state
    try:
        nomad_app = websocket.app.state.nomad_app

        # Send current announce stream
        if hasattr(nomad_app, 'directory') and nomad_app.directory:
            announces = []
            for entry in nomad_app.directory.announce_stream[:50]:  # Last 50
                timestamp, source_hash, app_data, announce_type = entry
                display_name = None
                if app_data:
                    try:
                        display_name = app_data.decode('utf-8')
                    except:
                        pass

                announces.append({
                    "timestamp": timestamp,
                    "hash": source_hash.hex() if isinstance(source_hash, bytes) else source_hash,
                    "name": display_name,
                    "type": announce_type
                })

            await websocket.send_text(json.dumps({
                "type": "announce_stream",
                "announces": announces
            }))

        # Send unread conversation count
        if hasattr(nomad_app, 'conversations'):
            unread = sum(1 for c in nomad_app.conversations() if c.unread)
            await websocket.send_text(json.dumps({
                "type": "unread_count",
                "count": unread
            }))

    except Exception as e:
        print(f"Error sending initial state: {e}")

    # Keep connection alive and handle incoming messages
    try:
        while True:
            data = await websocket.receive_text()
            # Handle client messages if needed (ping/pong, etc.)
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)


def get_manager() -> ConnectionManager:
    """Get the global connection manager"""
    return manager

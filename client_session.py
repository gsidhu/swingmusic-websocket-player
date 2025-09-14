"""
This script defines the ClientSession class. This class acts as a data structure
to hold client-specific information, such as their unique ID, WebSocket connection
object, and an optional instance of HLSStreamManager if the client is actively
streaming via HLS.
"""

import uuid
from enum import Enum
from typing import Optional, Dict, Any

from starlette.websockets import WebSocket
from logger_setup import logger
from hls_manager import HLSStreamManager

class ClientType(Enum):
    SERVER_PLAYBACK = "server_playback"
    HLS_STREAMING = "hls_streaming"
    CONTROLLER = "controller" # For clients that only send commands, no dedicated stream/player

class ClientSession:
    """
    Represents a single connected WebSocket client and its associated state,
    including an optional HLSStreamManager.
    """
    def __init__(self, client_id: str, websocket: WebSocket, client_type: ClientType, metadata: Optional[Dict[str, Any]] = None):
        self.client_id = client_id
        self.websocket = websocket
        self.client_type = client_type
        self.metadata = metadata if metadata is not None else {}
        self.hls_manager: Optional[HLSStreamManager] = None
        logger.info(f"ClientSession created for client ID: {client_id}, Type: {client_type.value}")

    async def disconnect(self):
        """Clean up resources when a client disconnects."""
        if self.hls_manager:
            await self.hls_manager.stop_stream()
        logger.info(f"ClientSession disconnected for client ID: {self.client_id}")

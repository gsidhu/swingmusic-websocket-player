"""
This script defines the ClientSession class. This class acts as a data structure
to hold client-specific information, such as their unique ID, WebSocket connection
object, and an optional instance of HLSStreamManager if the client is actively
streaming via HLS.
"""

import uuid
from typing import Optional

from starlette.websockets import WebSocket
from logger_setup import logger
from hls_manager import HLSStreamManager

class ClientSession:
    """
    Represents a single connected WebSocket client and its associated state,
    including an optional HLSStreamManager.
    """
    def __init__(self, client_id: str, websocket: WebSocket):
        self.client_id = client_id
        self.websocket = websocket
        self.hls_manager: Optional[HLSStreamManager] = None
        logger.info(f"ClientSession created for client ID: {client_id}")

"""
This script contains the player_websocket_endpoint function. It is responsible
for handling incoming WebSocket connections, registering/unregistering clients,
parsing WebSocket commands (e.g., play, pause, start_hls), and dispatching
these commands to the VLCPlayer instance.
"""

from starlette.websockets import WebSocket, WebSocketDisconnect
from logger_setup import logger
from vlc_player import VLCPlayer
from client_session import ClientType
from protocol import * # Import all HLS-specific commands and error codes

player = VLCPlayer()

class WebSocketHandler:
    def __init__(self, player_instance: VLCPlayer):
        self.player = player_instance
        self.command_handlers = {
            # General commands
            "REGISTER": self._handle_register, # Handled separately during initial handshake
            "get_status": self._handle_get_status,
            "ping": self._handle_ping,
            "get_connections_count": self._handle_get_connections_count,
            "kill_and_reset": self._handle_kill_and_reset,

            # HLS-specific commands
            COMMAND_REQUEST_HLS_STREAM: self._handle_request_hls_stream,
            COMMAND_STOP_HLS_STREAM: self._handle_stop_hls_stream,
            COMMAND_GET_HLS_URL: self._handle_get_hls_url,
            COMMAND_HLS_SEEK: self._handle_hls_seek,
            COMMAND_HLS_STATUS: self._handle_hls_status,

            # VLC Player control commands
            "play": self._handle_play,
            "pause": self._handle_pause,
            "stop": self._handle_stop,
            "seek": self._handle_seek,
            "set_volume": self._handle_set_volume,
            "set_keep_alive": self._handle_set_keep_alive,
            "set_queue": self._handle_set_queue,
            "queue_next": self._handle_queue_next,
            "queue_previous": self._handle_queue_previous,
            "queue_jump": self._handle_queue_jump,
        }

    async def _send_error(self, client_id: str, command: str, message: str, code: str|None = None):
        error_response = {
            "status": "error",
            "command": command,
            "message": message
        }
        if code:
            error_response["code"] = code
        await self.player.send_message_to_client(client_id, error_response)

    async def _handle_register(self, client_id: str, payload: dict, client_session):
        await self._send_error(client_id, "REGISTER", "Already registered.", ERROR_INVALID_COMMAND)

    async def _handle_get_status(self, client_id: str, payload: dict, client_session):
        current_status = await self.player.get_status()
        await self.player.send_message_to_client(client_id, {MESSAGE_TYPE_STATUS_UPDATE: "status_update", "data": current_status})

    async def _handle_ping(self, client_id: str, payload: dict, client_session):
        await self.player.send_message_to_client(client_id, {"type": "pong"})

    async def _handle_get_connections_count(self, client_id: str, payload: dict, client_session):
        count = self.player.get_active_connections_count()
        await self.player.send_message_to_client(client_id, {"type": "connections_count", "data": {"count": count}})

    async def _handle_kill_and_reset(self, client_id: str, payload: dict, client_session):
        # Authorization check for kill_and_reset
        if client_session.client_type not in [ClientType.SERVER_PLAYBACK, ClientType.CONTROLLER]:
            await self._send_error(client_id, "kill_and_reset", "Unauthorized to perform this action.", ERROR_UNAUTHORIZED)
            return
        await self.player.kill_all_connections_and_reset()

    # HLS-specific command handlers
    async def _handle_request_hls_stream(self, client_id: str, payload: dict, client_session):
        if client_session.client_type != ClientType.HLS_STREAMING:
            await self._send_error(client_id, COMMAND_REQUEST_HLS_STREAM, "Unauthorized to request HLS stream.", ERROR_UNAUTHORIZED)
            return

        track_id = payload.get("track_id")
        start_position = payload.get("start_position", 0)

        if not track_id:
            await self._send_error(client_id, COMMAND_REQUEST_HLS_STREAM, "Missing 'track_id' in payload.", ERROR_INVALID_PARAMETERS)
            return

        # Call hls_manager to start the stream
        hls_url = await self.player.start_hls_for_client(client_id, track_id, start_position) # This method needs to be implemented in VLCPlayer and hls_manager

        if hls_url:
            await self.player.send_message_to_client(client_id, {
                "status": "success",
                "command": COMMAND_REQUEST_HLS_STREAM,
                "data": {"hls_url": hls_url}
            })
        else:
            # Error handling will be more specific from hls_manager
            await self._send_error(client_id, COMMAND_REQUEST_HLS_STREAM, "Failed to start HLS stream.", ERROR_FFMPEG_FAILED)

    async def _handle_stop_hls_stream(self, client_id: str, payload: dict, client_session):
        if client_session.client_type != ClientType.HLS_STREAMING:
            await self._send_error(client_id, COMMAND_STOP_HLS_STREAM, "Unauthorized to stop HLS stream.", ERROR_UNAUTHORIZED)
            return

        success = await self.player.stop_hls_for_client(client_id) # This method needs to be implemented in VLCPlayer and hls_manager

        if success:
            await self.player.send_message_to_client(client_id, {
                "status": "success",
                "command": COMMAND_STOP_HLS_STREAM,
                "data": {"message": "HLS stream stopped."}
            })
        else:
            await self._send_error(client_id, COMMAND_STOP_HLS_STREAM, "Failed to stop HLS stream or no stream active.", ERROR_STREAM_NOT_ACTIVE)

    async def _handle_get_hls_url(self, client_id: str, payload: dict, client_session):
        if client_session.client_type != ClientType.HLS_STREAMING:
            await self._send_error(client_id, COMMAND_GET_HLS_URL, "Unauthorized to get HLS URL.", ERROR_UNAUTHORIZED)
            return

        hls_url = await self.player.get_client_hls_url(client_id)

        if hls_url:
            await self.player.send_message_to_client(client_id, {
                "status": "success",
                "command": COMMAND_GET_HLS_URL,
                "data": {"hls_url": hls_url}
            })
        else:
            await self._send_error(client_id, COMMAND_GET_HLS_URL, "No active HLS stream for this client.", ERROR_STREAM_NOT_ACTIVE)

    async def _handle_hls_seek(self, client_id: str, payload: dict, client_session):
        if client_session.client_type != ClientType.HLS_STREAMING:
            await self._send_error(client_id, COMMAND_HLS_SEEK, "Unauthorized to seek HLS stream.", ERROR_UNAUTHORIZED)
            return

        seek_position = payload.get("seek_position")
        if not isinstance(seek_position, (int, float)):
            await self._send_error(client_id, COMMAND_HLS_SEEK, "Missing or invalid 'seek_position' in payload.", ERROR_INVALID_PARAMETERS)
            return

        success = await self.player.seek_hls_stream(client_id, seek_position)

        if success:
            await self.player.send_message_to_client(client_id, {
                "status": "success",
                "command": COMMAND_HLS_SEEK,
                "data": {"message": f"HLS stream seeked to {seek_position}s."}
            })
        else:
            await self._send_error(client_id, COMMAND_HLS_SEEK, "Failed to seek HLS stream or no stream active.", ERROR_HLS_SEEK_FAILED)

    async def _handle_hls_status(self, client_id: str, payload: dict, client_session):
        if client_session.client_type != ClientType.HLS_STREAMING:
            await self._send_error(client_id, COMMAND_HLS_STATUS, "Unauthorized to get HLS stream status.", ERROR_UNAUTHORIZED)
            return

        status_data = await self.player.get_hls_stream_status(client_id)

        if status_data:
            await self.player.send_message_to_client(client_id, {
                "status": "success",
                "command": COMMAND_HLS_STATUS,
                "data": status_data
            })
        else:
            await self._send_error(client_id, COMMAND_HLS_STATUS, "No active HLS stream for this client.", ERROR_STREAM_NOT_ACTIVE)

    # VLC Player control command handlers
    async def _handle_play(self, client_id: str, payload: dict, client_session):
        if client_session.client_type not in [ClientType.SERVER_PLAYBACK, ClientType.CONTROLLER]:
            await self._send_error(client_id, "play", "Unauthorized to control server playback.", ERROR_UNAUTHORIZED)
            return
        filepath = payload.get("filepath")
        if filepath:
            play_immediately = payload.get("play_immediately", True)
            await self.player.play_new(filepath, play_immediately=play_immediately)
        else:
            await self.player.resume()

    async def _handle_pause(self, client_id: str, payload: dict, client_session):
        if client_session.client_type not in [ClientType.SERVER_PLAYBACK, ClientType.CONTROLLER]:
            await self._send_error(client_id, "pause", "Unauthorized to control server playback.", ERROR_UNAUTHORIZED)
            return
        await self.player.pause()

    async def _handle_stop(self, client_id: str, payload: dict, client_session):
        if client_session.client_type not in [ClientType.SERVER_PLAYBACK, ClientType.CONTROLLER]:
            await self._send_error(client_id, "stop", "Unauthorized to control server playback.", ERROR_UNAUTHORIZED)
            return
        await self.player.stop()

    async def _handle_seek(self, client_id: str, payload: dict, client_session):
        if client_session.client_type not in [ClientType.SERVER_PLAYBACK, ClientType.CONTROLLER]:
            await self._send_error(client_id, "seek", "Unauthorized to control server playback.", ERROR_UNAUTHORIZED)
            return
        position_ms = payload.get("position_ms", 0)
        if not isinstance(position_ms, int):
            await self._send_error(client_id, "seek", "Invalid 'position_ms' in payload.", ERROR_INVALID_PARAMETERS)
            return
        await self.player.seek(position_ms)

    async def _handle_set_volume(self, client_id: str, payload: dict, client_session):
        if client_session.client_type not in [ClientType.SERVER_PLAYBACK, ClientType.CONTROLLER]:
            await self._send_error(client_id, "set_volume", "Unauthorized to control server playback.", ERROR_UNAUTHORIZED)
            return
        level = payload.get("level", 100)
        if not isinstance(level, int) or not (0 <= level <= 100):
            await self._send_error(client_id, "set_volume", "Invalid 'level' in payload. Must be an integer between 0 and 100.", ERROR_INVALID_PARAMETERS)
            return
        await self.player.set_volume(level)

    async def _handle_set_keep_alive(self, client_id: str, payload: dict, client_session):
        if client_session.client_type not in [ClientType.SERVER_PLAYBACK, ClientType.CONTROLLER]:
            await self._send_error(client_id, "set_keep_alive", "Unauthorized to control server playback.", ERROR_UNAUTHORIZED)
            return
        enabled = payload.get("enabled", False)
        if not isinstance(enabled, bool):
            await self._send_error(client_id, "set_keep_alive", "Invalid 'enabled' in payload. Must be a boolean.", ERROR_INVALID_PARAMETERS)
            return
        self.player.set_keep_alive(enabled)

    async def _handle_set_queue(self, client_id: str, payload: dict, client_session):
        if client_session.client_type not in [ClientType.SERVER_PLAYBACK, ClientType.CONTROLLER]:
            await self._send_error(client_id, "set_queue", "Unauthorized to control server playback.", ERROR_UNAUTHORIZED)
            return
        filepaths = payload.get("filepaths", [])
        start_index = payload.get("startIndex", 0)
        tracklist_data = payload.get("tracklistData")
        if not isinstance(filepaths, list) or not all(isinstance(f, str) for f in filepaths):
            await self._send_error(client_id, "set_queue", "Invalid 'filepaths' in payload. Must be a list of strings.", ERROR_INVALID_PARAMETERS)
            return
        if not isinstance(start_index, int) or start_index < 0:
            await self._send_error(client_id, "set_queue", "Invalid 'startIndex' in payload. Must be a non-negative integer.", ERROR_INVALID_PARAMETERS)
            return
        # tracklist_data can be None or dict, no specific validation for content yet
        self.player.set_queue(filepaths, start_index, tracklist_data)
        self.player.auto_advance = True
        if filepaths and payload.get("play_immediately", True):
            await self.player.jump_to_queue_index(start_index)

    async def _handle_queue_next(self, client_id: str, payload: dict, client_session):
        if client_session.client_type not in [ClientType.SERVER_PLAYBACK, ClientType.CONTROLLER]:
            await self._send_error(client_id, "queue_next", "Unauthorized to control server playback.", ERROR_UNAUTHORIZED)
            return
        await self.player.play_next_in_queue()

    async def _handle_queue_previous(self, client_id: str, payload: dict, client_session):
        if client_session.client_type not in [ClientType.SERVER_PLAYBACK, ClientType.CONTROLLER]:
            await self._send_error(client_id, "queue_previous", "Unauthorized to control server playback.", ERROR_UNAUTHORIZED)
            return
        await self.player.play_previous_in_queue()

    async def _handle_queue_jump(self, client_id: str, payload: dict, client_session):
        if client_session.client_type not in [ClientType.SERVER_PLAYBACK, ClientType.CONTROLLER]:
            await self._send_error(client_id, "queue_jump", "Unauthorized to control server playback.", ERROR_UNAUTHORIZED)
            return
        index = payload.get("index", 0)
        if not isinstance(index, int) or index < 0:
            await self._send_error(client_id, "queue_jump", "Invalid 'index' in payload. Must be a non-negative integer.", ERROR_INVALID_PARAMETERS)
            return
        await self.player.jump_to_queue_index(index)

    async def handle_message(self, client_id: str, message: dict):
        command = message.get("command")
        payload = message.get("data", {}) # Changed from 'payload' to 'data' as per plan

        if not command:
            await self._send_error(client_id, "unknown", "Command field is missing.", ERROR_INVALID_COMMAND)
            return

        client_session = self.player.get_client_session(client_id)
        if not client_session:
            logger.error(f"Client session not found for ID: {client_id}. Cannot process command: {command}.")
            await self._send_error(client_id, command, "Client session not found.", ERROR_UNAUTHORIZED)
            return

        handler = self.command_handlers.get(command)
        if handler:
            await handler(client_id, payload, client_session)
        else:
            await self._send_error(client_id, command, f"Unknown command: {command}", ERROR_INVALID_COMMAND)


websocket_handler_instance = WebSocketHandler(player)

async def player_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id: str | None = None

    try:
        await websocket.send_json({"command": "REGISTER_REQUEST"})
        logger.info("Sent REGISTER_REQUEST to new client.")

        registration_message = await websocket.receive_json()
        if registration_message.get("command") != "REGISTER":
            logger.warning(f"Client sent non-REGISTER command during handshake: {registration_message.get('command')}")
            await websocket.send_json({"command": "ERROR", "message": "Registration required. First message must be REGISTER."})
            return

        client_type_str = registration_message.get("client_type")
        metadata = registration_message.get("metadata", {})

        if not client_type_str:
            logger.error("Client did not provide client_type during registration.")
            await websocket.send_json({"command": "ERROR", "message": "client_type is required for registration."})
            return

        client_id = await player.register_client(websocket, client_type_str, metadata)

        if not client_id:
            logger.error(f"Failed to register client with type {client_type_str}.")
            await websocket.send_json({"command": "ERROR", "message": "Failed to register client. Invalid client type or server error."})
            return

        websocket.client_id = client_id # type: ignore

        await websocket.send_json({"command": "REGISTER_SUCCESS", "client_id": client_id})
        logger.info(f"Client {client_id} successfully registered as {client_type_str}.")

        initial_status = await player.get_status()
        await player.send_message_to_client(client_id, {"type": MESSAGE_TYPE_STATUS_UPDATE, "data": initial_status})

        while True:
            message = await websocket.receive_json()
            incoming_client_id = message.get("client_id")

            if incoming_client_id != client_id:
                logger.warning(f"Received message from {incoming_client_id} with mismatched client_id {client_id}. Rejecting.")
                await websocket_handler_instance._send_error(client_id, message.get("command", "unknown"), "Client ID mismatch.")
                continue

            await websocket_handler_instance.handle_message(client_id, message)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for client {client_id}.")
    except Exception as e:
        logger.error(f"An error occurred in the WebSocket handler for client {client_id}: {e}", exc_info=True)
    finally:
        if client_id:
            await player.unregister_client(client_id)

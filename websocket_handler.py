"""
This script contains the player_websocket_endpoint function. It is responsible
for handling incoming WebSocket connections, registering/unregistering clients,
parsing WebSocket commands (e.g., play, pause, start_hls), and dispatching
these commands to the VLCPlayer instance.
"""

from starlette.websockets import WebSocket, WebSocketDisconnect
from logger_setup import logger
from vlc_player import VLCPlayer
from client_session import ClientType # Import ClientType

player = VLCPlayer()

async def player_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id: str | None = None # Initialize client_id to None

    try:
        # Phase 1: Initial connection - Request client to register
        await websocket.send_json({"command": "REGISTER_REQUEST"})
        logger.info("Sent REGISTER_REQUEST to new client.")

        # Phase 2: Wait for client's REGISTER message
        registration_message = await websocket.receive_json()
        if registration_message.get("command") != "REGISTER":
            logger.warning(f"Client sent non-REGISTER command during handshake: {registration_message.get('command')}")
            await websocket.send_json({"command": "ERROR", "message": "Registration required. First message must be REGISTER."})
            return # Close connection if not registered properly

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

        # Store client_id in the websocket object for easy access
        websocket.client_id = client_id # type: ignore

        # Phase 3: Send REGISTER_SUCCESS back to client
        await websocket.send_json({"command": "REGISTER_SUCCESS", "client_id": client_id})
        logger.info(f"Client {client_id} successfully registered as {client_type_str}.")

        # Send initial status immediately after successful registration
        initial_status = await player.get_status()
        await player.send_message_to_client(client_id, {"type": "status_update", "data": initial_status})

        while True:
            message = await websocket.receive_json()
            command = message.get("command")
            incoming_client_id = message.get("client_id")
            payload = message.get("payload", {})

            if incoming_client_id != client_id:
                logger.warning(f"Received message from {incoming_client_id} with mismatched client_id {client_id}. Rejecting.")
                await player.send_message_to_client(client_id, {"command": "ERROR", "message": "Client ID mismatch."})
                continue

            client_session = player.get_client_session(client_id)
            if not client_session:
                logger.error(f"Client session not found for ID: {client_id}. Disconnecting.")
                await player.send_message_to_client(client_id, {"command": "ERROR", "message": "Client session not found."})
                break # Disconnect this client

            logger.debug(f"Received command: {command} from client {client_id} ({client_session.client_type.value}) with payload: {payload}")
            
            # --- Command Routing and Authorization ---
            if command == "REGISTER": # Should not receive REGISTER again
                await player.send_message_to_client(client_id, {"command": "ERROR", "message": "Already registered."})
            elif command == "get_status":
                current_status = await player.get_status()
                await player.send_message_to_client(client_id, {"type": "status_update", "data": current_status})
            elif command == "ping":
                await player.send_message_to_client(client_id, {"type": "pong"})
            elif command == "get_connections_count":
                count = player.get_active_connections_count()
                await player.send_message_to_client(client_id, {"type": "connections_count", "data": {"count": count}})
            elif command == "kill_and_reset":
                await player.kill_all_connections_and_reset()
                # No need to send message back, as all connections are killed.
            
            # HLS-specific commands (for HLS_STREAMING clients)
            elif client_session.client_type == ClientType.HLS_STREAMING:
                if command == "start_hls":
                    playlist_url = await player.start_hls_for_client(client_id)
                    if playlist_url:
                        await player.send_message_to_client(client_id, {"type": "hls_started", "data": {"playlist_url": playlist_url}})
                    else:
                        await player.send_message_to_client(client_id, {"type": "error", "data": {"message": "Failed to start HLS stream."}})
                elif command == "stop_hls":
                    await player.stop_hls_for_client(client_id)
                    await player.send_message_to_client(client_id, {"type": "hls_stopped", "data": {"message": "HLS stream stopped."}})
                else:
                    await player.send_message_to_client(client_id, {"command": "ERROR", "message": f"Unauthorized command '{command}' for HLS_STREAMING client."})

            # VLC Player control commands (for SERVER_PLAYBACK or CONTROLLER clients)
            elif client_session.client_type in [ClientType.SERVER_PLAYBACK, ClientType.CONTROLLER]:
                if command == "play":
                    filepath = payload.get("filepath")
                    if filepath:
                        play_immediately = payload.get("play_immediately", True)
                        await player.play_new(filepath, play_immediately=play_immediately)
                    else:
                        await player.resume()
                elif command == "pause":
                    await player.pause()
                elif command == "stop":
                    await player.stop()
                elif command == "seek":
                    await player.seek(int(payload.get("position_ms", 0)))
                elif command == "set_volume":
                    await player.set_volume(int(payload.get("level", 100)))
                elif command == "set_keep_alive":
                    enabled = payload.get("enabled", False)
                    player.set_keep_alive(enabled)
                elif command == "set_queue":
                    filepaths = payload.get("filepaths", [])
                    start_index = payload.get("startIndex", 0)
                    tracklist_data = payload.get("tracklistData")
                    player.set_queue(filepaths, start_index, tracklist_data)
                    player.auto_advance = True
                    if filepaths and payload.get("play_immediately", True):
                        await player.jump_to_queue_index(start_index)
                elif command == "queue_next":
                    await player.play_next_in_queue()
                elif command == "queue_previous":
                    await player.play_previous_in_queue()
                elif command == "queue_jump":
                    index = payload.get("index", 0)
                    await player.jump_to_queue_index(index)
                else:
                    await player.send_message_to_client(client_id, {"command": "ERROR", "message": f"Unauthorized command '{command}' for {client_session.client_type.value} client."})
            else:
                await player.send_message_to_client(client_id, {"command": "ERROR", "message": f"Unknown client type: {client_session.client_type.value}"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for client {client_id}.")
    except Exception as e:
        logger.error(f"An error occurred in the WebSocket handler for client {client_id}: {e}", exc_info=True)
    finally:
        if client_id:
            await player.unregister_client(client_id)

"""
This script contains the player_websocket_endpoint function. It is responsible
for handling incoming WebSocket connections, registering/unregistering clients,
parsing WebSocket commands (e.g., play, pause, start_hls), and dispatching
these commands to the VLCPlayer instance.
"""

from starlette.websockets import WebSocket, WebSocketDisconnect
from logger_setup import logger
from vlc_player import VLCPlayer

player = VLCPlayer()

async def player_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = await player.register_client(websocket) # Get the client_id after registration
    
    try:
        # Send initial status immediately on connection
        initial_status = await player.get_status()
        await websocket.send_json({"type": "status_update", "data": initial_status})

        while True:
            message = await websocket.receive_json()
            command = message.get("command")
            payload = message.get("payload", {})

            logger.debug(f"Received command: {command} from client {client_id} with payload: {payload}")
            
            # HLS-specific commands
            if command == "start_hls":
                playlist_url = await player.start_hls_for_client(client_id)
                if playlist_url:
                    await websocket.send_json({"type": "hls_started", "data": {"playlist_url": playlist_url}})
                else:
                    await websocket.send_json({"type": "error", "data": {"message": "Failed to start HLS stream."}})
            elif command == "stop_hls":
                await player.stop_hls_for_client(client_id)
                await websocket.send_json({"type": "hls_stopped", "data": {"message": "HLS stream stopped."}})
            # Existing commands

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
                # Acknowledge the change by sending back the current status.
                # This will be broadcast to all clients, which is the desired behavior.
            elif command == "set_queue":
                filepaths = payload.get("filepaths", [])
                start_index = payload.get("startIndex", 0)
                tracklist_data = payload.get("tracklistData") # Extract the full tracklist object
                player.set_queue(filepaths, start_index, tracklist_data)
                player.auto_advance = True  # Enable auto-advance when queue is set
                # Optionally start playing the current track immediately
                if filepaths and payload.get("play_immediately", True):
                    await player.jump_to_queue_index(start_index)
            elif command == "queue_next":
                await player.play_next_in_queue()
            elif command == "queue_previous":
                await player.play_previous_in_queue()
            elif command == "queue_jump":
                index = payload.get("index", 0)
                await player.jump_to_queue_index(index)
            elif command == "get_status":
                current_status = await player.get_status()
                await websocket.send_json({"type": "status_update", "data": current_status})
            elif command == "ping":
                # pong is handled implicitly by status updates, but we can be explicit
                await websocket.send_json({"type": "pong"})
            elif command == "get_connections_count":
                count = player.get_active_connections_count()
                await websocket.send_json({"type": "connections_count", "data": {"count": count}})
            elif command == "kill_and_reset":
                await player.kill_all_connections_and_reset()
                # Cannot call "send" once a close message has been sent.
                # await websocket.send_json({"type": "server_reset", "data": {"message": "Server reset complete."}})
            else:
                await websocket.send_json({
                    "type": "error", 
                    "data": {"message": f"Unknown command: {command}"}
                })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected.")
    except Exception as e:
        logger.error(f"An error occurred in the WebSocket handler for client {client_id}: {e}", exc_info=True)
    finally:
        await player.unregister_client(client_id)

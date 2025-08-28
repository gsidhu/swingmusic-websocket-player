import asyncio
import logging
from pathlib import Path
import time
from typing import List, Optional

import vlc
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

# Configuration
LOG_LEVEL = logging.INFO

#  Logging Setup
logging.basicConfig(
    level=LOG_LEVEL, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class VLCPlayer:
    """
    A singleton class to manage the VLC player instance and state.
    This class bridges the synchronous python-vlc library with the asyncio world.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(VLCPlayer, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.vlc_instance: vlc.Instance
        self.player: vlc.MediaPlayer
        self.current_track_path: Path | None
        self.connected_clients: set[WebSocket]
        self._status_broadcaster_task: asyncio.Task | None
        self.keep_alive: bool
        
        # Queue management
        self.queue: List[str] = []
        self.current_queue_index: int = 0
        self.auto_advance: bool = True
        self._track_end_listener_task: asyncio.Task | None = None
        self.tracklist_data: Optional[dict] = None # New attribute to store the full tracklist object

        if hasattr(self, 'player'):
            return

        logger.info("Initializing VLC Player...")
        self.vlc_instance = vlc.Instance("--no-xlib") # type: ignore
        self.player = self.vlc_instance.media_player_new()
        self.current_track_path = None
        
        self.connected_clients = set()
        self._status_broadcaster_task = None
        self.keep_alive = False

    async def _run_sync(self, func, *args, **kwargs):
        """Runs a synchronous (blocking) function in a separate thread."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    # Queue Management Methods

    def set_queue(self, filepaths: List[str], start_index: int = 0, tracklist_data: Optional[dict] = None):
        """Sets the entire queue and current position, along with the full tracklist data."""
        self.queue = filepaths.copy()
        self.current_queue_index = max(0, min(start_index, len(self.queue) - 1))
        self.tracklist_data = tracklist_data # Store the full tracklist object
        logger.info(f"Queue set with {len(self.queue)} tracks, starting at index {self.current_queue_index}")
        if self.tracklist_data:
            logger.info("Tracklist data received and stored.")

    def get_queue_status(self) -> dict:
        """Returns current queue information."""
        return {
            "queue": self.queue,
            "currentIndex": self.current_queue_index,
            "totalTracks": len(self.queue),
            "autoAdvance": self.auto_advance,
            "tracklistData": self.tracklist_data # Include the full tracklist object
        }

    async def play_next_in_queue(self) -> bool:
        """Advances to the next track in the queue. Returns True if successful."""
        if not self.queue or self.current_queue_index >= len(self.queue) - 1:
            logger.info("End of queue reached.")
            return False
        
        self.current_queue_index += 1
        next_track = self.queue[self.current_queue_index]
        logger.info(f"Auto-advancing to track {self.current_queue_index + 1}/{len(self.queue)}: {next_track}")
        await self.play_new(next_track, play_immediately=True)
        return True

    async def play_previous_in_queue(self) -> bool:
        """Goes back to the previous track in the queue. Returns True if successful."""
        if not self.queue or self.current_queue_index <= 0:
            logger.info("Already at the beginning of the queue.")
            return False
        
        self.current_queue_index -= 1
        previous_track = self.queue[self.current_queue_index]
        logger.info(f"Going back to track {self.current_queue_index + 1}/{len(self.queue)}: {previous_track}")
        await self.play_new(previous_track, play_immediately=True)
        return True

    async def jump_to_queue_index(self, index: int) -> bool:
        """Jumps to a specific track in the queue by index."""
        if not self.queue or index < 0 or index >= len(self.queue):
            logger.warning(f"Invalid queue index: {index}")
            return False
        
        self.current_queue_index = index
        track = self.queue[self.current_queue_index]
        logger.info(f"Jumping to track {self.current_queue_index + 1}/{len(self.queue)}: {track}")
        await self.play_new(track, play_immediately=True)
        return True

    # Player Control Methods (async wrappers)

    async def play_new(self, audio_filepath: str, play_immediately: bool = True) -> dict:
        """
        Loads a new track.
        If play_immediately is True, it plays the track.
        If play_immediately is False, it loads the track and then immediately pauses it.
        """
        try:
            filepath = Path(audio_filepath).resolve()
            if not filepath.is_file():
                raise FileNotFoundError("Track file not found.")
        except (ValueError, FileNotFoundError) as e:
            error_message = f"Invalid track path: {e}"
            logger.error(error_message)
            return {"error": error_message}

        self.current_track_path = filepath
        log_action = "Playing" if play_immediately else "Loading"
        logger.info(f"{log_action} new track: {self.current_track_path}")

        def _play_sync():
            media = self.vlc_instance.media_new(str(self.current_track_path))
            media.parse()  # Pre-parse the media structure
            self.player.set_media(media)
            self.player.play()
            
            if not play_immediately:
                # Give VLC a moment to start before pausing. This is crucial for pre-loading.
                time.sleep(0.2) 
                self.player.pause()

        await self._run_sync(_play_sync)
        
        # Start the track end listener if we have a queue
        if self.queue and not self._track_end_listener_task:
            self.start_track_end_listener()
            
        return await self.get_status()

    async def resume(self):
        """Resumes playback if paused."""
        logger.info("Resuming playback.")
        # VLC's pause method is a toggle.
        await self._run_sync(self.player.set_pause, 0)

    async def pause(self):
        """Pauses playback if playing."""
        logger.info("Pausing playback.")
        # VLC's pause method is a toggle.
        await self._run_sync(self.player.set_pause, 1)

    async def stop(self):
        """Stops playback."""
        logger.info("Stopping playback.")
        self.current_track_path = None
        await self._run_sync(self.player.stop)
        
        # Stop the track end listener
        if self._track_end_listener_task:
            self._track_end_listener_task.cancel()
            self._track_end_listener_task = None

    async def seek(self, position_ms: int):
        """Seeks to a specific time in milliseconds."""
        if await self._run_sync(self.player.is_seekable):
            logger.info(f"Seeking to {position_ms}ms.")
            await self._run_sync(self.player.set_time, position_ms)
        else:
            logger.warning("Seek attempted on non-seekable media.")

    async def set_volume(self, level: int):
        """Sets the volume (0-100)."""
        clamped_level = max(0, min(100, level))
        logger.info(f"Setting volume to {clamped_level}.")
        await self._run_sync(self.player.audio_set_volume, clamped_level)

    # Status and Client Management

    def set_keep_alive(self, enabled: bool):
        """ Sets the keep-alive flag. This is a sync operation."""
        self.keep_alive = bool(enabled)
        logger.info(f"Keep-alive has been {'ENABLED' if self.keep_alive else 'DISABLED'}.")

    async def get_status(self) -> dict:
        """Gets the current player status."""
        def _get_status_sync():
            state = self.player.get_state()
            return {
                "state": str(state).split(".")[-1],
                "currentTime": self.player.get_time() / 1000.0,
                "duration": self.player.get_length() / 1000.0,
                "volume": self.player.audio_get_volume(),
                "filepath": str(self.current_track_path) if self.current_track_path else None,
                "keepAlive": self.keep_alive,
                "queueStatus": self.get_queue_status()
            }
        return await self._run_sync(_get_status_sync)
    
    async def register_client(self, websocket: WebSocket):
        """
        Registers a new client. This server supports multiple simultaneous connections.
        The `keep_alive` state is NOT reset on new connections, allowing for persistent sessions.
        """
        self.connected_clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.connected_clients)}")

    async def unregister_client(self, websocket: WebSocket):
        """Removes a client and stops playback if it was the last one and keep_alive is false."""
        self.connected_clients.discard(websocket)
        logger.info(f"Client disconnected. Remaining clients: {len(self.connected_clients)}")
        
        # Check both client count and the keep_alive flag
        if not self.connected_clients and not self.keep_alive:
            logger.info("Last client has disconnected and keep-alive is OFF. Stopping VLC playback.")
            await self.stop()
        elif not self.connected_clients and self.keep_alive:
            logger.info("Last client has disconnected, but keep-alive is ON. Playback will continue.")

    def get_active_connections_count(self) -> int:
        """Returns the number of currently active WebSocket connections."""
        return len(self.connected_clients)

    async def kill_all_connections_and_reset(self):
        """Kills all active connections, clears the queue, and resets the server."""
        logger.info("Killing all connections, clearing queue, and resetting server.")
        
        # Close all active WebSocket connections
        for client in list(self.connected_clients): # Iterate over a copy to allow modification
            try:
                await client.close()
            except Exception as e:
                logger.warning(f"Error closing client connection during reset: {e}")
        self.connected_clients.clear()

        # Clear the queue
        self.queue = []
        self.current_queue_index = 0
        self.auto_advance = True # Reset auto-advance to default

        # Stop VLC playback
        await self.stop()

        # Reset keep_alive flag
        self.set_keep_alive(False)

        # Cancel background tasks
        if self._status_broadcaster_task and not self._status_broadcaster_task.done():
            self._status_broadcaster_task.cancel()
            self._status_broadcaster_task = None
            logger.info("Status broadcaster task cancelled.")
        
        if self._track_end_listener_task and not self._track_end_listener_task.done():
            self._track_end_listener_task.cancel()
            self._track_end_listener_task = None
            logger.info("Track end listener task cancelled.")
        
        logger.info("Server reset complete.")

    async def _status_broadcaster(self):
        """Periodically sends the player status to all connected clients."""
        while True:
            try:
                # Also process player state if keep_alive is true, even with no clients
                is_active = self.connected_clients or self.keep_alive
                if not is_active:
                    await asyncio.sleep(1)
                    continue

                status = await self.get_status()
                
                # Only try to send if there are actually clients connected
                if self.connected_clients:
                    # Create a list of send tasks to avoid issues if a client disconnects during iteration
                    tasks = [
                        client.send_json({"type": "status_update", "data": status})
                        for client in self.connected_clients
                    ]
                    await asyncio.gather(*tasks, return_exceptions=True) # Don't let one failed client stop others
            except Exception as e:
                logger.warning(f"Error in status broadcaster: {e}")

            await asyncio.sleep(0.25)

    def start_status_broadcaster(self):
        """Starts the background task for broadcasting status."""
        if not self._status_broadcaster_task or self._status_broadcaster_task.done():
            logger.info("Starting status broadcaster task.")
            self._status_broadcaster_task = asyncio.create_task(self._status_broadcaster())

    async def _track_end_listener(self):
        """Monitors for track end events and auto-advances the queue."""
        while True:
            try:
                if not self.auto_advance or not self.queue:
                    await asyncio.sleep(1)
                    continue

                state = await self._run_sync(self.player.get_state)
                
                # Check if track has ended
                if str(state) == "State.Ended":
                    logger.info("Track ended, attempting to play next track in queue.")
                    success = await self.play_next_in_queue()
                    if not success:
                        logger.info("End of queue reached, stopping auto-advance.")
                        self.auto_advance = False
                
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Error in track end listener: {e}")
                await asyncio.sleep(1)

    def start_track_end_listener(self):
        """Starts the background task for monitoring track end events."""
        if not self._track_end_listener_task or self._track_end_listener_task.done():
            logger.info("Starting track end listener task.")
            self._track_end_listener_task = asyncio.create_task(self._track_end_listener())

# Starlette WebSocket Endpoint
player = VLCPlayer()

async def player_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await player.register_client(websocket)
    
    try:
        # Send initial status immediately on connection
        # Status includes "state", "currentTime", "duration", "volume", "filepath", "keepAlive" and "queueStatus"
        initial_status = await player.get_status()
        await websocket.send_json({"type": "status_update", "data": initial_status})

        while True:
            message = await websocket.receive_json()
            command = message.get("command")
            payload = message.get("payload", {})

            logger.debug(f"Received command: {command} with payload: {payload}")

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
        logger.error(f"An error occurred in the WebSocket handler: {e}", exc_info=True)
    finally:
        await player.unregister_client(websocket)

async def on_startup():
    player.start_status_broadcaster()

routes = [
    WebSocketRoute("/ws/player", endpoint=player_websocket_endpoint),
]

app = Starlette(routes=routes, on_startup=[on_startup])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=1971)

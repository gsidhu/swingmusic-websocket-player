"""
This script encapsulates the VLCPlayer singleton class. It manages the core VLC
player instance, audio playback controls (play, pause, stop, seek, volume),
queue management, and the overall state of the media player. It also includes
methods for starting and stopping HLS streams for specific clients by interacting
with HLSStreamManager instances.
"""

import asyncio
import time
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any

import vlc
import psutil # Added for process killing in HLS stream management
from starlette.websockets import WebSocket
from logger_setup import logger
from client_session import ClientSession, ClientType
from hls_manager import HLSStreamManager
from config import HLS_HTTP_PORT
from protocol import MESSAGE_TYPE_STATUS_UPDATE

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
        self.active_clients: Dict[str, ClientSession]
        self.websocket_connections: Dict[str, WebSocket]
        self._status_broadcaster_task: asyncio.Task | None
        self.keep_alive: bool
        self.hls_http_port: int = HLS_HTTP_PORT
        
        # Queue management
        self.queue: List[str] = []
        self.current_queue_index: int = 0
        self.auto_advance: bool = True
        self._track_end_listener_task: asyncio.Task | None = None
        self.tracklist_data: Optional[dict] = None # New attribute to store the full tracklist object

        if hasattr(self, 'player'):
            return

        logger.info("Initializing VLC Player (acting as ClientManager)...")
        self.vlc_instance = vlc.Instance("--no-xlib") # type: ignore
        self.player = self.vlc_instance.media_player_new()
        self.current_track_path = None
        
        self.active_clients = {} 
        self.websocket_connections = {}
        self._status_broadcaster_task = None
        self.keep_alive = False

    def get_client_session(self, client_id: str) -> Optional[ClientSession]:
        """Retrieves a ClientSession object by its ID."""
        return self.active_clients.get(client_id)

    async def start_hls_for_client(self, client_id: str, track_id: str, start_position: int = 0) -> Optional[str]:
        """
        Starts an HLS stream for a specific client.
        Returns the playlist URL if successful, None otherwise.
        """
        client_session = self.get_client_session(client_id)
        if not client_session:
            logger.warning(f"Attempted to start HLS for unknown client: {client_id}")
            return None
        
        if client_session.client_type != ClientType.HLS_STREAMING:
            logger.warning(f"Client {client_id} is not an HLS_STREAMING client. Cannot start HLS.")
            return None

        # Assuming track_id is the filepath
        media_filepath = Path(track_id).resolve() 

        if not media_filepath.is_file():
            logger.error(f"Track ID '{track_id}' (filepath: {media_filepath}) not found for client {client_id}.")
            return None

        if client_session.hls_manager:
            logger.info(f"HLS stream already active for client {client_id}. Stopping existing stream.")
            await client_session.hls_manager.stop_stream()

        logger.info(f"Starting HLS stream for client {client_id} from {media_filepath} at position {start_position}s")
        hls_manager = HLSStreamManager(client_id, media_filepath, self.hls_http_port)
        client_session.hls_manager = hls_manager
        await hls_manager.start_stream(start_position=start_position)
        
        if hls_manager.ffmpeg_process:
            playlist_url = hls_manager.get_playlist_url()
            logger.info(f"HLS stream started for client {client_id}. Playlist URL: {playlist_url}")
            return playlist_url
        else:
            logger.error(f"Failed to start FFmpeg process for client {client_id}.")
            client_session.hls_manager = None
            return None

    async def stop_hls_for_client(self, client_id: str) -> bool:
        """Stops the HLS stream for a specific client. Returns True if successful."""
        client_session = self.get_client_session(client_id)
        if not client_session:
            logger.warning(f"Attempted to stop HLS for unknown client: {client_id}")
            return False
        
        if client_session.client_type != ClientType.HLS_STREAMING:
            logger.warning(f"Client {client_id} is not an HLS_STREAMING client. No HLS stream to stop.")
            return False

        if client_session.hls_manager:
            logger.info(f"Stopping HLS stream for client {client_id}.")
            await client_session.hls_manager.stop_stream()
            client_session.hls_manager = None
            return True
        else:
            logger.info(f"No active HLS stream found for client {client_id}.")
            return False

    async def get_client_hls_url(self, client_id: str) -> Optional[str]:
        """Returns the HLS playlist URL for a specific client if a stream is active."""
        client_session = self.get_client_session(client_id)
        if not client_session or not client_session.hls_manager or not client_session.hls_manager.ffmpeg_process:
            return None
        return client_session.hls_manager.get_playlist_url()

    async def seek_hls_stream(self, client_id: str, seek_position: float) -> bool:
        """Seeks the HLS stream for a specific client."""
        client_session = self.get_client_session(client_id)
        if not client_session or not client_session.hls_manager:
            logger.warning(f"Attempted to seek HLS for unknown client or no active stream: {client_id}")
            return False
        
        logger.info(f"Seeking HLS stream for client {client_id} to {seek_position}s.")
        return await client_session.hls_manager.seek_stream(seek_position)

    async def get_hls_stream_status(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Gets the detailed status of the HLS stream for a specific client."""
        client_session = self.get_client_session(client_id)
        if not client_session or not client_session.hls_manager:
            return None
        
        status = await client_session.hls_manager.get_stream_status()
        return status

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

    async def send_message_to_client(self, client_id: str, message: Dict[str, Any]):
        """Sends a JSON message to a specific client."""
        websocket = self.websocket_connections.get(client_id)
        if websocket:
            try:
                await websocket.send_json(message)
                logger.debug(f"Sent message to client {client_id}: {message.get('command', message.get('type'))}")
            except Exception as e:
                logger.error(f"Failed to send message to client {client_id}: {e}")
        else:
            logger.warning(f"Attempted to send message to unknown client: {client_id}")

    async def broadcast_message_to_type(self, client_type: ClientType, message: Dict[str, Any]):
        """Sends a JSON message to all clients of a specific type."""
        tasks = []
        for client_id, session in self.active_clients.items():
            if session.client_type == client_type:
                tasks.append(self.send_message_to_client(client_id, message))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"Broadcasted message to {client_type.value} clients: {message.get('command', message.get('type'))}")
        else:
            logger.debug(f"No {client_type.value} clients to broadcast to.")

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
    
    async def register_client(self, websocket: WebSocket, client_type_str: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Registers a new client with a generated ID, client type, and metadata.
        Returns the generated client_id if successful, None otherwise.
        """
        try:
            client_type = ClientType(client_type_str)
        except ValueError:
            logger.error(f"Invalid client type provided: {client_type_str}")
            return None

        client_id = str(uuid.uuid4())
        client_session = ClientSession(client_id, websocket, client_type, metadata)
        
        self.active_clients[client_id] = client_session
        self.websocket_connections[client_id] = websocket
        
        logger.info(f"Client {client_id} registered as {client_type.value}. Total active clients: {len(self.active_clients)}")
        return client_id

    async def unregister_client(self, client_id: str):
        """Removes a client and stops its HLS stream if active."""
        client_session = self.active_clients.pop(client_id, None)
        websocket = self.websocket_connections.pop(client_id, None)

        if client_session:
            logger.info(f"Client {client_id} ({client_session.client_type.value}) disconnected. Remaining clients: {len(self.active_clients)}")
            if client_session.hls_manager:
                await client_session.hls_manager.stop_stream()
        else:
            logger.warning(f"Attempted to unregister unknown client: {client_id}")
        
        # Check both client count and the keep_alive flag for VLC playback
        if not self.active_clients and not self.keep_alive:
            logger.info("Last client has disconnected and keep-alive is OFF. Stopping VLC playback.")
            await self.stop()
        elif not self.active_clients and self.keep_alive:
            logger.info("Last client has disconnected, but keep-alive is ON. Playback will continue.")

    def get_active_connections_count(self) -> int:
        """Returns the number of currently active WebSocket connections."""
        return len(self.active_clients)

    async def kill_all_connections_and_reset(self):
        """Kills all active connections, clears the queue, and resets the server."""
        logger.info("Killing all connections, clearing queue, and resetting server.")
        
        # Close all active WebSocket connections and stop HLS streams
        for client_id, client_session in list(self.active_clients.items()):
            try:
                if client_session.hls_manager:
                    await client_session.hls_manager.stop_stream()
                # Use the stored websocket connection to close
                websocket = self.websocket_connections.get(client_id)
                if websocket:
                    await websocket.close()
            except Exception as e:
                logger.warning(f"Error closing client {client_id} connection during reset: {e}")
        self.active_clients.clear()
        self.websocket_connections.clear()

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
                is_active = self.active_clients or self.keep_alive
                if not is_active:
                    await asyncio.sleep(1)
                    continue

                status = await self.get_status()
                
                # Only try to send if there are actually clients connected
                if self.active_clients:
                    # Create a list of send tasks to avoid issues if a client disconnects during iteration
                    tasks = []
                    for client_id, client_session in self.active_clients.items():
                        try:
                            # Include HLS stream status if active for this client
                            hls_stream_status = None
                            if client_session.hls_manager and client_session.hls_manager.is_active:
                                hls_stream_status = await client_session.hls_manager.get_stream_status()

                            # Ensure the message includes the client_id for context
                            message_data = {
                                "server_status": status,
                                "current_track": status.get("filepath"), # Simplified for now
                                "hls_stream": hls_stream_status
                            }
                            message = {"type": MESSAGE_TYPE_STATUS_UPDATE, "data": message_data, "recipient_client_id": client_id}
                            tasks.append(self.send_message_to_client(client_id, message))
                        except Exception as e:
                            logger.warning(f"Error preparing status update for client {client_id}: {e}")
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

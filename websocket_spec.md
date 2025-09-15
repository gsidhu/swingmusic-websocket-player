# WebSocket Client Specification for Swing Music Player

This document outlines the complete process for a front-end client to connect to the Swing Music WebSocket Player server, including initial handshake, sending commands for playback control, receiving status updates, and handling errors.

## 1. WebSocket Connection URL

The client should establish a WebSocket connection to the following URL:

`ws://<server_ip>:1971/ws/player`

- Replace `<server_ip>` with the actual IP address or hostname where your `swingmusic-websocket-player` server is running.
- If the server is running on the same machine as the client, `localhost` can be used.
- The port `1971` is the default port for the WebSocket server.

**Example (JavaScript):**

```javascript
const serverIp = "localhost"; // Or your server's IP address
const ws = new WebSocket(`ws://${serverIp}:1971/ws/player`);

ws.onopen = () => {
    console.log("WebSocket connection established.");
    // Proceed with registration
};

ws.onclose = () => {
    console.log("WebSocket connection closed.");
};

ws.onerror = (error) => {
    console.error("WebSocket error:", error);
};
```

## 2. Initial Registration Handshake

Upon a successful WebSocket connection, the server will immediately send a `REGISTER_REQUEST` message. The client **must** respond with a `REGISTER` command, specifying its `client_type` and optional `metadata`.

### 2.1 Server's `REGISTER_REQUEST`

The first message from the server will be:

```json
{
  "command": "REGISTER_REQUEST"
}
```

### 2.2 Client's `REGISTER` Response

The client must respond with a `REGISTER` message.

**`client_type` options (from `client_session.py`):**

-   `"server_playback"`: For clients that control the main server playback (e.g., the primary UI that manages the queue and playback state).
-   `"controller"`: For clients that send commands to control playback (e.g., a simple remote control app).
-   `"hls_streaming"`: For clients that intend to stream HLS audio directly from the server (e.g., a browser playing audio via HLS).

**Example (JavaScript):**

```javascript
ws.onmessage = (event) => {
    const message = JSON.parse(event.data);

    if (message.command === "REGISTER_REQUEST") {
        console.log("Received REGISTER_REQUEST from server. Sending REGISTER response.");
        ws.send(JSON.stringify({
            "command": "REGISTER",
            "client_type": "server_playback", // Or "controller", "hls_streaming"
            "metadata": {
                "name": "My Vue Frontend",
                "version": "1.0.0",
                "device": "MacBook Pro"
            }
        }));
    } else if (message.command === "REGISTER_SUCCESS") {
        console.log(`Client successfully registered with ID: ${message.client_id}`);
        const clientId = message.client_id; // Store this client_id for future commands
        // Now the client can start sending commands
    }
    // ... handle other messages
};
```

## 3. Sending Commands to the Server

Once successfully registered, the client can send commands to the server using a consistent JSON message format. The `client_id` received during registration **must** be included in all subsequent messages.

**General Command Format:**

```json
{
  "client_id": "<YOUR_ASSIGNED_CLIENT_ID>",
  "command": "<COMMAND_NAME>",
  "data": {
    // Command-specific payload (can be an empty object if no data is needed)
  }
}
```

### 3.1 Common Playback Control Commands

*   **Play a new track:** Loads and plays a specified audio file.
    ```json
    {
      "client_id": "...",
      "command": "play",
      "data": {
        "filepath": "/path/to/your/music/track.mp3",
        "play_immediately": true // Optional, defaults to true. If false, loads and pauses.
      }
    }
    ```
    If `filepath` is omitted, it attempts to resume playback.

*   **Pause playback:** Pauses the currently playing track.
    ```json
    {
      "client_id": "...",
      "command": "pause",
      "data": {}
    }
    ```

*   **Stop playback:** Stops the currently playing track and resets the player.
    ```json
    {
      "client_id": "...",
      "command": "stop",
      "data": {}
    }
    ```

*   **Seek to a position:** Jumps to a specific time in the current track.
    ```json
    {
      "client_id": "...",
      "command": "seek",
      "data": {
        "position_ms": 60000 // Seek to 60 seconds (in milliseconds)
      }
    }
    ```

*   **Set volume:** Adjusts the player's volume.
    ```json
    {
      "client_id": "...",
      "command": "set_volume",
      "data": {
        "level": 75 // Integer between 0 and 100
      }
    }
    ```

*   **Set keep-alive:** Controls whether playback continues when all clients disconnect.
    ```json
    {
      "client_id": "...",
      "command": "set_keep_alive",
      "data": {
        "enabled": true // true to keep playing, false to stop on disconnect
      }
    }
    ```

*   **Set the playback queue:** Replaces the entire playback queue and sets the starting track.
    ```json
    {
      "client_id": "...",
      "command": "set_queue",
      "data": {
        "filepaths": ["/path/to/track1.mp3", "/path/to/track2.mp3", "/path/to/track3.mp3"],
        "startIndex": 0, // Optional, defaults to 0. Index of the track to start playing.
        "tracklistData": { /* full tracklist JSON object from Swing Music app */ }, // Optional
        "play_immediately": true // Optional, defaults to true. If true, starts playing the track at startIndex.
      }
    }
    ```

*   **Play next in queue:** Advances to the next track in the current queue.
    ```json
    {
      "client_id": "...",
      "command": "queue_next",
      "data": {}
    }
    ```

*   **Play previous in queue:** Goes back to the previous track in the current queue.
    ```json
    {
      "client_id": "...",
      "command": "queue_previous",
      "data": {}
    }
    ```

*   **Jump to specific queue index:** Jumps to and plays a track at a specific index in the queue.
    ```json
    {
      "client_id": "...",
      "command": "queue_jump",
      "data": {
        "index": 2 // Jump to the 3rd track in the queue (0-indexed)
      }
    }
    ```

### 3.2 HLS-Specific Commands (for `HLS_STREAMING` clients)

These commands are primarily for clients registered with `client_type: "HLS_STREAMING"`.

*   **Request HLS stream:** Initiates an HLS stream for a given track.
    ```json
    {
      "client_id": "...",
      "command": "REQUEST_HLS_STREAM",
      "data": {
        "track_id": "/path/to/your/music/track.mp3", // Filepath of the track
        "start_position": 0 // Optional, defaults to 0. Start position in seconds.
      }
    }
    ```
    Server response (on success):
    ```json
    {
      "status": "success",
      "command": "REQUEST_HLS_STREAM",
      "data": {"hls_url": "http://<server_ip>:<hls_port>/hls/<client_id>/playlist.m3u8"}
    }
    ```

*   **Stop HLS stream:** Stops the active HLS stream for the client.
    ```json
    {
      "client_id": "...",
      "command": "STOP_HLS_STREAM",
      "data": {}
    }
    ```

*   **Get HLS URL:** Retrieves the current HLS playlist URL if a stream is active.
    ```json
    {
      "client_id": "...",
      "command": "GET_HLS_URL",
      "data": {}
    }
    ```

*   **HLS Seek:** Seeks to a specific position in the HLS stream.
    ```json
    {
      "client_id": "...",
      "command": "HLS_SEEK",
      "data": {
        "seek_position": 30.5 // Seek to 30.5 seconds
      }
    }
    ```

*   **HLS Status:** Gets detailed status of the HLS stream.
    ```json
    {
      "client_id": "...",
      "command": "HLS_STATUS",
      "data": {}
    }
    ```

## 4. Receiving Status Updates from the Server

The server periodically broadcasts status updates to all connected clients. Clients should listen for messages with `"type": "status_update"` to keep their UI synchronized with the server's playback state.

**Status Update Format:**

```json
{
  "type": "status_update",
  "data": {
    "server_status": {
      "state": "Playing", // e.g., "Playing", "Paused", "Stopped", "Ended"
      "currentTime": 123.45, // Current playback time in seconds
      "duration": 240.0,    // Total duration of the current track in seconds
      "volume": 75,         // Current volume level (0-100)
      "filepath": "/path/to/current/track.mp3", // Currently playing track
      "keepAlive": false,   // Whether keep-alive is enabled
      "queueStatus": {
        "queue": ["/path/to/track1.mp3", "/path/to/track2.mp3"], // Current queue
        "currentIndex": 0,      // Index of the currently playing track in the queue
        "totalTracks": 2,       // Total number of tracks in the queue
        "autoAdvance": true,    // Whether auto-advance is enabled
        "tracklistData": { /* full tracklist JSON object */ } // Stored tracklist data
      }
    },
    "current_track": "/path/to/current/track.mp3", // Simplified current track path
    "hls_stream": { // Only present if an HLS stream is active for this client
      "is_active": true,
      "current_time": 15.2,
      "duration": 180.0,
      "bitrate": "128k",
      "hls_url": "http://<server_ip>:<hls_port>/hls/<client_id>/playlist.m3u8"
    }
  },
  "recipient_client_id": "..." // The client ID this message is intended for (for context)
}
```

## 5. Error Handling

The server will send error messages in a standardized format when a command fails or an invalid operation is attempted.

**Error Message Format:**

```json
{
  "status": "error",
  "command": "<COMMAND_THAT_FAILED_OR_UNKNOWN>", // The command that caused the error
  "message": "<DESCRIPTIVE_ERROR_MESSAGE>",     // Human-readable error description
  "code": "<ERROR_CODE>"                        // Optional, specific error code (e.g., "INVALID_COMMAND", "UNAUTHORIZED")
}
```

Clients should implement logic to display or log these errors appropriately.

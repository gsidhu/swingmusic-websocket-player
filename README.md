# Swing Music WebSocket Player

This project enables local music playback for the Swing Music web app, utilizing either browser APIs or a websocket connection for the device's default audio output via `vlc`. The services are designed to run on a headless Raspberry Pi 5.

With this setup, you can queue music from a Vue front-end running on your MacBook's browser and have it play on speakers connected to the Raspberry Pi. A 'keep alive' mechanism has been implemented on both the front-end and the server to ensure continuous music playback on the Pi even if the MacBook instance disconnects.

The Vue front-end hands over the playback queue to the server as an array of filepaths and the complete `tracklist` JSON object. The websocker server uses the filepaths array for playback. On reverse handover or when a new client connects, the `tracklist` object is passed to the client for populating the UI (queue, track metadata etc.).

## Development
This server relies on three main packages: VLC, Starlette, and Uvicorn.

You'll need to have VLC (or at least the `libvlc5` package) installed on your system. Install the Python packages from the `requirements.txt` file.

Run using: 
```python
# In development
python3 player.py
# In production
uvicorn player:app --host 0.0.0.0 --port 1971
```

The services run on these ports:
- **Core Swing Music App:** `http://localhost:1980`
- **Front-end Vue Client:** `http://localhost:5173`
- **WebSocket Server:** `ws://localhost:1971`

> [!NOTE]
> At the moment, this project only works with my fork of the [swingmusic webclient](https://github.com/gsidhu/webclient/tree/websocket-player).

## Why this project

This project was created to enable controlling music playback on a headless Raspberry Pi, which runs the core Swing Music app and is connected to a home theatre system. It allows any device connected to the home network (phone, tablet, computer) to control the playback queue on the server.

**Why VLC and not ffmpeg?**
The core swingmusic app already uses ffmpeg for silence detection so it makes sense for this server to use ffplay for playback control. Hence the [`player_ffmpeg.py`](./player_ffmpeg.py) script.

Unfortunately, in the ffmpeg version, both `seek()` and `set_volume()` functions work by stopping the current `ffplay` process and immediately starting a new one at the correct timestamp or with the new volume. This causes a noticeable audio gap and stutter during these operations. These are fundamental limitations of controlling playback in ffplay processes.

In comparison, VLC does a far better job in terms of playback (which makes sense).
# Swing Music WebSocket Player

This project enables local music playback for the Swing Music web app, utilizing either browser APIs or a websocket connection for the device's default audio output via `python-vlc`. The services are designed to run on a headless Raspberry Pi 5.

With this setup, you can queue music from a Vue front-end running on your MacBook's browser and have it play on speakers connected to the Raspberry Pi. A 'keep alive' mechanism has been implemented on both the front-end and the server to ensure continuous music playback on the Pi even if the MacBook instance disconnects.

The Vue front-end hands over the playback queue to the server as an array of filepaths and the complete `tracklist` JSON object. The websocker server uses the filepaths array for playback. On reverse handover or when a new client connects, the `tracklist` object is passed to the client for populating the UI (queue, track metadata etc.).

## Development Ports

- **Core Swing Music App:** `http://localhost:1980`
- **Front-end Vue Client:** `http://localhost:5173`
- **WebSocket Server:** `ws://localhost:1971`

> [!NOTE]
> At the moment, this project only works with my fork of the [swingmusic webclient](https://github.com/gsidhu/webclient/tree/websocket-player).

## Why this project

This project was created to enable controlling music playback on a headless Raspberry Pi, which runs the core Swing Music app and is connected to a home theatre system. It allows any device connected to the home network (phone, tablet, computer) to control the playback queue on the server.

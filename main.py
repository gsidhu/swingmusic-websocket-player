"""
This will be the main entry point of the application. It will import all the
necessary components from the other scripts, initialize the VLCPlayer instance,
set up the Starlette application with its WebSocket routes, and then concurrently
run both the Starlette WebSocket server and the aiohttp HLS HTTP server using
the run_servers function.
"""

import asyncio
import uvicorn
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute

from config import HLS_HTTP_PORT
from logger_setup import logger
from vlc_player import VLCPlayer
from websocket_handler import player_websocket_endpoint
from hls_server import start_hls_http_server

# Initialize the VLCPlayer instance (singleton)
player = VLCPlayer()

async def on_startup():
    player.start_status_broadcaster()

routes = [
    WebSocketRoute("/ws/player", endpoint=player_websocket_endpoint),
]

app = Starlette(routes=routes, on_startup=[on_startup])

async def run_servers():
    """Runs both the Starlette WebSocket server and the aiohttp HLS HTTP server concurrently."""
    # Set the HLS HTTP port in the VLCPlayer instance
    player.hls_http_port = HLS_HTTP_PORT

    # Start the Starlette server
    config = uvicorn.Config(app, host="0.0.0.0", port=1971, log_level="info")
    starlette_server = uvicorn.Server(config)
    starlette_task = asyncio.create_task(starlette_server.serve())

    # Start the aiohttp HLS HTTP server
    hls_server_runner = await start_hls_http_server("0.0.0.0", HLS_HTTP_PORT)
    
    # Keep servers running indefinitely
    await asyncio.gather(starlette_task, asyncio.Future()) # asyncio.Future() to keep the aiohttp server running

if __name__ == "__main__":
    asyncio.run(run_servers())

"""
This script implements the aiohttp HTTP server functionality. It includes the
hls_file_server_handler to serve HLS playlist (.m3u8) and segment (.ts) files
from the temporary directories managed by HLSStreamManager instances. It also
contains the start_hls_http_server function to set up and run this server.
"""

from aiohttp import web
from logger_setup import logger
from vlc_player import VLCPlayer # To access connected_clients and HLSStreamManager instances

player = VLCPlayer() # Get the singleton instance

async def hls_file_server_handler(request):
    """
    Handles requests for HLS playlist (.m3u8) and segment (.ts) files.
    """
    client_id = request.match_info.get('client_id')
    filename = request.match_info.get('filename')
    
    if not client_id or not filename:
        raise web.HTTPNotFound()

    # Prevent directory traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise web.HTTPForbidden()

    # Find the HLSStreamManager for the client
    client_session = player.connected_clients.get(client_id)
    if not client_session or not client_session.hls_manager:
        logger.warning(f"Request for HLS file for non-existent or non-streaming client: {client_id}")
        raise web.HTTPNotFound()

    file_path = client_session.hls_manager.temp_dir / filename

    if not file_path.is_file():
        logger.warning(f"HLS file not found: {file_path}")
        raise web.HTTPNotFound()

    logger.debug(f"Serving HLS file: {file_path}")
    response = web.FileResponse(file_path)
    response.headers['Access-Control-Allow-Origin'] = '*' # CORS for browser compatibility
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
    
    if filename.endswith(".m3u8"):
        response.headers['Content-Type'] = 'application/x-mpegURL'
    elif filename.endswith(".ts"):
        response.headers['Content-Type'] = 'video/MP2T'
    
    return response

async def start_hls_http_server(host: str, port: int):
    """Starts the aiohttp HTTP server for serving HLS files."""
    hls_app = web.Application()
    hls_app.router.add_get("/{client_id}/{filename}", hls_file_server_handler)
    
    runner = web.AppRunner(hls_app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    logger.info(f"Starting HLS HTTP server on http://{host}:{port}")
    await site.start()
    return runner # Return runner to keep it alive

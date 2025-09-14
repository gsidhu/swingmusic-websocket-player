"""
This script centralizes all configuration variables for the Swing Music WebSocket Player.
It provides a single place to manage application-wide settings, making it easier to
modify configurations without touching core logic.
"""

import logging

# Configuration
LOG_LEVEL = logging.INFO
HLS_HTTP_PORT = 8000 # Port for the HLS HTTP server

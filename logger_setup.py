"""
This script handles the initial setup of the application's logging system.
It configures the basic logging format and level, ensuring consistent logging
behavior across all other modules.
"""

import logging
from config import LOG_LEVEL

# Logging Setup
logging.basicConfig(
    level=LOG_LEVEL, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

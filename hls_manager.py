"""
This script contains the HLSStreamManager class, which is responsible for managing
the lifecycle of individual HLS streams. This includes creating and cleaning up
temporary directories for HLS segments, constructing and executing FFmpeg commands,
and monitoring the FFmpeg subprocess. It also defines the HLS_TEMP_DIR constant.
"""

import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

import psutil
from logger_setup import logger
from config import HLS_HTTP_PORT

HLS_TEMP_DIR = Path("/tmp/hls_streams")
HLS_TEMP_DIR.mkdir(exist_ok=True)

class HLSStreamManager:
    """
    Manages the lifecycle of a single HLS stream for a client.
    Handles FFmpeg process, temporary directory, and HLS file serving.
    """
    def __init__(self, client_id: str, input_path: Path, http_port: int = HLS_HTTP_PORT):
        self.client_id = client_id
        self.input_path = input_path
        self.http_port = http_port
        self.stream_id = str(uuid.uuid4())
        self.temp_dir = HLS_TEMP_DIR / self.stream_id
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_process: Optional[asyncio.subprocess.Process] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self.current_position: float = 0.0
        self.duration: float = 0.0
        self.is_active: bool = False
        self.state: str = "stopped" # e.g., "playing", "buffering", "stopped", "error"
        self.quality: str = "unknown"
        self.last_error: Optional[Dict[str, Any]] = None # To store the last HLS-specific error
        logger.info(f"HLSStreamManager initialized for client {client_id}, stream {self.stream_id}")

    async def start_stream(self, start_position: float = 0.0):
        """Constructs and launches the FFmpeg process for HLS streaming."""
        await self.stop_stream() # Ensure any existing stream is stopped and cleaned up
        self.last_error = None # Clear previous errors

        playlist_path = self.temp_dir / f"{self.stream_id}.m3u8"
        segment_path = self.temp_dir / f"{self.stream_id}_%03d.ts"

        # Create directory if it doesn't exist
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        ffmpeg_command = [
            "ffmpeg",
            "-nostdin",
            "-re",
        ]
        if start_position > 0:
            ffmpeg_command.extend(["-ss", str(start_position)])
        
        ffmpeg_command.extend([
            "-i", str(self.input_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-hls_time", "4",
            "-hls_list_size", "5",
            "-hls_flags", "delete_segments+independent_segments",
            "-y",
            "-hls_segment_filename", str(segment_path),
            str(playlist_path)
        ])

        logger.info(f"Starting FFmpeg for client {self.client_id}: {' '.join(ffmpeg_command)}")
        try:
            self.ffmpeg_process = await asyncio.create_subprocess_exec(
                *ffmpeg_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self._monitor_task = asyncio.create_task(self._monitor_ffmpeg_process())
            self.is_active = True
            self.state = "playing"
            self.current_position = start_position
            logger.info(f"FFmpeg process started with PID {self.ffmpeg_process.pid}")
        except FileNotFoundError:
            error_msg = "FFmpeg not found. Please ensure FFmpeg is installed and in your PATH."
            logger.error(error_msg)
            self.ffmpeg_process = None
            self.state = "error"
            self.last_error = {"code": "FFMPEG_NOT_FOUND", "message": error_msg}
        except Exception as e:
            error_msg = f"Error starting FFmpeg process: {e}"
            logger.error(error_msg, exc_info=True)
            self.ffmpeg_process = None
            self.state = "error"
            self.last_error = {"code": "FFMPEG_START_FAILED", "message": error_msg}

    async def _monitor_ffmpeg_process(self):
        """Monitors the FFmpeg process and logs its output/errors."""
        if not self.ffmpeg_process:
            return

        while self.ffmpeg_process and self.ffmpeg_process.returncode is None:
            try:
                stdout_line = b""
                stderr_line = b""

                if self.ffmpeg_process.stdout:
                    stdout_line = await self.ffmpeg_process.stdout.readline()
                if self.ffmpeg_process.stderr:
                    stderr_line = await self.ffmpeg_process.stderr.readline()

                if stdout_line:
                    logger.debug(f"FFmpeg stdout ({self.client_id}): {stdout_line.decode().strip()}")
                if stderr_line:
                    decoded_stderr = stderr_line.decode().strip()
                    logger.debug(f"FFmpeg stderr ({self.client_id}): {decoded_stderr}")
                    
                    # Basic parsing for duration
                    if "Duration:" in decoded_stderr and self.duration == 0:
                        try:
                            duration_str = decoded_stderr.split("Duration:")[1].split(",")[0].strip()
                            h, m, s = map(float, duration_str.split(':'))
                            self.duration = h * 3600 + m * 60 + s
                            logger.info(f"Detected media duration for client {self.client_id}: {self.duration}s")
                        except Exception as parse_e:
                            logger.warning(f"Could not parse duration from FFmpeg stderr: {parse_e}")
                    
                    # Basic parsing for current time (very rudimentary, needs more robust regex)
                    if "time=" in decoded_stderr:
                        try:
                            time_str = decoded_stderr.split("time=")[1].split(" ")[0].strip()
                            h, m, s = map(float, time_str.split(':'))
                            self.current_position = h * 3600 + m * 60 + s
                        except Exception:
                            pass # Ignore parsing errors for time for now

                    # Basic parsing for quality (e.g., bitrate)
                    if "bitrate=" in decoded_stderr:
                        try:
                            bitrate_str = decoded_stderr.split("bitrate=")[1].split(" ")[0].strip()
                            self.quality = bitrate_str
                        except Exception:
                            pass # Ignore parsing errors for quality for now

                await asyncio.sleep(1) # Check every second
            except asyncio.CancelledError:
                logger.info(f"FFmpeg monitor task cancelled for client {self.client_id}.")
                break
            except Exception as e:
                error_msg = f"Error monitoring FFmpeg process for client {self.client_id}: {e}"
                logger.error(error_msg, exc_info=True)
                self.state = "error"
                self.last_error = {"code": "FFMPEG_MONITOR_ERROR", "message": error_msg}
                break

        if self.ffmpeg_process and self.ffmpeg_process.returncode is not None:
            logger.warning(f"FFmpeg process for client {self.client_id} exited with code {self.ffmpeg_process.returncode}")
            if self.ffmpeg_process.returncode != 0:
                stderr_output = ""
                if self.ffmpeg_process.stderr:
                    stderr_output = (await self.ffmpeg_process.stderr.read()).decode()
                    logger.error(f"FFmpeg error output for client {self.client_id}:\n{stderr_output}")
                self.state = "error"
                self.last_error = {"code": "FFMPEG_PROCESS_FAILED", "message": f"FFmpeg exited with code {self.ffmpeg_process.returncode}.", "details": stderr_output}
            else:
                self.state = "stopped" # Process exited cleanly
        
        # Ensure cleanup if process exits unexpectedly
        await self.stop_stream()

    async def stop_stream(self):
        """Terminates the FFmpeg process and cleans up temporary files."""
        if self._monitor_task:
            self._monitor_task.cancel()
            await asyncio.gather(self._monitor_task, return_exceptions=True) # Wait for cancellation

        if self.ffmpeg_process and self.ffmpeg_process.returncode is None:
            logger.info(f"Terminating FFmpeg process {self.ffmpeg_process.pid} for client {self.client_id}.")
            try:
                # Use psutil to kill the process tree
                process = psutil.Process(self.ffmpeg_process.pid)
                for proc in process.children(recursive=True):
                    proc.kill()
                process.kill()
                await self.ffmpeg_process.wait() # Wait for the process to actually terminate
                logger.info(f"FFmpeg process {self.ffmpeg_process.pid} terminated.")
            except psutil.NoSuchProcess:
                logger.warning(f"FFmpeg process {self.ffmpeg_process.pid} already gone.")
            except Exception as e:
                error_msg = f"Error terminating FFmpeg process {self.ffmpeg_process.pid}: {e}"
                logger.error(error_msg, exc_info=True)
                if not self.last_error: # Only set if no other error was more specific
                    self.last_error = {"code": "FFMPEG_TERMINATION_ERROR", "message": error_msg}
        
        if self.temp_dir.exists():
            logger.info(f"Cleaning up temporary HLS directory: {self.temp_dir}")
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        self.ffmpeg_process = None
        self.is_active = False
        self.state = "stopped"
        self.current_position = 0.0
        self.duration = 0.0
        self.quality = "unknown"
        logger.info(f"HLS stream stopped and cleaned up for client {self.client_id}.")

    def get_playlist_url(self) -> str:
        """Returns the URL for the HLS playlist."""
        return f"http://localhost:{self.http_port}/{self.client_id}/{self.stream_id}.m3u8"

    async def seek_stream(self, seek_position: float) -> bool:
        """
        Seeks the HLS stream by stopping and restarting FFmpeg with a new -ss parameter.
        """
        if not self.is_active:
            logger.warning(f"Cannot seek, HLS stream not active for client {self.client_id}.")
            self.last_error = {"code": "HLS_SEEK_FAILED", "message": "Cannot seek, HLS stream not active."}
            return False
        
        logger.info(f"Seeking HLS stream for client {self.client_id} to {seek_position}s. Restarting FFmpeg.")
        await self.start_stream(start_position=seek_position)
        if not self.is_active:
            self.last_error = {"code": "HLS_SEEK_FAILED", "message": "Failed to restart stream for seeking."}
        return self.is_active # Return true if restart was successful

    async def get_stream_status(self) -> dict:
        """
        Gathers and returns the current status of the HLS stream.
        """
        status = {
            "is_active": self.is_active,
            "track_id": str(self.input_path), # Assuming input_path is the track_id for now
            "hls_url": self.get_playlist_url() if self.is_active else None,
            "current_position": self.current_position,
            "duration": self.duration,
            "state": self.state,
            "quality": self.quality,
            "process_health": "running" if self.ffmpeg_process and self.ffmpeg_process.returncode is None else "stopped",
            "last_error": self.last_error
        }
        return status

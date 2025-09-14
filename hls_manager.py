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
from typing import Optional

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
        logger.info(f"HLSStreamManager initialized for client {client_id}, stream {self.stream_id}")

    async def start_stream(self):
        """Constructs and launches the FFmpeg process for HLS streaming."""
        playlist_path = self.temp_dir / f"{self.stream_id}.m3u8"
        segment_path = self.temp_dir / f"{self.stream_id}_%03d.ts"

        # FFmpeg command for HLS generation
        # -nostdin: Prevents FFmpeg from waiting for input on stdin
        # -re: Read input at native frame rate
        # -i "{input_path}": Input file
        # -c:v copy: Copy video codec (no re-encoding)
        # -c:a aac -b:a 192k: Encode audio to AAC at 192kbps
        # -hls_time 4: Segment duration of 4 seconds
        # -hls_list_size 5: Keep 5 segments in the playlist
        # -hls_flags delete_segments+independent_segments: Delete old segments, ensure segments are independent
        # -y: Overwrite output files without asking
        # -hls_segment_filename "{segment_path}": Pattern for segment filenames
        # "{playlist_path}": Output playlist filename
        ffmpeg_command = [
            "ffmpeg",
            "-nostdin",
            "-re",
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
        ]

        logger.info(f"Starting FFmpeg for client {self.client_id}: {' '.join(ffmpeg_command)}")
        try:
            self.ffmpeg_process = await asyncio.create_subprocess_exec(
                *ffmpeg_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self._monitor_task = asyncio.create_task(self._monitor_ffmpeg_process())
            logger.info(f"FFmpeg process started with PID {self.ffmpeg_process.pid}")
        except FileNotFoundError:
            logger.error("FFmpeg not found. Please ensure FFmpeg is installed and in your PATH.")
            self.ffmpeg_process = None
        except Exception as e:
            logger.error(f"Error starting FFmpeg process: {e}", exc_info=True)
            self.ffmpeg_process = None

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
                    logger.debug(f"FFmpeg stderr ({self.client_id}): {stderr_line.decode().strip()}")

                await asyncio.sleep(1) # Check every second
            except asyncio.CancelledError:
                logger.info(f"FFmpeg monitor task cancelled for client {self.client_id}.")
                break
            except Exception as e:
                logger.error(f"Error monitoring FFmpeg process for client {self.client_id}: {e}", exc_info=True)
                break

        if self.ffmpeg_process and self.ffmpeg_process.returncode is not None:
            logger.warning(f"FFmpeg process for client {self.client_id} exited with code {self.ffmpeg_process.returncode}")
            if self.ffmpeg_process.returncode != 0:
                if self.ffmpeg_process.stderr:
                    stderr_output = (await self.ffmpeg_process.stderr.read()).decode()
                    logger.error(f"FFmpeg error output for client {self.client_id}:\n{stderr_output}")
        
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
                logger.error(f"Error terminating FFmpeg process {self.ffmpeg_process.pid}: {e}", exc_info=True)
        
        if self.temp_dir.exists():
            logger.info(f"Cleaning up temporary HLS directory: {self.temp_dir}")
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        self.ffmpeg_process = None
        logger.info(f"HLS stream stopped and cleaned up for client {self.client_id}.")

    def get_playlist_url(self) -> str:
        """Returns the URL for the HLS playlist."""
        return f"http://localhost:{self.http_port}/{self.client_id}/{self.stream_id}.m3u8"

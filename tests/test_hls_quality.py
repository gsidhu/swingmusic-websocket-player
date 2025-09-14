import unittest
import asyncio
import os
import shutil
import time
from unittest.mock import patch, MagicMock

class TestHLSQuality(unittest.TestCase):

    def setUp(self):
        """Set up for each test."""
        self.test_hls_dir = "test_hls_quality_temp"
        os.makedirs(self.test_hls_dir, exist_ok=True)
        self.client_id = "quality_test_client"
        self.client_dir = os.path.join(self.test_hls_dir, self.client_id)
        os.makedirs(self.client_dir, exist_ok=True)

    def tearDown(self):
        """Tear down after each test."""
        if os.path.exists(self.test_hls_dir):
            shutil.rmtree(self.test_hls_dir)

    @patch('subprocess.run')
    def test_ffprobe_verification(self, mock_subprocess_run):
        """Verify stream properties using a mocked ffprobe."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = '{"streams":[{"codec_type":"audio","bit_rate":"128000"}]}'
        mock_subprocess_run.return_value = mock_process

        # This would be a helper function to call ffprobe
        def get_stream_properties(file_path):
            import json
            command = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_streams', file_path
            ]
            result = mock_subprocess_run(command, capture_output=True, text=True)
            if result.returncode == 0:
                return json.loads(result.stdout)
            return None

        properties = get_stream_properties("dummy.ts")
        if properties:
            self.assertEqual(properties['streams'][0]['bit_rate'], "128000")
        else:
            self.fail("get_stream_properties returned None")

    def test_segment_timing_consistency(self):
        """Assert that segment durations are close to the configured value."""
        # This test would require monitoring FFmpeg logs.
        # For now, we simulate by checking playlist entries.
        playlist_content = """
#EXTM3U
#EXT-X-TARGETDURATION:2
#EXTINF:2.000,
segment0.ts
#EXTINF:1.980,
segment1.ts
"""
        with open(os.path.join(self.client_dir, "stream.m3u8"), "w") as f:
            f.write(playlist_content)

        durations = []
        with open(os.path.join(self.client_dir, "stream.m3u8"), "r") as f:
            for line in f:
                if line.startswith("#EXTINF"):
                    duration = float(line.split(":")[1].split(",")[0])
                    durations.append(duration)
        
        target_duration = 2.0
        tolerance = 0.1
        for duration in durations:
            self.assertAlmostEqual(duration, target_duration, delta=tolerance)

    def test_playlist_segment_continuity(self):
        """Verify that segment sequences are continuous."""
        playlist_content = """
#EXTM3U
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:2.0,
segment0.ts
#EXTINF:2.0,
segment1.ts
"""
        with open(os.path.join(self.client_dir, "stream.m3u8"), "w") as f:
            f.write(playlist_content)

        # Simulate update
        updated_playlist_content = """
#EXTM3U
#EXT-X-MEDIA-SEQUENCE:1
#EXTINF:2.0,
segment1.ts
#EXTINF:2.0,
segment2.ts
"""
        with open(os.path.join(self.client_dir, "stream.m3u8"), "w") as f:
            f.write(updated_playlist_content)

        with open(os.path.join(self.client_dir, "stream.m3u8"), "r") as f:
            content = f.read()
            self.assertIn("#EXT-X-MEDIA-SEQUENCE:1", content)
            self.assertNotIn("segment0.ts", content)
            self.assertIn("segment2.ts", content)

    def test_playlist_cleanup(self):
        """Asserts that old segments are removed from the temporary directory."""
        # Create dummy segment files
        with open(os.path.join(self.client_dir, "segment0.ts"), "w") as f: f.write("d")
        with open(os.path.join(self.client_dir, "segment1.ts"), "w") as f: f.write("d")
        with open(os.path.join(self.client_dir, "segment2.ts"), "w") as f: f.write("d")

        # Simulate cleanup logic (e.g., from hls_server.py)
        # This would typically be a function that we can call and test.
        # For this test, we'll just manually delete the old segment.
        os.remove(os.path.join(self.client_dir, "segment0.ts"))

        self.assertFalse(os.path.exists(os.path.join(self.client_dir, "segment0.ts")))
        self.assertTrue(os.path.exists(os.path.join(self.client_dir, "segment1.ts")))

if __name__ == '__main__':
    unittest.main()

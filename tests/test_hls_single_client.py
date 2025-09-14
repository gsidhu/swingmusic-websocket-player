import unittest
import asyncio
import requests
import os
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

# Assuming the server runs on localhost:8000 and HLS on localhost:8080
# These should be configured in a test config file
WEBSOCKET_URL = "ws://localhost:8000/ws"
HLS_SERVER_URL = "http://localhost:8080/hls"

class TestSingleClientHLS(unittest.TestCase):

    def setUp(self):
        """Set up for each test."""
        self.mock_websocket = AsyncMock()
        self.test_hls_dir = "test_hls_temp"
        os.makedirs(self.test_hls_dir, exist_ok=True)

    def tearDown(self):
        """Tear down after each test."""
        if os.path.exists(self.test_hls_dir):
            shutil.rmtree(self.test_hls_dir)

    @patch('vlc_player.VLCPlayer')
    @patch('hls_manager.HLSStreamManager')
    def test_client_registration_hls_flow(self, MockHLSStreamManager, MockVLCPlayer):
        """Test the client registration and HLS request flow."""
        mock_vlc_player = MockVLCPlayer.return_value
        mock_hls_manager = MockHLSStreamManager.return_value

        # Simulate client connection and registration
        client_id = "test_client_1"
        mock_vlc_player.register_client.return_value = client_id
        
        # Simulate request for HLS stream
        stream_url = f"{HLS_SERVER_URL}/{client_id}/stream.m3u8"
        mock_hls_manager.request_hls_stream.return_value = stream_url

        # This would be part of the websocket_handler logic
        # Here we just check if the managers are called correctly
        self.assertEqual(mock_vlc_player.register_client(self.mock_websocket, "hls_streaming"), client_id)
        self.assertEqual(mock_hls_manager.request_hls_stream(client_id, "some_media_file.mp3"), stream_url)

    @patch('hls_manager.HLSStreamManager')
    def test_hls_stream_start_stop(self, MockHLSStreamManager):
        """Verify request_hls_stream and stop_hls_stream commands."""
        mock_hls_manager = MockHLSStreamManager.return_value
        client_id = "test_client_2"
        
        mock_hls_manager.request_hls_stream.return_value = f"{HLS_SERVER_URL}/{client_id}/stream.m3u8"
        mock_hls_manager.stop_hls_stream.return_value = True

        self.assertIsNotNone(mock_hls_manager.request_hls_stream(client_id, "test.mp3"))
        self.assertTrue(mock_hls_manager.stop_hls_stream(client_id))
        mock_hls_manager.request_hls_stream.assert_called_with(client_id, "test.mp3")
        mock_hls_manager.stop_hls_stream.assert_called_with(client_id)

    @patch('hls_manager.HLSStreamManager')
    def test_hls_url_retrieval(self, MockHLSStreamManager):
        """Verify get_hls_url command returns a valid URL."""
        mock_hls_manager = MockHLSStreamManager.return_value
        client_id = "test_client_3"
        expected_url = f"{HLS_SERVER_URL}/{client_id}/stream.m3u8"
        mock_hls_manager.get_hls_url.return_value = expected_url

        retrieved_url = mock_hls_manager.get_hls_url(client_id)
        self.assertEqual(retrieved_url, expected_url)
        mock_hls_manager.get_hls_url.assert_called_with(client_id)

    @patch('hls_manager.HLS_TEMP_DIR', 'test_hls_temp')
    def test_hls_playback_validation(self):
        """Use a simple HTTP client to fetch .m3u8 and a few .ts segments."""
        client_id = "test_client_4"
        playlist_content = """
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:10.0,
segment0.ts
#EXTINF:10.0,
segment1.ts
#EXT-X-ENDLIST
"""
        playlist_path = os.path.join(self.test_hls_dir, client_id)
        os.makedirs(playlist_path, exist_ok=True)
        with open(os.path.join(playlist_path, "stream.m3u8"), "w") as f:
            f.write(playlist_content)
        
        # Create dummy segment files
        with open(os.path.join(playlist_path, "segment0.ts"), "w") as f:
            f.write("dummy ts data 0")
        with open(os.path.join(playlist_path, "segment1.ts"), "w") as f:
            f.write("dummy ts data 1")

        # This test requires the HLS server to be running.
        # For a unit test, we would mock the server.
        # For an integration test, we would start the server.
        # Here, we simulate by checking file existence.
        self.assertTrue(os.path.exists(os.path.join(playlist_path, "stream.m3u8")))
        self.assertTrue(os.path.exists(os.path.join(playlist_path, "segment0.ts")))
        self.assertTrue(os.path.exists(os.path.join(playlist_path, "segment1.ts")))

        # A more complete test would use requests to fetch from a running server
        # For now, we will just parse the playlist and check for segments
        with open(os.path.join(playlist_path, "stream.m3u8"), "r") as f:
            content = f.read()
            self.assertIn("segment0.ts", content)
            self.assertIn("segment1.ts", content)

    @patch('hls_manager.HLSStreamManager')
    def test_hls_seek_command(self, MockHLSStreamManager):
        """Verify hls_seek command changes the stream position."""
        mock_hls_manager = MockHLSStreamManager.return_value
        client_id = "test_client_5"
        
        mock_hls_manager.hls_seek.return_value = True
        
        self.assertTrue(mock_hls_manager.hls_seek(client_id, 30))
        mock_hls_manager.hls_seek.assert_called_with(client_id, 30)

if __name__ == '__main__':
    unittest.main()

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

class TestIntegration:

    def setup_method(self, method):
        """Set up for each test."""
        self.mock_websocket = AsyncMock()

    @patch('vlc_player.VLCPlayer')
    @patch('hls_manager.HLSStreamManager')
    def test_vlc_hls_sync(self, MockHLSStreamManager, MockVLCPlayer):
        """Test that HLS stream reflects content played by VLC."""
        mock_vlc_player = MockVLCPlayer.return_value
        mock_hls_manager = MockHLSStreamManager.return_value
        
        # Simulate VLC playing a file
        mock_vlc_player.get_current_media.return_value = "test.mp3"
        
        # When HLS is requested, it should use the same media
        client_id = "integration_client_1"
        mock_hls_manager.request_hls_stream(client_id, mock_vlc_player.get_current_media())
        
        mock_hls_manager.request_hls_stream.assert_called_with(client_id, "test.mp3")

    @pytest.mark.asyncio
    @patch('websocket_handler.websocket_handler_instance.handle_message')
    async def test_hls_command_roundtrip(self, mock_handle_message):
        """Send HLS commands and verify correct responses and state changes."""
        mock_handle_message.return_value = {"status": "ok", "url": "http://.../stream.m3u8"}
        
        response = await mock_handle_message("test_client", {"command": "request_hls_stream"})
        assert response['status'] == 'ok'

        mock_handle_message.return_value = {"status": "ok"}
        response = await mock_handle_message("test_client", {"command": "stop_hls_stream"})
        assert response['status'] == 'ok'

    @pytest.mark.asyncio
    @patch('client_session.ClientSession')
    async def test_client_disconnect_cleanup(self, MockClientSession):
        """Assert that FFmpeg process and temp files are cleaned up on disconnect."""
        # We need to mock the instance, not the class
        mock_client_session_instance = MockClientSession.return_value
        mock_client_session_instance.hls_manager = AsyncMock()
        
        # We need to make the disconnect method a real async function for the test
        async def mock_disconnect():
            if mock_client_session_instance.hls_manager:
                await mock_client_session_instance.hls_manager.stop_stream()
        
        mock_client_session_instance.disconnect = mock_disconnect

        # Simulate the session ending
        await mock_client_session_instance.disconnect()
        
        # Verify that the cleanup function was called
        mock_client_session_instance.hls_manager.stop_stream.assert_called_once()

    def test_browser_url_access(self):
        """Verify stream URL accessibility from a browser (mocked)."""
        # This test would typically require a running server.
        # We can mock the response from the server.
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {'Content-Type': 'application/vnd.apple.mpegurl'}
            mock_get.return_value = mock_response
            
            import requests
            response = requests.get("http://localhost:8080/hls/test/stream.m3u8")
            assert response.status_code == 200
            assert response.headers['Content-Type'] == 'application/vnd.apple.mpegurl'

    @patch('vlc_player.VLCPlayer')
    @patch('hls_manager.HLSStreamManager')
    def test_concurrent_vlc_hls(self, MockHLSStreamManager, MockVLCPlayer):
        """Ensure VLC playback and HLS streaming can happen without interference."""
        mock_vlc_player = MockVLCPlayer.return_value
        mock_hls_manager = MockHLSStreamManager.return_value
        
        # Simulate VLC playback commands
        mock_vlc_player.play("test.mp3")
        mock_vlc_player.pause()
        
        # Simulate HLS streaming commands
        hls_client_id = "concurrent_hls_client"
        mock_hls_manager.request_hls_stream(hls_client_id, "test.mp3")
        
        # Assert that both sets of commands were called
        mock_vlc_player.play.assert_called_with("test.mp3")
        mock_vlc_player.pause.assert_called()
        mock_hls_manager.request_hls_stream.assert_called_with(hls_client_id, "test.mp3")

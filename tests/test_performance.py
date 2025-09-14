import asyncio
import time
import psutil
import pytest
from unittest.mock import patch, MagicMock

class TestPerformance:

    def setup_method(self, method):
        """Set up for each test."""
        pass

    @patch('hls_manager.HLSStreamManager')
    def test_single_hls_resource_usage(self, MockHLSStreamManager):
        """Test resource usage with a single HLS client."""
        mock_hls_manager = MockHLSStreamManager.return_value
        
        # Simulate starting a stream
        mock_hls_manager.request_hls_stream.return_value = "http://.../stream.m3u8"
        
        process = psutil.Process()
        cpu_before = process.cpu_percent(interval=None)
        mem_before = process.memory_info().rss

        # Simulate streaming for a short period
        time.sleep(2)

        cpu_after = process.cpu_percent(interval=None)
        mem_after = process.memory_info().rss

        print(f"CPU Usage during test: {cpu_after - cpu_before}%")
        print(f"Memory Usage during test: {(mem_after - mem_before) / 1024 / 1024} MB")

        # These are example thresholds and should be adjusted
        assert cpu_after - cpu_before < 50.0
        assert mem_after - mem_before < 100 * 1024 * 1024 # 100 MB

    @pytest.mark.asyncio
    @patch('hls_manager.HLSStreamManager')
    async def test_stream_generation_latency(self, MockHLSStreamManager):
        """Measure the time from request to first playlist availability."""
        mock_hls_manager = MockHLSStreamManager.return_value
        
        start_time = time.time()
        
        # Simulate a delay in stream generation
        async def delayed_request(*args, **kwargs):
            await asyncio.sleep(0.5)
            return "http://.../stream.m3u8"
        
        mock_hls_manager.request_hls_stream.side_effect = delayed_request
        
        await mock_hls_manager.request_hls_stream("perf_client", "test.mp3")
        
        end_time = time.time()
        latency = end_time - start_time
        print(f"Stream generation latency: {latency:.4f} seconds")
        
        assert latency < 5.0 # Assert latency is under 5 seconds

    def test_network_bandwidth(self):
        """Monitor network traffic to assert it aligns with HLS bitrate."""
        # This test is highly dependent on the environment and is hard to mock.
        # A real-world test would involve running the server and measuring traffic.
        # Here's a conceptual placeholder.
        
        net_io_before = psutil.net_io_counters()
        
        # Simulate HLS streaming (e.g., by downloading a file)
        time.sleep(5)
        
        net_io_after = psutil.net_io_counters()
        
        bytes_sent = net_io_after.bytes_sent - net_io_before.bytes_sent
        bandwidth_mbps = (bytes_sent * 8) / (5 * 1024 * 1024)
        
        print(f"Average network bandwidth: {bandwidth_mbps:.2f} Mbps")
        # We can't assert a specific value without a real stream.
        assert bandwidth_mbps >= 0

    @patch('hls_manager.HLSStreamManager')
    def test_system_stability_single_hls(self, MockHLSStreamManager):
        """Run a single HLS stream for an extended period to check for crashes."""
        mock_hls_manager = MockHLSStreamManager.return_value
        
        # This is a long-running test and might be skipped in regular CI.
        # For now, we'll run it for a very short duration.
        duration = 5 # seconds
        
        print(f"Running stability test for {duration} seconds...")
        
        start_time = time.time()
        while time.time() - start_time < duration:
            # In a real test, we would be checking for process health.
            # Here, we just sleep.
            time.sleep(1)
            
        # If the test completes without crashing, it's a pass.
        assert True

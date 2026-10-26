import asyncio
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))
from usability.network import BoundaryError, BrowserProxy, NetworkBoundary, global_ip, parse_url


class UrlTests(unittest.TestCase):
    def test_non_web_credentials_and_nonstandard_ports_are_rejected(self):
        for url in ("file:///etc/passwd", "javascript:alert(1)", "http://secret@example.com", "http://example.com:8080", "http://example.com\n/private"):
            with self.assertRaises(BoundaryError): parse_url(url)

    def test_private_reserved_and_mapped_addresses_are_rejected(self):
        for ip in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "192.168.1.1", "100.64.0.1", "::1", "::ffff:127.0.0.1", "224.0.0.1"):
            self.assertFalse(global_ip(ip), ip)


class Writer:
    def __init__(self): self.data = b""; self.closed = False
    def write(self, data): self.data += data
    def close(self): self.closed = True
    def is_closing(self): return self.closed
    async def drain(self): pass


class NetworkTests(unittest.IsolatedAsyncioTestCase):
    def address(self, ip): return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

    async def test_dns_rebinding_to_private_address_is_blocked_at_connect(self):
        boundary = NetworkBoundary()
        with patch("socket.getaddrinfo", side_effect=[self.address("93.184.216.34"), self.address("127.0.0.1")]):
            await boundary.endpoint("https://example.com/")
            reader = asyncio.StreamReader()
            reader.feed_data(b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
            reader.feed_eof()
            writer = Writer()
            with patch("asyncio.open_connection", new_callable=AsyncMock) as connect:
                await BrowserProxy(boundary)._handle(reader, writer)
                connect.assert_not_called()
            self.assertIn(b"403", writer.data)

    async def test_proxy_connects_to_checked_ip_not_hostname(self):
        reader = asyncio.StreamReader()
        reader.feed_data(b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
        reader.feed_eof()
        remote = asyncio.StreamReader()
        remote.feed_eof()
        with patch("socket.getaddrinfo", return_value=self.address("93.184.216.34")):
            with patch("asyncio.open_connection", new_callable=AsyncMock, return_value=(remote, Writer())) as connect:
                await BrowserProxy(NetworkBoundary())._handle(reader, Writer())
                connect.assert_awaited_once_with("93.184.216.34", 443)


if __name__ == "__main__": unittest.main()

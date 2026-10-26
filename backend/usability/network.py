"""Browser egress for local read-only website tests.

The proxy resolves and connects to a checked literal IP, avoiding a second
browser DNS lookup. HTTPS methods are additionally checked by Playwright.
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit


class BoundaryError(ValueError):
    pass


def parse_url(url: str):
    if not isinstance(url, str) or len(url) > 4096 or any(ord(c) < 33 for c in url):
        raise BoundaryError("Enter a complete http or https URL without spaces")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise BoundaryError("Use an http or https URL without embedded credentials")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise BoundaryError("URL port is invalid") from None
    if port not in {80, 443}:
        raise BoundaryError("Public tests currently support standard web ports only")
    return parts


def origin(url: str) -> tuple:
    p = urlsplit(url)
    return p.scheme, p.hostname, p.port or (443 if p.scheme == "https" else 80)


def global_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


class NetworkBoundary:
    def __init__(self, demo_url: str | None = None):
        self.demo_url = demo_url

    async def public_address(self, host: str, port: int) -> str:
        try:
            addresses = await asyncio.wait_for(
                asyncio.to_thread(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM), 5)
        except (OSError, asyncio.TimeoutError):
            raise BoundaryError("The website address could not be resolved") from None
        ips = list(dict.fromkeys(item[4][0] for item in addresses))
        if not ips or any(not global_ip(ip) for ip in ips):
            raise BoundaryError("Private, local, and reserved network addresses are blocked")
        # Prefer IPv4 where both stacks are published.
        return sorted(ips, key=lambda ip: ":" in ip)[0]

    async def endpoint(self, url: str) -> tuple[str, int]:
        if self.demo_url and url.split("#", 1)[0] == self.demo_url:
            p = urlsplit(url)
            return "127.0.0.1", p.port
        p = parse_url(url)
        port = p.port or (443 if p.scheme == "https" else 80)
        return await self.public_address(p.hostname, port), port


class BrowserProxy:
    def __init__(self, boundary: NetworkBoundary):
        self.boundary = boundary
        self.tasks = set()

    async def __aenter__(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0, limit=65536)
        self.url = f"http://127.0.0.1:{self.server.sockets[0].getsockname()[1]}"
        return self

    async def __aexit__(self, *args):
        self.server.close()
        await self.server.wait_closed()
        pending = list(self.tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def _handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        upstream = None
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
            first, *headers = header.decode("latin-1").split("\r\n")
            method, target, version = first.split(" ", 2)
            if method == "CONNECT":
                p = parse_url("https://" + target)
                port = p.port or 443
                ip = await self.boundary.public_address(p.hostname, port)
                remote, upstream = await asyncio.wait_for(asyncio.open_connection(ip, port), 10)
                writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            elif method in {"GET", "HEAD"}:
                ip, port = await self.boundary.endpoint(target)
                p = urlsplit(target)
                remote, upstream = await asyncio.wait_for(asyncio.open_connection(ip, port), 10)
                path = urlunsplit(("", "", p.path or "/", p.query, ""))
                safe = [h for h in headers if h and h.split(":", 1)[0].lower() not in {
                    "host", "connection", "proxy-connection", "proxy-authorization", "upgrade"}]
                outgoing = "\r\n".join([f"{method} {path} {version}", f"Host: {p.netloc}", *safe, "Connection: close", "", ""])
                upstream.write(outgoing.encode("latin-1"))
                await upstream.drain()
            else:
                raise BoundaryError("Only read-only requests are allowed")
            await writer.drain()

            async def relay(source, destination):
                while data := await source.read(65536):
                    destination.write(data)
                    await destination.drain()
            a = asyncio.create_task(relay(reader, upstream))
            b = asyncio.create_task(relay(remote, writer))
            try:
                done, pending = await asyncio.wait((a, b), return_when=asyncio.FIRST_COMPLETED)
                for finished in done:
                    finished.result()
            finally:
                a.cancel()
                b.cancel()
                await asyncio.gather(a, b, return_exceptions=True)
        except (OSError, ValueError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            if not writer.is_closing():
                writer.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
        finally:
            if upstream:
                upstream.close()
            writer.close()
            self.tasks.discard(task)

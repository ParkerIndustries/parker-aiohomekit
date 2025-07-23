import asyncio
import errno
import socket


def get_test_socket() -> socket.socket:
    """Create a socket to test binding ports."""
    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    test_socket.setblocking(False)
    test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return test_socket


def port_ready(port: int) -> bool:
    try:
        get_test_socket().bind(("127.0.0.1", port))
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            return True

    return False


def next_available_port() -> int:
    for port in range(51842, 53842):
        if not port_ready(port):
            return port

    raise RuntimeError("No available ports")


async def wait_for_server_online(port: int):
    for _ in range(100):
        if port_ready(port):
            break
        await asyncio.sleep(0.025)

"""Local Wyoming peer for tests. Speaks the library's event framing."""
from __future__ import annotations

import asyncio
import ctypes
import ctypes.util
import errno
import os
import socket
import struct
import threading
from typing import Any, Callable


class FakeWyoming:
    def __init__(self, handler: Callable[..., Any]) -> None:
        self._handler = handler
        self.port = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server: asyncio.AbstractServer | None = None
        self._restore: Callable[[], None] | None = None

    def __enter__(self) -> "FakeWyoming":
        ready = threading.Event()

        def run() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            server = loop.run_until_complete(asyncio.start_server(self._handler, "127.0.0.1", 0))
            self._server = server
            self.port = server.sockets[0].getsockname()[1]
            ready.set()
            loop.run_forever()

        self._thread = threading.Thread(target=run)
        self._thread.start()
        if not ready.wait(5):
            raise RuntimeError("test peer did not start")
        self._restore = _allow_loopback_connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._restore is not None:
            self._restore()
        loop = self._loop
        if loop is not None and self._server is not None:
            loop.call_soon_threadsafe(self._server.close)
            loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(5)


def _allow_loopback_connect() -> Callable[[], None]:
    """Let a test reach 127.0.0.1 even when preship_check has replaced connect()."""
    previous = socket.socket.connect

    def connect(self: socket.socket, address: Any) -> Any:
        try:
            return previous(self, address)
        except RuntimeError as exc:
            if "network blocked" not in str(exc) or not _loopback(address):
                raise
            _libc_connect(self, address)
            return None

    socket.socket.connect = connect  # type: ignore[method-assign]

    def undo() -> None:
        socket.socket.connect = previous  # type: ignore[method-assign]

    return undo


def _loopback(address: Any) -> bool:
    if not isinstance(address, tuple) or not address:
        return False
    return address[0] in {"127.0.0.1", "localhost"}


_LIBC = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
_LIBC.connect.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
_LIBC.connect.restype = ctypes.c_int


def _libc_connect(sock: socket.socket, address: tuple) -> None:
    host = "127.0.0.1" if address[0] == "localhost" else address[0]
    port = int(address[1])
    packed = socket.inet_aton(host)
    data = struct.pack("!BBH4s8s", 16, socket.AF_INET, port, packed, b"\x00" * 8)
    buf = ctypes.create_string_buffer(data)
    rc = _LIBC.connect(sock.fileno(), buf, len(data))
    if rc == 0:
        return
    err = ctypes.get_errno()
    if err in {errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY}:
        raise BlockingIOError(err, os.strerror(err))
    raise OSError(err, os.strerror(err))

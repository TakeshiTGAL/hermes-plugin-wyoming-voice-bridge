"""Host and port for one Wyoming server. Nothing here opens a socket."""
from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass

HOST_MAX = 253
_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int

    @property
    def label(self) -> str:
        return f"{self.host}:{self.port}"


class EndpointError(ValueError):
    pass


def _host_ok(host: str) -> bool:
    if not host or len(host) > HOST_MAX:
        return False
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in host):
        return False
    if any(ch in host for ch in "/@?#%\\[]"):
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    if host.endswith("."):
        return False
    labels = host.split(".")
    return all(_DNS_LABEL.fullmatch(label) for label in labels)


def _port_ok(raw: str) -> int | None:
    if not raw or not raw.isascii() or not raw.isdigit():
        return None
    if len(raw) > 1 and raw.startswith("0"):
        return None
    port = int(raw)
    if port < 1 or port > 65535:
        return None
    return port


def parse_endpoint(host: str | None, port: str | None) -> Endpoint:
    """Reject anything that is not a host and a decimal port. No scheme, path, or userinfo."""
    host = (host or "").strip()
    port_raw = (port or "").strip()
    if not host and not port_raw:
        raise EndpointError("Host and port are not set.")
    if not host:
        raise EndpointError("Host is not set.")
    if not port_raw:
        raise EndpointError("Port is not set.")
    if "://" in host or "://" in port_raw:
        raise EndpointError("Write a host and a port, not a URL.")
    if not _host_ok(host):
        raise EndpointError("Host must be a hostname or an IP address.")
    port = _port_ok(port_raw)
    if port is None:
        raise EndpointError("Port must be an integer from 1 to 65535.")
    return Endpoint(host=host, port=port)


def endpoint_from_env(prefix: str, env: dict[str, str] | None = None) -> Endpoint | None:
    """Return None when both variables are absent. Raise when one of them is set and invalid."""
    source = os.environ if env is None else env
    host = source.get(f"{prefix}_HOST")
    port = source.get(f"{prefix}_PORT")
    if (host is None or host.strip() == "") and (port is None or port.strip() == ""):
        return None
    try:
        return parse_endpoint(host, port)
    except EndpointError:
        raise


def tcp_uri(endpoint: Endpoint) -> str:
    host = endpoint.host
    if ":" in host:
        host = f"[{host}]"
    return f"tcp://{host}:{endpoint.port}"

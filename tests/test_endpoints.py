from endpoints import EndpointError, endpoint_from_env, parse_endpoint, tcp_uri


def test_host_and_port():
    got = parse_endpoint("whisper.local", "10300")
    assert got.host == "whisper.local"
    assert got.port == 10300
    assert tcp_uri(got) == "tcp://whisper.local:10300"


def test_ipv6_uri_is_bracketed():
    got = parse_endpoint("::1", "10300")
    assert tcp_uri(got) == "tcp://[::1]:10300"


def test_urls_and_schemes_are_refused():
    for host, port in (
        ("tcp://127.0.0.1", "10300"),
        ("127.0.0.1/secret", "10300"),
        ("user@host", "10300"),
        ("http://127.0.0.1", "80"),
        ("127.0.0.1", "tcp://1"),
        ("127.0.0.1", "080"),
        ("127.0.0.1", "0"),
        ("127.0.0.1", "65536"),
        ("", "10300"),
        ("127.0.0.1", ""),
        ("unix://tmp/socket", "1"),
        ("stdio://", "1"),
    ):
        try:
            parse_endpoint(host, port)
        except EndpointError:
            continue
        raise AssertionError(f"accepted {host!r} {port!r}")


def test_absent_env_is_unset_not_an_error():
    assert endpoint_from_env("WYOMING_STT", {}) is None


def test_half_set_env_is_an_error():
    try:
        endpoint_from_env("WYOMING_STT", {"WYOMING_STT_HOST": "127.0.0.1"})
    except EndpointError as exc:
        assert "Port" in str(exc)
    else:
        raise AssertionError("half set")

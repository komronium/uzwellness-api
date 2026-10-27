"""The tracked deploy files are the source of truth for the VPS.

These checks keep them consistent with each other and with the hardening the
live host depends on, so a careless edit is caught before it is copied over.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = ROOT / "deploy" / "systemd"
NGINX = ROOT / "deploy" / "nginx" / "api.uzwellness.com"
SOCKET = "/run/uzwellness/uvicorn.sock"


def _unit(name: str) -> dict[str, list[str]]:
    """Parse a systemd unit into {key: [values]} (keys may repeat)."""
    values: dict[str, list[str]] = {}
    text = (SYSTEMD / name).read_text().replace("\\\n", " ")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "[")) or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values.setdefault(key.strip(), []).append(" ".join(value.split()))
    return values


def test_api_unit_uses_the_live_unit_name() -> None:
    # The live unit is uzwellness.service; a second name makes runbooks lie.
    names = sorted(p.name for p in SYSTEMD.glob("uzwellness*.service"))
    assert "uzwellness.service" in names
    assert "uzwellness-api.service" not in names


def test_api_unit_serves_the_socket_nginx_proxies_to() -> None:
    unit = _unit("uzwellness.service")
    assert f"--uds {SOCKET}" in unit["ExecStart"][0]
    assert f"proxy_pass http://unix:{SOCKET};" in NGINX.read_text()
    assert unit["WorkingDirectory"] == ["/var/www/uzwellness-api"]
    assert unit["EnvironmentFile"] == ["/var/www/uzwellness-api/.env"]


def test_api_unit_runs_with_least_privilege() -> None:
    unit = _unit("uzwellness.service")
    assert unit["User"] == ["uzwellness"]
    assert unit["Group"] == ["www-data"]
    assert unit["UMask"] == ["0007"]
    assert unit["RuntimeDirectoryMode"] == ["0750"]
    # Uvicorn chmods its unix socket to 0666 after binding; tighten it after.
    assert f"/usr/bin/chmod 0660 {SOCKET}" in unit["ExecStartPost"]
    assert unit["NoNewPrivileges"] == ["true"]
    assert unit["ProtectSystem"] == ["strict"]
    assert unit["ProtectHome"] == ["true"]
    assert unit["PrivateTmp"] == ["true"]
    assert unit["ReadWritePaths"] == ["/var/www/uzwellness-api/uploads"]
    assert unit["Restart"] == ["always"]


def test_nginx_sends_security_headers_on_every_response() -> None:
    text = NGINX.read_text()
    for header in (
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
    ):
        assert re.search(rf"add_header {header} .+ always;", text), header
    assert "server_tokens off;" in text


@pytest.mark.parametrize("unit", ["uzwellness-complete-bookings"])
def test_daily_jobs_have_a_service_and_timer(unit: str) -> None:
    service = _unit(f"{unit}.service")
    timer = _unit(f"{unit}.timer")
    assert service["User"] == ["uzwellness"]
    assert "scripts.complete_bookings" in service["ExecStart"][0]
    assert timer["OnCalendar"]
    assert timer["Persistent"] == ["true"]


def test_compose_publishes_ports_on_loopback_only() -> None:
    compose = (ROOT / "docker-compose.yml").read_text()
    published = re.findall(r'^\s*-\s*"([^"]+)"\s*$', compose, flags=re.M)
    port_mappings = [p for p in published if re.fullmatch(r"[\d.:]+", p)]
    assert port_mappings
    for mapping in port_mappings:
        assert mapping.startswith("127.0.0.1:"), mapping

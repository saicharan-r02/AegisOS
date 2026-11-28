"""PR Pilot (React + Vite, built from web/) is the only web UI; the War Room dashboard stays removed."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aegis_os import api
from aegis_os.api import app, init_app

WEB_SRC = Path(api.__file__).resolve().parent.parent / "web" / "src"
LEGACY_DASHBOARD_MARKERS = re.compile(r"war.?room|launch mission|memory & rules", re.IGNORECASE)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    init_app(tmp_path / "web_ui_test.db")
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def built_ui(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the API at a fake `npm run build` output."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<!doctype html><title>PR Pilot</title><div id=root></div>")
    monkeypatch.setattr(api, "_STATIC_DIR", static_dir)
    return static_dir


@pytest.fixture
def unbuilt_ui(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the API at a folder where the UI was never built."""
    monkeypatch.setattr(api, "_STATIC_DIR", tmp_path / "not-built")


def test_root_redirects_to_pr_pilot(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/pr-pilot"


def test_pr_pilot_serves_built_index(client: TestClient, built_ui: Path) -> None:
    response = client.get("/pr-pilot")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "PR Pilot" in response.text


@pytest.mark.usefixtures("unbuilt_ui")
def test_pr_pilot_explains_how_to_build_when_ui_is_missing(client: TestClient) -> None:
    response = client.get("/pr-pilot")

    assert response.status_code == 503
    assert "npm run build" in response.json()["detail"]


def test_legacy_dashboard_bundle_is_gone(client: TestClient) -> None:
    assert client.get("/assets/index-DFRznF7o.js").status_code == 404


def test_api_stays_available_without_a_built_ui(client: TestClient, unbuilt_ui: None) -> None:
    assert client.get("/api/stats").status_code == 200


@pytest.mark.skipif(not WEB_SRC.is_dir(), reason="web/ source is not part of this checkout")
def test_web_source_contains_no_war_room_dashboard() -> None:
    offenders = [
        path.relative_to(WEB_SRC).as_posix()
        for path in WEB_SRC.rglob("*")
        if path.suffix in {".ts", ".tsx", ".css"} and LEGACY_DASHBOARD_MARKERS.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []

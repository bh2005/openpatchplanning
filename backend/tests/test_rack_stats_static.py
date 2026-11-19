from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.static import register_static


def rack(client, admin, site, units=10):
    r = client.post("/api/locations", headers=admin, json={"site_id": site["id"], "kind": "rack", "name": "Rack 1", "rack_units": units})
    assert r.status_code == 201, r.text
    return r.json()


def put_dev(client, admin, rack_id, name, pos, height=1, expect=201):
    r = client.post("/api/devices", headers=admin, json={"hostname": name, "location_id": rack_id, "rack_position": pos, "height_u": height})
    assert r.status_code == expect, r.text
    return r.json()


def test_rack_fit_and_overlap_rules(client, admin, site):
    rk = rack(client, admin, site, 10)
    put_dev(client, admin, rk["id"], "sw-1", 1, 2)                       # HE 1-2
    put_dev(client, admin, rk["id"], "pp-1", 3)                          # HE 3
    assert "überschneidet" in put_dev(client, admin, rk["id"], "x", 2, 2, 409)["detail"]      # HE 2-3 kollidiert
    assert "passt nicht" in put_dev(client, admin, rk["id"], "y", 10, 2, 400)["detail"]       # HE 10-11 > 10 HE
    put_dev(client, admin, rk["id"], "ok", 4, 7)                         # HE 4-10 passt genau
    room = client.post("/api/locations", headers=admin, json={"site_id": site["id"], "kind": "room", "name": "Raum"}).json()
    assert "nur in einem Rack" in put_dev(client, admin, room["id"], "z", 1, 1, 400)["detail"]


def test_moving_a_device_does_not_collide_with_itself(client, admin, site):
    rk = rack(client, admin, site)
    d = put_dev(client, admin, rk["id"], "sw-1", 1, 2)
    r = client.put(f"/api/devices/{d['id']}", headers=admin, json={"hostname": "sw-1", "location_id": rk["id"], "rack_position": 2, "height_u": 3})
    assert r.status_code == 200 and r.json()["height_u"] == 3


def test_height_defaults_to_one_and_is_validated(client, admin):
    d = client.post("/api/devices", headers=admin, json={"hostname": "x"}).json()
    assert d["height_u"] == 1
    assert client.post("/api/devices", headers=admin, json={"hostname": "y", "height_u": 0}).status_code == 422


def test_stats(client, admin, site):
    rk = rack(client, admin, site)
    put_dev(client, admin, rk["id"], "sw-1", 1)
    client.post("/api/devices", headers=admin, json={"hostname": "ohne-ort", "type": "router", "status": "planned"})
    client.post("/api/import/json", headers=admin, json={"devices": [{"hostname": "imp", "ports": [{"name": "p1"}]}], "dry_run": False})
    s = client.get("/api/stats", headers=admin).json()
    assert (s["sites"], s["racks"], s["devices"], s["ports"], s["devices_without_location"]) == (1, 1, 3, 1, 2)
    assert s["devices_by_type"] == {"switch": 2, "router": 1} and s["devices_by_status"]["planned"] == 1
    assert s["devices_by_source"] == {"manual": 2, "json": 1} and s["last_imports"][0]["stats"]["created"] == 1
    assert client.get("/api/stats").status_code == 401


@pytest.fixture()
def spa(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>OPP</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "geheim.txt").write_text("geheim")
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    assert register_static(app, Path(tmp_path))
    return TestClient(app)


def test_static_spa_fallback_assets_and_api_isolation(spa):
    assert spa.get("/").text == "<html>OPP</html>"
    assert spa.get("/devices/42").text == "<html>OPP</html>"                      # Vue-Router-Pfad
    assert spa.get("/assets/app.js").text == "console.log(1)"
    assert spa.get("/favicon.svg").text == "<svg/>"
    assert spa.get("/api/ping").json() == {"ok": True}
    r = spa.get("/api/gibt-es-nicht")
    assert r.status_code == 404 and r.json() == {"detail": "Nicht gefunden"}      # kein index.html für API-Pfade


def test_static_blocks_path_traversal(spa):
    for evil in ("/..%2fgeheim.txt", "/%2e%2e/geheim.txt", "/assets/..%2f..%2fgeheim.txt"):
        assert "geheim" not in spa.get(evil).text


def test_no_dist_means_no_static(tmp_path):
    assert register_static(FastAPI(), None) is False
    assert register_static(FastAPI(), None) is False

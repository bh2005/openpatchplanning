"""Schnellsuche: Treffer mit Standort/Ort, Rechte je Standort, Sonderzeichen."""
import pytest

from conftest import login


@pytest.fixture()
def world(client, admin):
    out = {}
    for code, name in (("A", "Werk Nord"), ("B", "Werk Süd")):
        s = client.post("/api/sites", headers=admin, json={"code": code, "name": name}).json()["id"]
        room = client.post("/api/locations", headers=admin, json={"site_id": s, "kind": "room", "name": f"Serverraum {code}"}).json()["id"]
        rack = client.post("/api/locations", headers=admin, json={"site_id": s, "parent_id": room, "kind": "rack", "name": f"Rack {code}1", "rack_units": 20}).json()["id"]
        out[code] = {"site": s, "rack": rack}
    mk = lambda host, code, **kw: client.post("/api/devices", headers=admin, json={"hostname": host, "location_id": out[code]["rack"], "rack_position": 3, **kw}).json()["id"]  # noqa: E731
    out["sw_a"] = mk("sw-kassel-01", "A", type="switch", mgmt_ip="10.1.2.3", serial="SN-12345", model="C9300")
    out["sw_b"] = mk("sw-kassel-02", "B", type="switch")
    out["free"] = client.post("/api/devices", headers=admin, json={"hostname": "sw-kassel-lager"}).json()["id"]
    return out


def find(client, h, q):
    r = client.get("/api/search", headers=h, params={"q": q})
    assert r.status_code == 200, r.text
    return r.json()


def test_device_shows_site_and_location(client, admin, world):
    r = find(client, admin, "kassel-01")
    assert len(r["devices"]) == 1
    d = r["devices"][0]
    assert d["hostname"] == "sw-kassel-01" and d["site"] == "A – Werk Nord" and d["location"] == "A / Serverraum A / Rack A1" and d["position"] == 3
    assert d["location_id"] == world["A"]["rack"]
    assert [x["hostname"] for x in find(client, admin, "10.1.2")["devices"]] == ["sw-kassel-01"]       # IP
    assert [x["hostname"] for x in find(client, admin, "sn-123")["devices"]] == ["sw-kassel-01"]      # Seriennummer
    assert [x["hostname"] for x in find(client, admin, "c9300")["devices"]] == ["sw-kassel-01"]       # Modell


def test_other_kinds(client, admin, world):
    assert find(client, admin, "werk nord")["sites"][0]["code"] == "A"
    assert find(client, admin, "Serverraum")["locations"][0]["path"].startswith(("A /", "B /"))
    wo = client.post("/api/workorders", headers=admin, json={"title": "Umbau Kassel"}).json()
    assert find(client, admin, wo["number"])["orders"][0]["number"] == wo["number"]
    assert find(client, admin, "umbau kas")["orders"][0]["id"] == wo["id"]


def test_short_and_special_queries(client, admin, world):
    assert find(client, admin, "s")["devices"] == []                                   # zu kurz
    assert find(client, admin, "%%")["devices"] == [] and find(client, admin, "_")["devices"] == []
    assert find(client, admin, "kassel%")["devices"] == []                             # Platzhalter werden nicht ausgewertet
    assert find(client, admin, "'; DROP TABLE devices; --")["devices"] == []
    assert len(client.get("/api/devices?limit=10", headers=admin).json()["items"]) == 3


def test_scopes_limit_results(client, admin, world):
    client.post("/api/users", headers=admin, json={"username": "va", "password": "Passwort-123", "roles": [], "scopes": [{"role": "viewer", "site_id": world["A"]["site"]}]})
    h = login(client, "va", "Passwort-123")
    assert [d["hostname"] for d in find(client, h, "kassel")["devices"]] == ["sw-kassel-01"]       # weder Standort B noch das Gerät ohne Ort
    assert [s["code"] for s in find(client, h, "werk")["sites"]] == ["A"]
    assert all(x["path"].startswith("A /") for x in find(client, h, "Serverraum")["locations"])
    assert client.get("/api/search?q=kassel").status_code in (401, 403)                                 # ohne Anmeldung nicht

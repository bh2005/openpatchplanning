import pytest


def loc(client, admin, site, name, kind="room", parent=None, **kw):
    r = client.post("/api/locations", headers=admin, json={"site_id": site["id"], "parent_id": parent, "kind": kind, "name": name, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def dev(client, admin, hostname="sw-01", **kw):
    r = client.post("/api/devices", headers=admin, json={"hostname": hostname, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_site_crud_and_unique_code(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "A", "name": "Standort A"}).json()
    assert client.post("/api/sites", headers=admin, json={"code": "a", "name": "doppelt"}).status_code == 409     # Code ohne Groß-/Kleinschreibung eindeutig
    assert client.put(f"/api/sites/{s['id']}", headers=admin, json={"code": "A", "name": "Neuer Name"}).json()["name"] == "Neuer Name"
    assert client.get("/api/sites", headers=admin).json()[0]["locations"] == 0
    assert client.delete(f"/api/sites/{s['id']}", headers=admin).status_code == 200
    assert client.delete(f"/api/sites/{s['id']}", headers=admin).status_code == 404


def test_location_tree_path_and_rules(client, admin, site):
    b = loc(client, admin, site, "Gebäude 1", "building")
    r = loc(client, admin, site, "Raum 2", "room", b["id"])
    rack = loc(client, admin, site, "Rack 3", "rack", r["id"], rack_units=42)
    assert rack["path"] == "SITE-A / Gebäude 1 / Raum 2 / Rack 3"
    other = client.post("/api/sites", headers=admin, json={"code": "B", "name": "B"}).json()
    assert client.post("/api/locations", headers=admin, json={"site_id": other["id"], "parent_id": b["id"], "name": "x"}).status_code == 400   # anderer Standort
    assert client.post("/api/locations", headers=admin, json={"site_id": site["id"], "kind": "room", "name": "x", "rack_units": 10}).status_code == 400
    assert client.post("/api/locations", headers=admin, json={"site_id": site["id"], "kind": "keller", "name": "x"}).status_code == 400
    assert client.put(f"/api/locations/{b['id']}", headers=admin, json={"site_id": site["id"], "parent_id": rack["id"], "kind": "building", "name": "Gebäude 1"}).status_code == 400  # Zyklus
    assert client.delete(f"/api/locations/{b['id']}", headers=admin).status_code == 409       # hat Kinder


def test_device_crud_validation_and_conflicts(client, admin, site):
    rack = loc(client, admin, site, "Rack 1", "rack", rack_units=42)
    d = dev(client, admin, "SW-01", type="switch", location_id=rack["id"], rack_position=10, mgmt_ip="192.0.2.5")
    assert d["location_path"] == "SITE-A / Rack 1"
    assert client.post("/api/devices", headers=admin, json={"hostname": "sw-01"}).status_code == 409        # Hostname ohne Groß-/Kleinschreibung eindeutig
    assert client.post("/api/devices", headers=admin, json={"hostname": "x", "type": "toaster"}).status_code == 400
    assert client.post("/api/devices", headers=admin, json={"hostname": "x", "status": "kaputt"}).status_code == 400
    assert client.post("/api/devices", headers=admin, json={"hostname": "x", "rack_position": 3}).status_code == 400   # HE ohne Location
    assert client.put(f"/api/devices/{d['id']}", headers=admin, json={"hostname": "SW-01", "status": "retired"}).json()["status"] == "retired"
    assert client.get("/api/devices/999", headers=admin).status_code == 404
    assert client.delete(f"/api/devices/{d['id']}", headers=admin).status_code == 200


def test_device_filters_search_and_pagination(client, admin, site):
    r1 = loc(client, admin, site, "Raum 1")
    r2 = loc(client, admin, site, "Raum 2")
    dev(client, admin, "sw-a", location_id=r1["id"], model="X-48")
    dev(client, admin, "sw-b", location_id=r2["id"], type="router")
    dev(client, admin, "pp-1", type="patchpanel")
    lst = lambda **q: client.get("/api/devices", headers=admin, params=q).json()
    assert lst()["total"] == 3
    assert [d["hostname"] for d in lst(q="x-48")["items"]] == ["sw-a"]
    assert [d["hostname"] for d in lst(type="router")["items"]] == ["sw-b"]
    assert [d["hostname"] for d in lst(location_id=r1["id"])["items"]] == ["sw-a"]
    assert lst(site_id=site["id"])["total"] == 2
    assert len(lst(limit=2)["items"]) == 2 and lst(limit=2, offset=2)["items"][0]["hostname"] == "sw-b"


def test_ports_crud_bulk_and_unique_names(client, admin):
    d = dev(client, admin)
    p = client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": "Gi1/0/1", "medium": "RJ45", "speed_mbps": 1000}).json()
    assert client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": "gi1/0/1"}).status_code == 409
    assert client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": "x", "medium": "Pappe"}).status_code == 400
    bulk = client.post(f"/api/devices/{d['id']}/ports/bulk", headers=admin, json={"prefix": "Gi1/0/", "start": 1, "count": 4}).json()
    assert bulk == {"created": 3, "skipped": 1}                                   # Gi1/0/1 gab es schon
    ports = client.get(f"/api/devices/{d['id']}", headers=admin).json()["ports"]
    assert [x["name"] for x in ports] == ["Gi1/0/1", "Gi1/0/2", "Gi1/0/3", "Gi1/0/4"]
    assert client.put(f"/api/ports/{p['id']}", headers=admin, json={"name": "Gi1/0/1", "description": "Uplink"}).json()["description"] == "Uplink"
    assert client.delete(f"/api/ports/{p['id']}", headers=admin).status_code == 200
    assert client.get(f"/api/devices/{d['id']}", headers=admin).json()["port_count"] == 3


def test_deleting_device_removes_ports(client, admin):
    d = dev(client, admin)
    client.post(f"/api/devices/{d['id']}/ports/bulk", headers=admin, json={"prefix": "P", "count": 5})
    client.delete(f"/api/devices/{d['id']}", headers=admin)
    from app import db
    assert db.row("SELECT COUNT(*) AS n FROM ports")["n"] == 0


def test_patchpanel_peer_ports_are_symmetric_and_device_local(client, admin):
    pp = dev(client, admin, "pp-1", type="patchpanel")
    other = dev(client, admin, "sw-9")
    client.post(f"/api/devices/{pp['id']}/ports/bulk", headers=admin, json={"prefix": "F", "count": 2})
    client.post(f"/api/devices/{pp['id']}/ports/bulk", headers=admin, json={"prefix": "R", "count": 2})
    foreign = client.post(f"/api/devices/{other['id']}/ports", headers=admin, json={"name": "Gi1"}).json()
    ports = {p["name"]: p for p in client.get(f"/api/devices/{pp['id']}/ports", headers=admin).json()}
    assert client.put(f"/api/ports/{ports['F1']['id']}/peer", headers=admin, json={"peer_port_id": ports['R1']['id']}).status_code == 200
    got = {p["name"]: p for p in client.get(f"/api/devices/{pp['id']}/ports", headers=admin).json()}
    assert got["F1"]["peer_port_id"] == ports["R1"]["id"] and got["R1"]["peer_port_id"] == ports["F1"]["id"]
    # F1 neu mit R2 verbinden löst die alte Paarung
    client.put(f"/api/ports/{ports['F1']['id']}/peer", headers=admin, json={"peer_port_id": ports['R2']['id']})
    got = {p["name"]: p for p in client.get(f"/api/devices/{pp['id']}/ports", headers=admin).json()}
    assert got["R1"]["peer_port_id"] is None and got["R2"]["peer_port_id"] == ports["F1"]["id"]
    assert client.put(f"/api/ports/{ports['F1']['id']}/peer", headers=admin, json={"peer_port_id": foreign["id"]}).status_code == 400
    assert client.put(f"/api/ports/{ports['F1']['id']}/peer", headers=admin, json={"peer_port_id": ports['F1']['id']}).status_code == 400
    client.put(f"/api/ports/{ports['F1']['id']}/peer", headers=admin, json={"peer_port_id": None})
    assert {p["name"]: p["peer_port_id"] for p in client.get(f"/api/devices/{pp['id']}/ports", headers=admin).json()}["R2"] is None


def test_site_with_devices_cannot_be_deleted(client, admin, site):
    r = loc(client, admin, site, "Raum 1")
    dev(client, admin, "sw-1", location_id=r["id"])
    assert client.delete(f"/api/sites/{site['id']}", headers=admin).status_code == 409

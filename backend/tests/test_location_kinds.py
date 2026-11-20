"""Wandgehäuse, Schaltschränke in Anlagen/Maschinen, mobile Maschinen (Lader) und Hutschienen-Montage."""
import pytest

from conftest import login


def loc(client, admin, site, name, kind, parent=None, **kw):
    r = client.post("/api/locations", headers=admin, json={"site_id": site, "parent_id": parent, "kind": kind, "name": name, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def model_id(client, admin, name):
    return [m for m in client.get("/api/device-models?q=Generisch", headers=admin).json() if m["model"] == name][0]["id"]


@pytest.fixture()
def plant(client, admin):
    a = client.post("/api/sites", headers=admin, json={"code": "A", "name": "Werk A"}).json()["id"]
    b = client.post("/api/sites", headers=admin, json={"code": "B", "name": "Werk B"}).json()["id"]
    hall = loc(client, admin, a, "Halle 1", "room")
    machine = loc(client, admin, a, "Presse 3", "machine", hall["id"], ident="M-4711")
    cab = loc(client, admin, a, "SK-Presse", "cabinet", machine["id"], ident="SK-01", rack_units=6)
    wall = loc(client, admin, a, "WR-Flur", "wallrack", hall["id"], rack_units=9)
    loader = loc(client, admin, a, "Lader 7", "vehicle", None, ident="K-AB 123")
    lcab = loc(client, admin, a, "Fahrer-Schaltkasten", "cabinet", loader["id"])
    return {"a": a, "b": b, "hall": hall["id"], "machine": machine["id"], "cab": cab["id"], "wall": wall["id"], "loader": loader["id"], "lcab": lcab["id"]}


def dev(client, admin, host, location, **kw):
    r = client.post("/api/devices", headers=admin, json={"hostname": host, "location_id": location, **kw})
    return r


def test_new_kinds_and_ident_and_rules(client, admin, plant):
    locs = {l["name"]: l for l in client.get(f"/api/locations?site_id={plant['a']}", headers=admin).json()}
    assert locs["Presse 3"]["ident"] == "M-4711" and locs["SK-Presse"]["rack_units"] == 6 and locs["Lader 7"]["kind"] == "vehicle"
    assert locs["SK-Presse"]["path"] == "A / Halle 1 / Presse 3 / SK-Presse"                     # Schaltschrank in der Maschine
    assert locs["Fahrer-Schaltkasten"]["path"] == "A / Lader 7 / Fahrer-Schaltkasten"            # mobile Maschine direkt am Standort
    assert client.post("/api/locations", headers=admin, json={"site_id": plant["a"], "kind": "machine", "name": "X", "rack_units": 4}).status_code == 400   # HE nur bei Gehäusen
    assert client.post("/api/locations", headers=admin, json={"site_id": plant["a"], "kind": "hubschrauber", "name": "X"}).status_code == 400


def test_he_placement_in_wallrack_and_cabinet(client, admin, plant):
    mid = model_id(client, admin, "Switch 8 Port")
    ok = client.post("/api/wizards/device", headers=admin, json={"hostname": "sw-wr", "type": "switch", "model_id": mid, "location_id": plant["wall"], "rack_position": 2, "mount_side": "front"})
    assert ok.status_code == 200, ok.text
    assert client.post("/api/wizards/device", headers=admin, json={"hostname": "sw-wr2", "type": "switch", "model_id": mid, "location_id": plant["wall"], "rack_position": 2, "mount_side": "front"}).status_code == 409
    assert dev(client, admin, "zu-hoch", plant["wall"], rack_position=9, height_u=2).status_code == 400            # 9 HE Wandgehäuse
    slots = client.get(f"/api/wizards/rack-slots/{plant['wall']}", headers=admin).json()
    assert slots["rack_units"] == 9 and 2 not in slots["free_starts"]
    assert client.get(f"/api/wizards/rack-slots/{plant['machine']}", headers=admin).status_code == 400            # Maschine hat keine HE-Teilung
    assert dev(client, admin, "x", plant["machine"], rack_position=1).status_code == 400                           # HE nur in Gehäusen
    assert dev(client, admin, "seiten", plant["wall"], orientation="vertical", side_slot="left", mount_side="rear").status_code == 400   # Seitenkanäle nur im Rack


def test_din_rail_devices_in_cabinet_machine_and_vehicle(client, admin, plant):
    sps = model_id(client, admin, "SPS-Steuerung (Hutschiene)")
    sw = model_id(client, admin, "Industrie-Switch 5 Port (Hutschiene)")
    models = {m["model"]: m for m in client.get("/api/device-models?orientation=din_rail", headers=admin).json()}
    assert {"SPS-Steuerung (Hutschiene)", "LTE-Router (Hutschiene)", "Netzteil 24 V (Hutschiene)", "HMI-Bedienpanel"} <= set(models)
    assert models["SPS-Steuerung (Hutschiene)"]["type"] == "plc"
    for i, (where, name) in enumerate([("cab", "sps-1"), ("cab", "sps-2"), ("machine", "sps-3"), ("lcab", "sps-4")]):
        r = client.post("/api/wizards/device", headers=admin, json={"hostname": name, "type": "plc", "model_id": sps, "location_id": plant[where]})
        assert r.status_code == 200, (name, r.text)                                                              # mehrere Geräte, keine HE-Kollision
    d = client.get(f"/api/devices?q=sps-", headers=admin).json()["items"]
    assert {x["hostname"] for x in d} == {"sps-1", "sps-2", "sps-3", "sps-4"} and all(x["orientation"] == "din_rail" and x["rack_position"] is None for x in d)
    r = client.post("/api/wizards/device", headers=admin, json={"hostname": "sw-lader", "type": "switch", "model_id": sw, "location_id": plant["lcab"]})
    assert r.status_code == 200 and r.json()["device"]["location_path"] == "A / Lader 7 / Fahrer-Schaltkasten"
    # HE-Geräte und Hutschiene mischen sich im selben Schrank
    he = client.post("/api/wizards/device", headers=admin, json={"hostname": "sw-he", "type": "switch", "model_id": model_id(client, admin, "Switch 8 Port"),
                                                                "location_id": plant["cab"], "rack_position": 1, "mount_side": "front"})
    assert he.status_code == 200, he.text
    assert dev(client, admin, "ohne-ort", None, orientation="din_rail").status_code == 400                       # Hutschiene braucht eine Location


def test_industrial_device_types(client, admin, plant):
    for t in ("plc", "hmi", "io_module", "drive", "gateway", "power_supply"):
        assert dev(client, admin, f"t-{t}", plant["cab"], type=t, orientation="din_rail").status_code == 201, t
    assert dev(client, admin, "kaputt", plant["cab"], type="kaffeemaschine").status_code == 400


def test_move_mobile_machine_between_sites_moves_everything(client, admin, plant):
    sw = model_id(client, admin, "Industrie-Switch 5 Port (Hutschiene)")
    d = client.post("/api/wizards/device", headers=admin, json={"hostname": "sw-lader", "type": "switch", "model_id": sw, "location_id": plant["lcab"]}).json()
    r = client.post(f"/api/locations/{plant['loader']}/move", headers=admin, json={"site_id": plant["b"]})
    assert r.status_code == 200, r.text
    assert r.json()["path"] == "B / Lader 7" and r.json()["old_path"] == "A / Lader 7"
    b_locs = {l["name"]: l for l in client.get(f"/api/locations?site_id={plant['b']}", headers=admin).json()}
    assert set(b_locs) == {"Lader 7", "Fahrer-Schaltkasten"}                                  # Schaltkasten zieht mit um
    assert b_locs["Fahrer-Schaltkasten"]["path"] == "B / Lader 7 / Fahrer-Schaltkasten"
    assert client.get(f"/api/devices/{d['device_id']}", headers=admin).json()["location_path"] == "B / Lader 7 / Fahrer-Schaltkasten"
    assert "Lader 7" not in {l["name"] for l in client.get(f"/api/locations?site_id={plant['a']}", headers=admin).json()}
    audit = [a for a in client.get("/api/audit", headers=admin).json() if a["action"] == "location.move"]
    assert audit and "A / Lader 7 -> B / Lader 7" in audit[0]["detail"] and "1 Geräte" in audit[0]["detail"]
    # zurück und unter eine andere Location
    hall_b = loc(client, admin, plant["b"], "Halle B", "room")
    assert client.post(f"/api/locations/{plant['loader']}/move", headers=admin, json={"site_id": plant["b"], "parent_id": hall_b["id"]}).json()["path"] == "B / Halle B / Lader 7"


def test_move_validation(client, admin, plant):
    mv = lambda lid, **kw: client.post(f"/api/locations/{lid}/move", headers=admin, json=kw)  # noqa: E731
    assert mv(plant["loader"], site_id=999).status_code == 400
    assert mv(plant["loader"], site_id=plant["b"], parent_id=plant["hall"]).status_code == 400            # Parent gehört zu anderem Standort
    assert mv(plant["machine"], site_id=plant["a"], parent_id=plant["cab"]).status_code == 400            # in die eigene Unterstruktur
    assert mv(plant["lcab"], site_id=plant["a"], parent_id=plant["wall"]).status_code == 400              # Gehäuse nehmen nur Geräte auf
    assert mv(999, site_id=plant["a"]).status_code == 404


def test_move_permissions_and_visibility(client, admin, plant):
    def user(name, role, site):
        client.post("/api/users", headers=admin, json={"username": name, "password": "Passwort-123", "roles": [], "scopes": [{"role": role, "site_id": site}]})
        return login(client, name, "Passwort-123")
    adm_a = user("adm-a", "admin", plant["a"])
    assert client.post(f"/api/locations/{plant['loader']}/move", headers=adm_a, json={"site_id": plant["b"]}).status_code == 403   # Zielstandort fremd
    both = client.post("/api/users", headers=admin, json={"username": "adm-ab", "password": "Passwort-123", "roles": [],
                                                          "scopes": [{"role": "admin", "site_id": plant["a"]}, {"role": "admin", "site_id": plant["b"]}]})
    assert both.status_code == 201
    h = login(client, "adm-ab", "Passwort-123")
    assert client.post(f"/api/locations/{plant['loader']}/move", headers=h, json={"site_id": plant["b"]}).status_code == 200
    viewer_a = user("vw-a", "viewer", plant["a"])
    assert "Lader 7" not in {l["name"] for l in client.get("/api/locations", headers=viewer_a).json()}      # Lader ist jetzt in B – nicht mehr sichtbar
    vw = user("vw-x", "viewer", plant["a"])
    assert client.post(f"/api/locations/{plant['machine']}/move", headers=vw, json={"site_id": plant["a"]}).status_code == 403


def test_site_wizard_builds_machines_cabinets_and_vehicles(client, admin):
    n = lambda k, name, ch=None, **kw: {"kind": k, "name": name, "children": ch or [], **kw}  # noqa: E731
    tree = [n("building", "Halle", [n("floor", "EG", [n("room", "Fertigung", [
        n("machine", "Presse", [n("cabinet", "SK-1", rack_units=8), n("cabinet", "SK-2")]),
        n("wallrack", "WR-1"), n("rack", "R-1")])])]),
        n("vehicle", "Lader 1", [n("cabinet", "Kabine")])]
    r = client.post("/api/wizards/site", headers=admin, json={"site": {"code": "W9", "name": "Werk 9"}, "tree": tree})
    assert r.status_code == 200, r.text
    counts = {k: v for k, v in r.json()["counts"].items() if v}
    assert counts == {"standort": 1, "building": 1, "floor": 1, "room": 1, "machine": 1, "vehicle": 1, "rack": 1, "wallrack": 1, "cabinet": 3}
    items = {i["name"]: i for i in r.json()["items"]}
    assert items["WR-1"]["rack_units"] == 12 and items["R-1"]["rack_units"] == 42               # Vorgabe-HE je Art
    assert items["SK-1"]["rack_units"] == 8 and items["SK-2"]["rack_units"] is None             # Schaltschrank ohne HE-Teilung möglich
    assert items["Kabine"]["path"] == "W9 / Lader 1 / Kabine"
    st = client.get("/api/stats", headers=admin).json()
    assert st["racks"] == 5                                                                      # Racks, Wandgehäuse und Schaltschränke zählen als Gehäuse


def test_site_wizard_hierarchy_rules(client, admin):
    n = lambda k, name, ch=None, **kw: {"kind": k, "name": name, "children": ch or [], **kw}  # noqa: E731
    post = lambda tree: client.post("/api/wizards/site", headers=admin, json={"site": {"code": "H", "name": "H"}, "tree": tree, "dry_run": True}).status_code  # noqa: E731
    assert post([n("machine", "M", [n("machine", "M2")])]) == 400                                # Maschine in Maschine nicht
    assert post([n("cabinet", "S", [n("cabinet", "S2")])]) == 400                                # Gehäuse haben keine Unterstruktur
    assert post([n("rack", "R", [n("machine", "M")])]) == 400
    assert post([n("room", "R", [n("vehicle", "V")])]) == 200                                    # mobile Maschine im Raum (Halle) möglich
    assert post([n("machine", "M", rack_units=4)]) == 400                                        # HE nur bei Gehäusen
    assert post([n("cabinet", "S", rack_units=4)]) == 200

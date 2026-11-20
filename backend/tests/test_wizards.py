from conftest import make_user, login


def node(kind, name, children=None, **kw):
    return {"kind": kind, "name": name, "children": children or [], **kw}


TREE = [node("building", "Haus 1", [
    node("floor", "EG", [node("room", "Serverraum", [node("rack", "R1", rack_units=42), node("rack", "R2")])]),
    node("floor", "1.OG", [node("room", "Verteiler")]),
])]


def test_new_site_with_structure_atomic_and_paths(client, admin):
    r = client.post("/api/wizards/site", headers=admin, json={"site": {"code": "WERK1", "name": "Werk 1"}, "tree": TREE})
    assert r.status_code == 200, r.text
    d = r.json()
    assert {k: v for k, v in d["counts"].items() if v} == {"standort": 1, "building": 1, "floor": 2, "room": 2, "rack": 2}
    locs = client.get(f"/api/locations?site_id={d['site']['id']}", headers=admin).json()
    paths = {l["path"]: l for l in locs}
    assert "WERK1 / Haus 1 / EG / Serverraum / R1" in paths
    assert paths["WERK1 / Haus 1 / EG / Serverraum / R1"]["rack_units"] == 42
    assert paths["WERK1 / Haus 1 / EG / Serverraum / R2"]["rack_units"] == 42       # Standard 42 HE
    assert len(locs) == 7


def test_dry_run_writes_nothing(client, admin):
    r = client.post("/api/wizards/site", headers=admin, json={"site": {"code": "X", "name": "X"}, "tree": TREE, "dry_run": True})
    assert r.status_code == 200 and r.json()["dry_run"] and len(r.json()["items"]) == 7
    assert client.get("/api/sites", headers=admin).json() == []


def test_validation_errors_create_nothing(client, admin):
    bad_order = [node("room", "Raum", [node("floor", "Etage")])]
    assert client.post("/api/wizards/site", headers=admin, json={"site": {"code": "A", "name": "A"}, "tree": bad_order}).status_code == 400
    dup = [node("building", "H"), node("building", "h")]
    assert client.post("/api/wizards/site", headers=admin, json={"site": {"code": "A", "name": "A"}, "tree": dup}).status_code == 400
    rack_kids = [node("rack", "R", [node("rack", "R2")])]
    assert client.post("/api/wizards/site", headers=admin, json={"site": {"code": "A", "name": "A"}, "tree": rack_kids}).status_code == 400
    units = [node("room", "Raum", rack_units=10)]
    assert client.post("/api/wizards/site", headers=admin, json={"site": {"code": "A", "name": "A"}, "tree": units}).status_code == 400
    assert client.post("/api/wizards/site", headers=admin, json={"site": {"code": "A", "name": "A"}, "tree": [node("keller", "K")]}).status_code == 400
    assert client.post("/api/wizards/site", headers=admin, json={"tree": []}).status_code == 400
    assert client.get("/api/sites", headers=admin).json() == []                      # Standort wurde nirgends angelegt


def test_duplicate_site_code_conflict(client, admin, site):
    r = client.post("/api/wizards/site", headers=admin, json={"site": {"code": "site-a", "name": "doppelt"}, "tree": []})
    assert r.status_code == 409


def test_extend_existing_site_under_parent(client, admin, site):
    first = client.post("/api/wizards/site", headers=admin, json={"site_id": site["id"], "tree": [node("building", "B1", [node("room", "R")])]}).json()
    locs = {l["name"]: l for l in client.get(f"/api/locations?site_id={site['id']}", headers=admin).json()}
    assert first["counts"]["standort"] == 0
    # unter vorhandenem Raum nur Racks
    ok = client.post("/api/wizards/site", headers=admin, json={"site_id": site["id"], "parent_id": locs["R"]["id"], "tree": [node("rack", "Rack A")]})
    assert ok.status_code == 200 and ok.json()["items"][0]["path"] == "SITE-A / B1 / R / Rack A"
    # Doppelt unter derselben Ebene wie vorhandene
    dup = client.post("/api/wizards/site", headers=admin, json={"site_id": site["id"], "tree": [node("building", "b1")]})
    assert dup.status_code == 400
    # Rack-Eltern nicht möglich, Gebäude unter Raum nicht möglich
    rack = [l for l in client.get(f"/api/locations?site_id={site['id']}", headers=admin).json() if l["name"] == "Rack A"][0]
    assert client.post("/api/wizards/site", headers=admin, json={"site_id": site["id"], "parent_id": rack["id"], "tree": [node("rack", "x")]}).status_code == 400
    assert client.post("/api/wizards/site", headers=admin, json={"site_id": site["id"], "parent_id": locs["R"]["id"], "tree": [node("building", "x")]}).status_code == 400


def test_wizard_needs_write_permission(client, admin):
    make_user(client, admin, "v1", roles=("viewer",))
    h = login(client, "v1", "Passwort-123")
    assert client.post("/api/wizards/site", headers=h, json={"site": {"code": "V", "name": "V"}, "tree": []}).status_code == 403

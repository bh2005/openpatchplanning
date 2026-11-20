"""Patchfeld platzieren: Dual-Ports aus dem Katalog und mehrere Verbindungen (Port-Zuordnung) in einem Zug."""
import pytest


def model_id(client, admin, name):
    return [m for m in client.get("/api/device-models?q=Generisch", headers=admin).json() if m["model"] == name][0]["id"]


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    r = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": "R1", "rack_units": 20}).json()
    sw = client.post("/api/wizards/device", headers=admin, json={"hostname": "sw-core", "type": "switch", "location_id": r["id"], "rack_position": 20,
                     "model_id": model_id(client, admin, "Switch 24 Port")}).json()
    ports = client.get(f"/api/devices/{sw['device_id']}/ports", headers=admin).json()     # natürlich sortiert: Port1, Port2, …
    return {"site": s["id"], "rack": r["id"], "sw": sw["device_id"], "sw_ports": ports}


def links(lab, n, start=0, side=""):
    return [{"port_name": f"P{i + 1}{side}", "target_port_id": lab["sw_ports"][start + i]["id"], "cable_type": "Cat6A", "cable_label": f"PF-{i + 1:02d}"}
            for i in range(n)]


def pp_body(lab, **kw):
    return {"hostname": "pf-1", "type": "patchpanel", "location_id": lab["rack"], "rack_position": 1,
            "model_id": None, **kw}


def test_patchpanel_with_bulk_links_direct(client, admin, lab):
    mid = model_id(client, admin, "Patchfeld Cat6A 12 Port")
    r = client.post("/api/wizards/device", headers=admin, json=pp_body(lab, model_id=mid, links=links(lab, 12)))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ports_created"] == 24 and len(d["cable_ids"]) == 12
    dev = client.get(f"/api/devices/{d['device_id']}", headers=admin).json()
    assert dev["type"] == "patchpanel" and len(dev["ports"]) == 24
    front = [p for p in dev["ports"] if not p["name"].endswith("-back")]
    assert len(front) == 12 and all(p["cable"] and p["peer_port_id"] for p in front)             # vorn verkabelt, hinten durchgeschleift
    assert [p["cable"]["port_name"] for p in sorted(front, key=lambda p: int(p["name"][1:]))] == [f"Port{i}" for i in range(1, 13)]
    assert front[0]["cable"]["cable_type"] == "Cat6A" and {p["cable"]["cable_label"] for p in front} >= {"PF-01", "PF-12"}
    back = [p for p in dev["ports"] if p["name"].endswith("-back")]
    assert all(p["cable"] is None for p in back)


def test_dry_run_lists_all_cables(client, admin, lab):
    mid = model_id(client, admin, "Patchfeld Cat6A 8 Port")
    r = client.post("/api/wizards/device", headers=admin, json=pp_body(lab, model_id=mid, links=links(lab, 8), dry_run=True)).json()
    assert r["dry_run"] and len(r["cables"]) == 8 and r["cables"][0] == {"from": "pf-1:P1", "to": "sw-core:Port1", "type": "Cat6A", "label": "PF-01", "via": "direkt"}
    assert client.get("/api/cables", headers=admin).json() == []


def test_link_validation(client, admin, lab):
    mid = model_id(client, admin, "Patchfeld Cat6A 8 Port")
    post = lambda lk: client.post("/api/wizards/device", headers=admin, json=pp_body(lab, model_id=mid, links=lk)).status_code  # noqa: E731
    ok = links(lab, 2)
    assert post([ok[0], {**ok[1], "port_name": "P1"}]) == 400                                      # derselbe Port zweimal
    assert post([ok[0], {**ok[1], "target_port_id": ok[0]["target_port_id"]}]) == 400              # derselbe Zielport zweimal
    assert post([{**ok[0], "port_name": "P99"}]) == 400                                            # Port gibt es nicht
    assert post([{**ok[0], "target_port_id": 99999}]) == 404
    assert post([{**ok[0], "cable_type": "Zauber"}]) == 400
    assert client.get("/api/devices?q=pf-1", headers=admin).json()["total"] == 0                    # nichts angelegt


def test_one_question_for_all_busy_targets_and_direct_replacement(client, admin, lab):
    mid = model_id(client, admin, "Patchfeld Cat6A 8 Port")
    first = client.post("/api/wizards/device", headers=admin, json=pp_body(lab, hostname="alt", rack_position=1, model_id=mid, links=links(lab, 3)))
    assert first.status_code == 200
    new = pp_body(lab, hostname="neu", rack_position=3, model_id=mid, links=links(lab, 5, start=1))   # Ports 2–6; 2 und 3 sind belegt
    q = client.post("/api/wizards/device", headers=admin, json=new)
    d = q.json()["detail"]
    assert q.status_code == 409 and d["code"] == "port_busy" and len(d["conflicts"]) == 2 and "sofort" in d["message"]
    ok = client.post("/api/wizards/device", headers=admin, json={**new, "remove_old": True})
    assert ok.status_code == 200, ok.text
    cables = client.get("/api/cables", headers=admin).json()
    assert len(cables) == 3 + 5 - 2                                                                # 2 alte Patches ersetzt


def test_workorder_mode_creates_install_and_connect_items_plus_one_removal_order(client, admin, lab):
    mid = model_id(client, admin, "Patchfeld Cat6A 8 Port")
    client.post("/api/wizards/device", headers=admin, json=pp_body(lab, hostname="alt", rack_position=1, model_id=mid, links=links(lab, 2)))
    new = pp_body(lab, hostname="neu", rack_position=3, model_id=mid, mode="workorder", links=links(lab, 4))
    assert client.post("/api/wizards/device", headers=admin, json=new).status_code == 409
    ok = client.post("/api/wizards/device", headers=admin, json={**new, "remove_old": True})
    assert ok.status_code == 200, ok.text
    wo = ok.json()["workorder"]
    main = client.get(f"/api/workorders/{wo['id']}", headers=admin).json()
    assert [i["action"] for i in main["items"]] == ["install_device"] + ["connect"] * 4
    rem = client.get(f"/api/workorders/{wo['removal_order']['id']}", headers=admin).json()
    assert [i["action"] for i in rem["items"]] == ["disconnect", "disconnect"]                     # ein Rückbau-Auftrag für beide alten Patches
    dev = client.get(f"/api/devices/{ok.json()['device_id']}", headers=admin).json()
    assert dev["status"] == "planned" and all(p["cable"] is None for p in dev["ports"])


def test_back_side_links_to_another_panel(client, admin, lab):
    mid = model_id(client, admin, "Patchfeld Cat6A 8 Port")
    a = client.post("/api/wizards/device", headers=admin, json=pp_body(lab, hostname="pf-a", rack_position=1, model_id=mid)).json()["device_id"]
    a_ports = {p["name"]: p["id"] for p in client.get(f"/api/devices/{a}/ports", headers=admin).json()}
    lk = [{"port_name": f"P{i}-back", "target_port_id": a_ports[f"P{i}-back"], "cable_type": "Cat6A"} for i in (1, 2)]
    r = client.post("/api/wizards/device", headers=admin, json=pp_body(lab, hostname="pf-b", rack_position=3, model_id=mid, links=lk))
    assert r.status_code == 200, r.text
    b = client.get(f"/api/devices/{r.json()['device_id']}", headers=admin).json()
    assert {p["name"] for p in b["ports"] if p["cable"]} == {"P1-back", "P2-back"}


def test_scoped_planer_orders_patchpanel(client, admin, lab):
    mid = model_id(client, admin, "Patchfeld Cat6A 8 Port")
    client.post("/api/users", headers=admin, json={"username": "pl", "password": "Passwort-123", "roles": [], "scopes": [{"role": "planer", "site_id": lab["site"]}]})
    from conftest import login
    h = login(client, "pl", "Passwort-123")
    body = pp_body(lab, model_id=mid, links=links(lab, 3), mode="workorder")
    ok = client.post("/api/wizards/device", headers=h, json=body)
    assert ok.status_code == 200, ok.text
    assert client.post("/api/wizards/device", headers=h, json={**body, "hostname": "pf-2", "rack_position": 5, "mode": "direct"}).status_code == 403

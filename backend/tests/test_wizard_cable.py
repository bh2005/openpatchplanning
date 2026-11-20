"""Kabel-Assistent: beliebige Kabelarten (Daten, Strom, Koax, seriell, Telefon), Hinweise, Rückfrage bei belegten Ports."""
import pytest

from conftest import login


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    s2 = client.post("/api/sites", headers=admin, json={"code": "W2", "name": "Anderes Werk"}).json()
    loc = lambda sid, name: client.post("/api/locations", headers=admin, json={"site_id": sid, "kind": "rack", "name": name, "rack_units": 20}).json()["id"]  # noqa: E731
    r1, r2 = loc(s["id"], "R1"), loc(s2["id"], "R2")
    out = {"site": s["id"], "site2": s2["id"], "rack": r1, "rack2": r2}

    def dev(name, rack, ports, dtype="switch"):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": dtype, "location_id": rack}).json()
        ids = {n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n, "medium": m}).json()["id"] for n, m in ports}
        return {"id": d["id"], **ids}
    out["sw"] = dev("sw-1", r1, [("Gi1", "RJ45"), ("Gi2", "RJ45"), ("Gi3", "RJ45")])
    out["sw2"] = dev("sw-2", r1, [("Gi1", "RJ45")])
    out["pdu"] = dev("pdu-1", r1, [("Out1", "C13"), ("Out2", "C13")], "pdu")
    out["srv"] = dev("srv-1", r1, [("PSU1", "C14")], "server")
    out["clock"] = dev("ntp-1", r1, [("BNC1", "BNC")], "timeserver")
    out["dcf"] = dev("dcf-1", r1, [("BNC1", "BNC")], "timeserver")
    out["pbx"] = dev("pbx-1", r1, [("Tel1", "RJ11")], "other")
    out["far"] = dev("sw-w2", r2, [("Gi1", "RJ45")])
    return out


def cab(client, headers, a, b, **kw):
    return client.post("/api/wizards/cable", headers=headers, json={"port_a_id": a, "port_b_id": b, **kw})


def test_power_coax_serial_and_telco_cables_direct(client, admin, lab):
    cases = [(lab["pdu"]["Out1"], lab["srv"]["PSU1"], "Strom C13/C14", "PDU-1"),
             (lab["clock"]["BNC1"], lab["dcf"]["BNC1"], "RG58", "DCF-1"),
             (lab["pbx"]["Tel1"], lab["sw"]["Gi3"], "Telefon-Cu", "TEL-1")]
    for a, b, ctype, label in cases:
        r = cab(client, admin, a, b, cable_type=ctype, cable_label=label, length_m=3.5, fiber_count=2)
        assert r.status_code == 200, (ctype, r.text)
    cables = {c["cable_label"]: c for c in client.get("/api/cables", headers=admin).json()}
    assert set(cables) == {"PDU-1", "DCF-1", "TEL-1"}
    assert cables["DCF-1"]["cable_type"] == "RG58" and cables["PDU-1"]["length_m"] == 3.5
    assert cables["PDU-1"]["fiber_count"] is None and cables["TEL-1"]["fiber_count"] == 2          # Zählfeld nur bei Arten mit Anzahl (Paare)


def test_medium_mismatch_is_a_warning_not_an_error(client, admin, lab):
    r = cab(client, admin, lab["sw"]["Gi1"], lab["sw2"]["Gi1"], cable_type="Strom 230V", dry_run=True).json()
    assert len(r["warnings"]) == 2 and "RJ45" in r["warnings"][0] and "Strom 230V" in r["warnings"][0]
    ok = cab(client, admin, lab["pdu"]["Out2"], lab["srv"]["PSU1"], cable_type="Strom C13/C14", dry_run=True).json()
    assert ok["warnings"] == [] and ok["cable"]["category"] == "power"
    assert cab(client, admin, lab["sw"]["Gi1"], lab["sw2"]["Gi1"], cable_type="Strom 230V").status_code == 200       # trotzdem möglich


def test_dry_run_writes_nothing_and_validation(client, admin, lab):
    d = cab(client, admin, lab["sw"]["Gi1"], lab["sw2"]["Gi1"], cable_label="X", dry_run=True).json()
    assert d["dry_run"] and d["cable"]["from"] == "sw-1:Gi1" and d["cable"]["to"] == "sw-2:Gi1" and d["cable"]["via"] == "direkt"
    assert client.get("/api/cables", headers=admin).json() == []
    assert cab(client, admin, lab["sw"]["Gi1"], lab["sw"]["Gi1"]).status_code == 400                 # nicht mit sich selbst
    assert cab(client, admin, lab["sw"]["Gi1"], 99999).status_code == 404
    assert cab(client, admin, lab["sw"]["Gi1"], lab["sw2"]["Gi1"], cable_type="Zauber").status_code == 400
    assert cab(client, admin, lab["sw"]["Gi1"], lab["sw2"]["Gi1"], mode="beamen").status_code == 400
    assert cab(client, admin, lab["sw"]["Gi1"], lab["sw2"]["Gi1"]).status_code == 200
    assert cab(client, admin, lab["sw2"]["Gi1"], lab["sw"]["Gi1"]).status_code == 409                # bereits verbunden (auch umgekehrt)


def test_busy_port_asks_and_direct_replaces(client, admin, lab):
    assert cab(client, admin, lab["sw"]["Gi1"], lab["sw2"]["Gi1"], cable_label="ALT").status_code == 200
    q = cab(client, admin, lab["sw"]["Gi1"], lab["sw"]["Gi2"], cable_label="NEU")
    d = q.json()["detail"]
    assert q.status_code == 409 and d["code"] == "port_busy" and d["conflicts"][0]["cable_label"] == "ALT" and "sofort" in d["message"]
    ok = cab(client, admin, lab["sw"]["Gi1"], lab["sw"]["Gi2"], cable_label="NEU", remove_old=True)
    assert ok.status_code == 200, ok.text
    assert [c["cable_label"] for c in client.get("/api/cables", headers=admin).json()] == ["NEU"]


def test_workorder_mode_with_removal_order(client, admin, lab):
    cab(client, admin, lab["sw"]["Gi1"], lab["sw2"]["Gi1"], cable_label="ALT")
    req = {"cable_label": "NEU", "mode": "workorder", "cable_type": "Cat6A"}
    q = cab(client, admin, lab["sw"]["Gi1"], lab["sw"]["Gi2"], **req)
    assert q.status_code == 409 and "Rückbau-Patchauftrag" in q.json()["detail"]["message"]
    r = cab(client, admin, lab["sw"]["Gi1"], lab["sw"]["Gi2"], remove_old=True, **req)
    assert r.status_code == 200, r.text
    wo = r.json()["workorder"]
    assert wo["new"] and wo["removal_order"] and r.json()["cable_id"] is None
    main = client.get(f"/api/workorders/{wo['id']}", headers=admin).json()
    assert main["title"] == "Kabel sw-1 ↔ sw-1" and main["location"]["id"] == lab["rack"]
    assert [(i["action"], i["cable_label"]) for i in main["items"]] == [("connect", "NEU")]
    rem = client.get(f"/api/workorders/{wo['removal_order']['id']}", headers=admin).json()
    assert [i["action"] for i in rem["items"]] == ["disconnect"]
    assert [c["cable_label"] for c in client.get("/api/cables", headers=admin).json()] == ["ALT"]        # Bestand erst nach Bestätigung geändert
    # in bestehenden Entwurf einhängen
    existing = client.post("/api/workorders", headers=admin, json={"title": "Sammel", "location_id": lab["rack"]}).json()
    again = cab(client, admin, lab["sw"]["Gi3"], lab["pbx"]["Tel1"], mode="workorder", workorder_id=existing["id"], cable_type="Telefon-Cu")
    assert again.status_code == 200 and again.json()["workorder"]["number"] == existing["number"] and again.json()["workorder"]["new"] is False


def test_retired_device_rejected(client, admin, lab):
    client.put(f"/api/devices/{lab['sw2']['id']}", headers=admin, json={"hostname": "sw-2", "status": "retired", "location_id": lab["rack"]})
    r = cab(client, admin, lab["sw"]["Gi1"], lab["sw2"]["Gi1"])
    assert r.status_code == 400 and "außer Betrieb" in r.json()["detail"]


def test_permissions_by_site(client, admin, lab):
    def user(name, role, site):
        client.post("/api/users", headers=admin, json={"username": name, "password": "Passwort-123", "roles": [], "scopes": [{"role": role, "site_id": site}]})
        return login(client, name, "Passwort-123")
    adm, pl, vw = user("adm", "admin", lab["site"]), user("pl", "planer", lab["site"]), user("vw", "viewer", lab["site"])
    assert cab(client, adm, lab["sw"]["Gi1"], lab["sw2"]["Gi1"]).status_code == 200                       # Bereichs-Admin: direkt im eigenen Standort
    assert cab(client, adm, lab["sw"]["Gi2"], lab["far"]["Gi1"]).status_code == 403                       # Gegenstelle im fremden Standort
    assert cab(client, pl, lab["sw"]["Gi2"], lab["sw"]["Gi3"]).status_code == 403                         # Planer: nicht direkt ...
    ok = cab(client, pl, lab["sw"]["Gi2"], lab["sw"]["Gi3"], mode="workorder")
    assert ok.status_code == 200 and ok.json()["workorder"]["number"]                                      # ... aber per Auftrag
    assert cab(client, pl, lab["sw"]["Gi2"], lab["far"]["Gi1"], mode="workorder").status_code == 403
    assert cab(client, vw, lab["sw"]["Gi2"], lab["sw"]["Gi3"], mode="workorder").status_code == 403

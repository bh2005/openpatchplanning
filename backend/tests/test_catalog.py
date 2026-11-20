from conftest import make_user, login


def mk_model(client, admin, **kw):
    body = {"vendor": "Hersteller", "model": "SW-48", "type": "switch", "height_u": 1,
            "ports": [{"prefix": "Gi1/0/", "count": 4, "medium": "RJ45", "speed_mbps": 1000},
                      {"prefix": "Te1/1/", "count": 2, "medium": "SFP+", "speed_mbps": 10000}], **kw}
    r = client.post("/api/device-models", headers=admin, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_builtin_cable_types_include_power_coax_serial_telco(client, admin):
    names = {t["name"]: t for t in client.get("/api/cable-types", headers=admin).json()}
    assert names["Strom 230V"]["category"] == "power"
    assert names["RG58"]["category"] == "coax"
    assert names["RS232"]["category"] == "serial"
    assert names["Telefon-Cu"]["count_label"] == "Paare"
    assert names["LWL-SM-OS2"]["count_label"] == "Fasern" and names["Cat6"]["count_label"] == ""


def test_custom_cable_type_usable_and_protected(client, admin):
    r = client.post("/api/cable-types", headers=admin, json={"name": "Hohlleiter", "category": "other"})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert client.post("/api/cable-types", headers=admin, json={"name": "hohlleiter"}).status_code == 409
    assert client.post("/api/cable-types", headers=admin, json={"name": "X", "category": "zauber"}).status_code == 400
    # in Patchauftrag verwendbar
    wo = client.post("/api/workorders", headers=admin, json={"title": "t"}).json()
    ok = client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "connect", "cable_type": "Hohlleiter"})
    assert ok.status_code == 201
    # Umbenennen verboten, Löschen bei Verwendung verboten, Deaktivieren möglich
    assert client.put(f"/api/cable-types/{cid}", headers=admin, json={"name": "Neu"}).status_code == 400
    assert client.delete(f"/api/cable-types/{cid}", headers=admin).status_code == 409
    assert client.put(f"/api/cable-types/{cid}", headers=admin, json={"name": "Hohlleiter", "active": False}).status_code == 200
    bad = client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "connect", "cable_type": "Hohlleiter"})
    assert bad.status_code == 400                      # inaktiv: nicht mehr für neue Positionen
    assert "Hohlleiter" not in [t["name"] for t in client.get("/api/cable-types", headers=admin).json()]
    # builtin nicht löschbar
    cat6 = next(t for t in client.get("/api/cable-types", headers=admin).json() if t["name"] == "Cat6")
    assert client.delete(f"/api/cable-types/{cat6['id']}", headers=admin).status_code == 409


def test_cable_type_admin_only_and_unknown_rejected(client, admin):
    make_user(client, admin, "planer1", roles=("planer",))
    h = login(client, "planer1", "Passwort-123")
    assert client.get("/api/cable-types", headers=h).status_code == 200
    assert client.post("/api/cable-types", headers=h, json={"name": "Y"}).status_code == 403


def test_cable_set_with_power_type(client, admin):
    a = client.post("/api/devices", headers=admin, json={"hostname": "pdu-1", "type": "pdu"}).json()
    b = client.post("/api/devices", headers=admin, json={"hostname": "sw-1"}).json()
    pa = client.post(f"/api/devices/{a['id']}/ports", headers=admin, json={"name": "Out1", "medium": "C13"}).json()
    pb = client.post(f"/api/devices/{b['id']}/ports", headers=admin, json={"name": "PSU1", "medium": "C14"}).json()
    r = client.put(f"/api/ports/{pa['id']}/cable", headers=admin, json={"port_b_id": pb["id"], "cable_type": "Strom C13/C14"})
    assert r.status_code == 200, r.text
    assert client.put(f"/api/ports/{pa['id']}/cable", headers=admin, json={"port_b_id": pb["id"], "cable_type": "Unbekannt"}).status_code == 400


def test_model_crud_and_validation(client, admin):
    m = mk_model(client, admin)
    assert m["port_total"] == 6 and m["device_count"] == 0
    assert client.post("/api/device-models", headers=admin, json={"vendor": "hersteller", "model": "sw-48"}).status_code == 409
    assert client.post("/api/device-models", headers=admin, json={"model": "X", "type": "kaffeemaschine"}).status_code == 400
    assert client.post("/api/device-models", headers=admin, json={"model": "X", "ports": [{"prefix": "p", "count": 1, "medium": "Laser"}]}).status_code == 400
    big = {"model": "Big", "ports": [{"prefix": "p", "count": 512}, {"prefix": "q", "count": 512, "dual": True}]}
    assert client.post("/api/device-models", headers=admin, json=big).status_code == 400          # > 1024 Ports
    assert client.get("/api/device-models?q=sw-48", headers=admin).json()[0]["id"] == m["id"]
    m["model"] = "SW-48X"
    assert client.put(f"/api/device-models/{m['id']}", headers=admin, json=m).json()["model"] == "SW-48X"
    assert client.delete(f"/api/device-models/{m['id']}", headers=admin).status_code == 200
    assert client.get(f"/api/device-models/{m['id']}", headers=admin).status_code == 404


def test_device_from_model_creates_ports_and_keeps_link_on_update(client, admin):
    m = mk_model(client, admin)
    r = client.post("/api/devices", headers=admin, json={"hostname": "sw-neu", "model_id": m["id"], "apply_model_ports": True})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["vendor"] == "Hersteller" and d["model"] == "SW-48" and d["model_id"] == m["id"] and d["port_count"] == 6
    # Update ohne model_id lässt die Verknüpfung stehen
    u = client.put(f"/api/devices/{d['id']}", headers=admin, json={"hostname": "sw-neu", "note": "x"}).json()
    assert u["model_id"] == m["id"]
    # Modell wird verwendet -> nicht löschbar
    assert client.delete(f"/api/device-models/{m['id']}", headers=admin).status_code == 409
    # nachträglich anwenden überspringt vorhandene Ports
    again = client.post(f"/api/devices/{d['id']}/ports/from-model", headers=admin, json={"model_id": m["id"]}).json()
    assert again == {"created": 0, "skipped": 6}
    assert client.post("/api/devices", headers=admin, json={"hostname": "x", "model_id": 999}).status_code == 400


def test_patchpanel_model_dual_ports_have_peers(client, admin):
    m = client.post("/api/device-models", headers=admin, json={
        "vendor": "V", "model": "PP24", "type": "patchpanel",
        "ports": [{"prefix": "P", "count": 3, "medium": "RJ45", "dual": True}]}).json()
    d = client.post("/api/devices", headers=admin, json={"hostname": "pp-x", "type": "patchpanel", "model_id": m["id"],
                                                         "apply_model_ports": True}).json()
    ports = client.get(f"/api/devices/{d['id']}/ports", headers=admin).json()
    assert len(ports) == 6 and all(p["peer_port_id"] for p in ports)


def test_generic_models_are_seeded(client, admin):
    ms = {m["model"]: m for m in client.get("/api/device-models?q=Generisch", headers=admin).json()}
    assert {n: ms[f"Switch {n} Port"]["port_total"] for n in (8, 12, 16, 24)} == {8: 8, 12: 12, 16: 16, 24: 24}
    assert {n: ms[f"Patchfeld Cat6A {n} Port"]["port_total"] for n in (8, 12, 24)} == {8: 16, 12: 24, 24: 48}   # dual: Vorder- + Rückseite
    assert ms["Patchfeld Cat6A 12 Port"]["type"] == "patchpanel"
    d = client.post("/api/devices", headers=admin, json={"hostname": "pp-gen", "type": "patchpanel",
                    "model_id": ms["Patchfeld Cat6A 8 Port"]["id"], "apply_model_ports": True}).json()
    ports = client.get(f"/api/devices/{d['id']}/ports", headers=admin).json()
    assert len(ports) == 16 and all(p["peer_port_id"] for p in ports)


def test_generic_uplink_and_fiber_models(client, admin):
    ms = {m["model"]: m for m in client.get("/api/device-models?q=Generisch", headers=admin).json()}
    assert ms["Switch 8 Port + 2 SFP"]["port_total"] == 10 and ms["Switch 24 Port + 4 SFP+"]["port_total"] == 28
    sfp = ms["Switch 16 Port + 2 SFP"]["ports"][1]
    assert sfp["medium"] == "SFP" and sfp["count"] == 2
    assert ms["Switch 24 Port + 4 SFP+"]["ports"][1]["speed_mbps"] == 10000
    assert {n: ms[f"Patchfeld LWL {n} Port"]["port_total"] for n in (8, 12, 24)} == {8: 16, 12: 24, 24: 48}
    assert ms["Patchfeld LWL 12 Port"]["ports"][0]["medium"] == "LWL"
    d = client.post("/api/devices", headers=admin, json={"hostname": "sw-up", "model_id": ms["Switch 8 Port + 2 SFP"]["id"],
                                                         "apply_model_ports": True}).json()
    names = [p["name"] for p in client.get(f"/api/devices/{d['id']}/ports", headers=admin).json()]
    assert "Port8" in names and "SFP2" in names and len(names) == 10

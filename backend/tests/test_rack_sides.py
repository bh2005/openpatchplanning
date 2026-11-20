"""Racks mit Vorder- und Rückseite; Hochkant-Geräte (PDU) im Seitenkanal."""
import pytest


def model_id(client, admin, name):
    return [m for m in client.get("/api/device-models?q=Generisch", headers=admin).json() if m["model"] == name][0]["id"]


@pytest.fixture()
def rack(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    r = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": "R1", "rack_units": 20}).json()
    return {"rack": r["id"], "site": s["id"]}


def wiz(client, admin, rack, **kw):
    body = {"hostname": "x", "type": "switch", "location_id": rack["rack"], "rack_position": 5, **kw}
    return client.post("/api/wizards/device", headers=admin, json=body)


def test_front_and_rear_devices_share_the_same_he(client, admin, rack):
    assert wiz(client, admin, rack, hostname="vorn", mount_side="front").status_code == 200
    hinten = wiz(client, admin, rack, hostname="hinten", mount_side="rear")
    assert hinten.status_code == 200, hinten.text                                  # gleiche HE, andere Seite: erlaubt (halbe Tiefe)
    q = wiz(client, admin, rack, hostname="noch-einer", mount_side="front")
    assert q.status_code == 409 and q.json()["detail"]["code"] == "slot_busy"      # vorne belegt
    durch = wiz(client, admin, rack, hostname="durchgehend", mount_side="both")
    assert durch.status_code == 409                                                # beide Seiten: kollidiert mit vorn und hinten
    assert len(durch.json()["detail"]["conflicts"]) == 2
    assert {d["hostname"]: d["mount_side"] for d in client.get(f"/api/wizards/rack-slots/{rack['rack']}", headers=admin).json()["devices"]} == {"vorn": "front", "hinten": "rear"}


def test_default_for_existing_devices_is_full_depth(client, admin, rack):
    d = client.post("/api/devices", headers=admin, json={"hostname": "alt", "location_id": rack["rack"], "rack_position": 3}).json()
    assert d["mount_side"] == "both" and d["orientation"] == "horizontal" and d["side_slot"] == ""
    assert client.post("/api/devices", headers=admin, json={"hostname": "neu", "location_id": rack["rack"], "rack_position": 3, "mount_side": "rear"}).status_code == 409
    other = client.post("/api/devices", headers=admin, json={"hostname": "neu", "location_id": rack["rack"], "rack_position": 4, "mount_side": "rear"})
    assert other.status_code == 201 and other.json()["mount_side"] == "rear"


def test_vertical_pdus_left_and_right_at_the_rear(client, admin, rack):
    pdu = model_id(client, admin, "PDU hochkant 24x C13 (42 HE)")
    a = client.post("/api/wizards/device", headers=admin, json={"hostname": "pdu-a", "type": "pdu", "model_id": pdu, "location_id": rack["rack"], "side_slot": "left"})
    assert a.status_code == 200, a.text
    pa = a.json()["device"]
    assert pa["orientation"] == "vertical" and pa["mount_side"] == "rear" and pa["side_slot"] == "left"
    assert pa["rack_position"] == 1 and pa["height_u"] == 20                        # Länge höchstens bis zur Rackhöhe (42 -> 20)
    assert client.post("/api/wizards/device", headers=admin, json={"hostname": "pdu-b", "type": "pdu", "model_id": pdu, "location_id": rack["rack"], "side_slot": "right"}).status_code == 200
    dup = client.post("/api/wizards/device", headers=admin, json={"hostname": "pdu-c", "type": "pdu", "model_id": pdu, "location_id": rack["rack"], "side_slot": "left"})
    assert dup.status_code == 409 and "Seitenkanal" in dup.json()["detail"]["message"]       # Kanal hinten links ist belegt
    front = client.post("/api/wizards/device", headers=admin, json={"hostname": "pdu-d", "type": "pdu", "model_id": pdu, "location_id": rack["rack"],
                                                                   "side_slot": "left", "mount_side": "front"})
    assert front.status_code == 200                                                          # vorne links ist ein anderer Kanal
    # PDUs blockieren keine 19-Zoll-HE
    assert wiz(client, admin, rack, hostname="sw", rack_position=1, height_u=20, mount_side="both").status_code == 200


def test_vertical_validation(client, admin, rack):
    pdu = model_id(client, admin, "PDU hochkant 12x C13 (24 HE)")
    base = {"hostname": "p", "type": "pdu", "model_id": pdu, "location_id": rack["rack"]}
    post = lambda **kw: client.post("/api/wizards/device", headers=admin, json={**base, **kw}).status_code  # noqa: E731
    assert post() == 200                                                                      # Modell bringt rear/right mit
    assert post(hostname="p2", side_slot="mitte") == 400
    assert post(hostname="p3", mount_side="both", side_slot="left") == 400                    # hochkant nur vorne oder hinten
    assert post(hostname="p4", orientation="schräg") == 400
    room = client.post("/api/locations", headers=admin, json={"site_id": rack["site"], "kind": "room", "name": "Raum"}).json()
    r = client.post("/api/wizards/device", headers=admin, json={**base, "hostname": "p5", "location_id": room["id"]})
    assert r.status_code == 400 and "Rack" in r.json()["detail"]                              # Seitenkanal gibt es nur im Rack
    # direkte API: hochkant ohne Seitenkanal
    assert client.post("/api/devices", headers=admin, json={"hostname": "p6", "location_id": rack["rack"], "orientation": "vertical"}).status_code == 400
    ok = client.post("/api/devices", headers=admin, json={"hostname": "p7", "location_id": rack["rack"], "orientation": "vertical", "side_slot": "right", "mount_side": "front"})
    assert ok.status_code == 201 and ok.json()["rack_position"] is None                       # ohne Position = ganze Höhe
    clash = client.post("/api/devices", headers=admin, json={"hostname": "p8", "location_id": rack["rack"], "orientation": "vertical", "side_slot": "right",
                                                              "mount_side": "front", "rack_position": 3, "height_u": 2})
    assert clash.status_code == 409                                                           # volle Höhe belegt jede Teilstrecke


def test_vertical_segments_do_not_collide_when_hes_differ(client, admin, rack):
    mk = lambda name, pos, h: client.post("/api/devices", headers=admin, json={  # noqa: E731
        "hostname": name, "location_id": rack["rack"], "orientation": "vertical", "side_slot": "left", "mount_side": "rear", "rack_position": pos, "height_u": h})
    assert mk("kf-unten", 1, 5).status_code == 201
    assert mk("kf-oben", 6, 5).status_code == 201                                             # unterschiedliche Abschnitte im selben Kanal
    assert mk("kf-mitte", 5, 2).status_code == 409


def test_update_keeps_mount_fields_when_not_sent_and_validates_changes(client, admin, rack):
    d = client.post("/api/devices", headers=admin, json={"hostname": "u1", "location_id": rack["rack"], "rack_position": 5, "mount_side": "front"}).json()
    u = client.put(f"/api/devices/{d['id']}", headers=admin, json={"hostname": "u1", "location_id": rack["rack"], "rack_position": 5, "note": "x"}).json()
    assert u["mount_side"] == "front"                                                         # nicht mitgesendet -> unverändert
    client.post("/api/devices", headers=admin, json={"hostname": "u2", "location_id": rack["rack"], "rack_position": 5, "mount_side": "rear"})
    clash = client.put(f"/api/devices/{d['id']}", headers=admin, json={"hostname": "u1", "location_id": rack["rack"], "rack_position": 5, "mount_side": "both"})
    assert clash.status_code == 409                                                           # auf beide Seiten erweitern kollidiert mit hinten


def test_rack_slots_respect_side_and_orientation(client, admin, rack):
    wiz(client, admin, rack, hostname="vorn", mount_side="front", rack_position=5, height_u=2)
    q = lambda **kw: client.get(f"/api/wizards/rack-slots/{rack['rack']}", params={"height_u": 1, **kw}, headers=admin).json()  # noqa: E731
    assert 5 not in q(mount_side="front")["free_starts"] and 6 not in q(mount_side="front")["free_starts"]
    assert 5 in q(mount_side="rear")["free_starts"]                                           # hinten ist die HE frei
    assert 5 not in q(mount_side="both")["free_starts"]
    v = q(orientation="vertical", mount_side="rear", side_slot="left")
    assert 5 in v["free_starts"]                                                              # Seitenkanal unabhängig von der 19-Zoll-Belegung
    assert client.get(f"/api/wizards/rack-slots/{rack['rack']}", params={"orientation": "vertical", "mount_side": "rear"}, headers=admin).status_code == 400   # Kanal fehlt


def test_catalog_model_carries_mount_defaults(client, admin):
    m = client.post("/api/device-models", headers=admin, json={"model": "Eigene PDU", "type": "pdu", "height_u": 30, "orientation": "vertical",
                                                               "mount_side": "rear", "side_slot": "left"}).json()
    assert (m["orientation"], m["mount_side"], m["side_slot"]) == ("vertical", "rear", "left")
    assert client.post("/api/device-models", headers=admin, json={"model": "Kaputt", "orientation": "vertical", "mount_side": "both"}).status_code == 400
    pdus = {x["model"] for x in client.get("/api/device-models?type=pdu", headers=admin).json()}
    assert {"PDU hochkant 24x C13 (42 HE)", "PDU hochkant 12x C13 (24 HE)", "PDU 1 HE 8x C13 (hinten)"} <= pdus
    vert = {x["model"] for x in client.get("/api/device-models?orientation=vertical", headers=admin).json()}
    assert "Kabelführung hochkant (42 HE)" in vert and "PDU 1 HE 8x C13 (hinten)" not in vert

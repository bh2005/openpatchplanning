"""Blindblende vorne und Kabelführung hinten auf derselben HE (Wunsch: Rückseite wird nicht durch Frontblenden blockiert)."""
import pytest


@pytest.fixture()
def rack(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    r = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": "R1", "rack_units": 12}).json()
    return r["id"]


def model(client, admin, name):
    return [m for m in client.get("/api/device-models?q=Generisch", headers=admin).json() if m["model"] == name][0]


def test_passive_models_are_single_sided_and_shelf_is_full_depth(client, admin):
    assert model(client, admin, "Blindblende 1 HE")["mount_side"] == "front"
    assert model(client, admin, "Kabelführung 1 HE")["mount_side"] == "front"
    assert model(client, admin, "Bürstenpanel 1 HE")["mount_side"] == "front"
    assert model(client, admin, "Fachboden 1 HE")["mount_side"] == "both"                   # Fachboden trägt Geräte: durchgehend
    assert model(client, admin, "Kabelführung hochkant (42 HE)")["mount_side"] == "rear"    # unverändert


def test_blank_panel_in_front_does_not_block_cable_guide_at_the_rear(client, admin, rack):
    bb, kf = model(client, admin, "Blindblende 1 HE"), model(client, admin, "Kabelführung 1 HE")
    # Blindblende über den Katalog (Modellvorgabe), ohne Seite anzugeben
    a = client.post("/api/wizards/device", headers=admin, json={"type": "blank_panel", "model_id": bb["id"], "location_id": rack, "rack_position": 4})
    assert a.status_code == 200, a.text
    assert a.json()["device"]["mount_side"] == "front"
    # Kabelführung hinten auf derselben HE: möglich
    b = client.post("/api/wizards/device", headers=admin, json={"type": "cable_mgmt", "model_id": kf["id"], "location_id": rack, "rack_position": 4, "mount_side": "rear"})
    assert b.status_code == 200, b.text
    # vorne ist belegt, hinten jetzt auch
    assert client.post("/api/wizards/device", headers=admin, json={"type": "cable_mgmt", "model_id": kf["id"], "location_id": rack, "rack_position": 4, "mount_side": "front"}).status_code == 409
    assert client.post("/api/wizards/device", headers=admin, json={"type": "cable_mgmt", "model_id": kf["id"], "location_id": rack, "rack_position": 4, "mount_side": "rear"}).status_code == 409
    slots = lambda side: client.get(f"/api/wizards/rack-slots/{rack}", params={"mount_side": side}, headers=admin).json()["free_starts"]  # noqa: E731
    assert 4 not in slots("front") and 4 not in slots("rear") and 5 in slots("rear")


def test_rear_slot_is_free_when_only_the_front_is_occupied(client, admin, rack):
    bb = model(client, admin, "Blindblende 2 HE")
    client.post("/api/wizards/device", headers=admin, json={"type": "blank_panel", "model_id": bb["id"], "location_id": rack, "rack_position": 3})
    free_rear = client.get(f"/api/wizards/rack-slots/{rack}", params={"mount_side": "rear", "height_u": 2}, headers=admin).json()["free_starts"]
    assert 3 in free_rear and 4 in free_rear                                               # hinten frei, obwohl vorne belegt
    free_front = client.get(f"/api/wizards/rack-slots/{rack}", params={"mount_side": "front", "height_u": 2}, headers=admin).json()["free_starts"]
    assert 3 not in free_front and 4 not in free_front and 2 not in free_front              # 2 würde HE 3 überlappen

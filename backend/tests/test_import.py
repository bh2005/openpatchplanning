import io
import json

from app import importer
from conftest import make_token

DEV = {"hostname": "sw-01", "type": "switch", "vendor": "Beispiel", "model": "X-48", "mgmt_ip": "192.0.2.10",
       "location": "SITE-A/Gebäude 1/Raum 2/Rack 3", "ext_id": "asset-1",
       "ports": [{"name": "Gi1/0/1", "medium": "RJ45", "speed_mbps": 1000, "description": "Uplink"},
                 {"name": "Gi1/0/2", "speed_mbps": "10G"}]}


def imp(client, headers, devices, **kw):
    r = client.post("/api/import/json", headers=headers, json={"devices": devices, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def count(table):
    from app import db
    return db.row(f"SELECT COUNT(*) AS n FROM {table}")["n"]


def test_import_creates_devices_ports_and_locations(client, admin):
    res = imp(client, admin, [DEV], dry_run=False)
    assert res["applied"] and res["stats"] == {"created": 1, "updated": 0, "unchanged": 0, "errors": 0}
    d = client.get("/api/devices", headers=admin).json()["items"][0]
    assert d["hostname"] == "sw-01" and d["source"] == "json" and d["location_path"] == "SITE-A / Gebäude 1 / Raum 2 / Rack 3"
    ports = client.get(f"/api/devices/{d['id']}/ports", headers=admin).json()
    assert [(p["name"], p["speed_mbps"]) for p in ports] == [("Gi1/0/1", 1000), ("Gi1/0/2", 10000)]


def test_import_is_idempotent(client, admin):
    imp(client, admin, [DEV], dry_run=False)
    again = imp(client, admin, [DEV], dry_run=False)
    assert again["stats"] == {"created": 0, "updated": 0, "unchanged": 1, "errors": 0}
    assert count("devices") == 1 and count("ports") == 2 and count("locations") == 3


def test_import_updates_changes_and_keeps_empty_fields(client, admin):
    imp(client, admin, [DEV], dry_run=False)
    res = imp(client, admin, [{"hostname": "SW-01", "model": "X-96", "vendor": "", "mgmt_ip": "", "ports": [{"name": "Gi1/0/1", "description": ""}, {"name": "Gi1/0/3"}]}], dry_run=False)
    assert res["stats"]["updated"] == 1
    d = client.get("/api/devices", headers=admin).json()["items"][0]
    assert d["model"] == "X-96" and d["vendor"] == "Beispiel" and d["mgmt_ip"] == "192.0.2.10"       # leere Felder überschreiben nichts
    ports = {p["name"]: p for p in client.get(f"/api/devices/{d['id']}/ports", headers=admin).json()}
    assert ports["Gi1/0/1"]["description"] == "Uplink" and "Gi1/0/3" in ports and "Gi1/0/2" in ports   # nichts gelöscht


def test_ext_id_match_renames_device_instead_of_duplicating(client, admin):
    imp(client, admin, [DEV], dry_run=False)
    res = imp(client, admin, [{**DEV, "hostname": "sw-01-neu", "ports": []}], dry_run=False)
    assert res["stats"] == {"created": 0, "updated": 1, "unchanged": 0, "errors": 0}
    assert "Hostname: sw-01 → sw-01-neu" in res["items"][0]["changes"]
    got = client.get("/api/devices", headers=admin).json()
    assert got["total"] == 1 and got["items"][0]["hostname"] == "sw-01-neu"


def test_rename_to_existing_hostname_is_an_error(client, admin):
    imp(client, admin, [DEV, {"hostname": "sw-02"}], dry_run=False)
    res = imp(client, admin, [{**DEV, "hostname": "sw-02", "ports": []}], dry_run=False)
    assert res["stats"]["errors"] == 1 and not res["applied"]


def test_dry_run_changes_nothing(client, admin):
    res = imp(client, admin, [DEV], dry_run=True)
    assert res["dry_run"] and not res["applied"] and res["stats"]["created"] == 1
    assert count("devices") == 0 and count("ports") == 0 and count("sites") == 0
    run = client.get(f"/api/import/runs/{res['run_id']}", headers=admin).json()
    assert run["dry_run"] is True and run["stats"]["applied"] is False


def test_atomic_import_with_error_applies_nothing(client, admin):
    res = imp(client, admin, [DEV, {"hostname": "kaputt", "type": "toaster"}], dry_run=False)
    assert not res["applied"] and res["stats"]["errors"] == 1
    assert count("devices") == 0 and count("sites") == 0
    assert any(i["outcome"] == "error" and "toaster" in i["message"] for i in res["items"])


def test_non_atomic_import_keeps_valid_records(client, admin):
    res = imp(client, admin, [DEV, {"hostname": "kaputt", "type": "toaster"}], dry_run=False, atomic=False)
    assert res["applied"] and res["stats"] == {"created": 1, "updated": 0, "unchanged": 0, "errors": 1}
    assert count("devices") == 1


def test_validation_errors_are_reported_per_row(client, admin):
    res = imp(client, admin, [{"hostname": ""}, {"hostname": "a", "ports": [{"name": "x", "medium": "Pappe"}]},
                              {"hostname": "b", "ports": [{"name": "p"}, {"name": "P"}]}, {"hostname": "c"}, {"hostname": "C"}], dry_run=True)
    msgs = {i["row"]: i.get("message", "") for i in res["items"] if i["outcome"] == "error"}
    assert "Hostname fehlt" in msgs[1] and "Medium" in msgs[2] and "doppelt" in msgs[3] and "mehrfach" in msgs[5]


def test_type_and_status_aliases(client, admin):
    imp(client, admin, [{"hostname": "pp", "type": "Patchfeld", "status": "geplant"}, {"hostname": "ap", "type": "WLAN"}], dry_run=False)
    got = {d["hostname"]: d for d in client.get("/api/devices", headers=admin).json()["items"]}
    assert got["pp"]["type"] == "patchpanel" and got["pp"]["status"] == "planned" and got["ap"]["type"] == "ap"


def test_unknown_location_without_create_is_an_error(client, admin):
    res = imp(client, admin, [{"hostname": "x", "location": "NIRGENDWO/Raum"}], dry_run=True, create_locations=False)
    assert res["stats"]["errors"] == 1 and "Standort" in res["items"][0]["message"]


def test_speed_parsing():
    assert [importer._speed(x) for x in ("1000", "1G", "10 Gbit/s", "100M", "1000mbps", "2,5G", "")] == [1000, 1000, 10000, 100, 1000, 2500, None]


def test_api_token_import_sets_source_api(client, admin):
    write = make_token(client, admin, "write")
    assert client.post("/api/import/json", headers=write, json={"devices": [DEV], "dry_run": False}).status_code == 200
    assert client.get("/api/devices", headers=admin).json()["items"][0]["source"] == "api"
    read = make_token(client, admin, "read", "lesen")
    assert client.post("/api/import/json", headers=read, json={"devices": [DEV]}).status_code == 403
    assert client.post("/api/import/json", json={"devices": [DEV]}).status_code == 401


def test_runs_listing(client, admin):
    imp(client, admin, [DEV], dry_run=True)
    imp(client, admin, [DEV], dry_run=False)
    runs = client.get("/api/import/runs", headers=admin).json()
    assert len(runs) == 2 and runs[0]["dry_run"] is False and runs[1]["dry_run"] is True and runs[0]["stats"]["created"] == 1


# ── CSV ───────────────────────────────────────────────────────────────────────

CSV_DEVICES = (
    "Hostname;Typ;Hersteller;Modell;Seriennummer;IP;Standort;Bemerkung\n"
    "sw-10;switch;Beispiel;X-24;SN1;192.0.2.21;SITE-A/Gebäude 1/Raum 1;erstes Gerät\n"
    "pp-10;Patchfeld;;24-fach;;;SITE-A/Gebäude 1/Raum 1;\n"
)


def post_csv(client, headers, text, **form):
    return client.post("/api/import/csv", headers=headers, data=form,
                       files={"file": ("export.csv", io.BytesIO(text.encode("utf-8")), "text/csv")})


def test_csv_preview_suggests_german_headers(client, admin):
    r = client.post("/api/import/csv/preview", headers=admin, data={"kind": "devices"},
                    files={"file": ("e.csv", io.BytesIO(CSV_DEVICES.encode()), "text/csv")}).json()
    m = r["suggested_mapping"]
    assert (m["hostname"], m["type"], m["vendor"], m["serial"], m["mgmt_ip"], m["location"], m["note"]) == \
        ("Hostname", "Typ", "Hersteller", "Seriennummer", "IP", "Standort", "Bemerkung")
    assert r["rows"] == 2 and r["sample"][0]["Hostname"] == "sw-10"


def test_csv_import_dry_run_is_default_and_real_run_writes(client, admin):
    dry = post_csv(client, admin, CSV_DEVICES, kind="devices").json()
    assert dry["dry_run"] and count("devices") == 0
    real = post_csv(client, admin, CSV_DEVICES, kind="devices", dry_run="false").json()
    assert real["applied"] and real["stats"]["created"] == 2
    got = {d["hostname"]: d for d in client.get("/api/devices", headers=admin).json()["items"]}
    assert got["pp-10"]["type"] == "patchpanel" and got["sw-10"]["source"] == "csv" and got["sw-10"]["note"] == "erstes Gerät"


def test_csv_with_explicit_mapping_and_comma_delimiter(client, admin):
    text = "name,kind\nsw-x,switch\n"
    mapping = json.dumps({"hostname": "name", "type": "kind"})
    r = post_csv(client, admin, text, kind="devices", mapping=mapping, dry_run="false").json()
    assert r["applied"] and r["mapping"] == {"hostname": "name", "type": "kind"}


def test_csv_ports_are_grouped_per_device(client, admin):
    imp(client, admin, [{"hostname": "sw-p"}], dry_run=False)
    text = "hostname,port,speed,description\nsw-p,Gi1/0/1,1G,Uplink\nsw-p,Gi1/0/2,100M,\nneu-sw,Te1/1/1,10G,Core\n"
    r = post_csv(client, admin, text, kind="ports", dry_run="false").json()
    assert r["applied"] and r["stats"]["created"] == 1 and r["stats"]["updated"] == 1
    d = {x["hostname"]: x for x in client.get("/api/devices", headers=admin).json()["items"]}
    assert d["sw-p"]["port_count"] == 2 and d["neu-sw"]["port_count"] == 1


def test_csv_missing_required_column_and_bad_inputs(client, admin):
    assert post_csv(client, admin, "foo;bar\n1;2\n", kind="devices").status_code == 400
    assert post_csv(client, admin, "hostname\n", kind="devices").status_code == 400          # keine Datenzeilen
    assert post_csv(client, admin, "hostname\nx\n", kind="geraete").status_code == 400
    assert post_csv(client, admin, "hostname\nx\n", kind="devices", mapping="[1,2]").status_code == 400
    assert client.post("/api/import/csv", headers=admin, files={"file": ("e.csv", io.BytesIO(b"a"), "text/csv")}).status_code in (200, 400)


def test_csv_latin1_encoding(client, admin):
    text = "Hostname;Standort\nsw-1;SITE-A/Gebäude 1\n".encode("cp1252")
    r = client.post("/api/import/csv", headers=admin, data={"kind": "devices", "dry_run": "false"},
                    files={"file": ("e.csv", io.BytesIO(text), "text/csv")}).json()
    assert r["applied"] and client.get("/api/devices", headers=admin).json()["items"][0]["location_path"] == "SITE-A / Gebäude 1"

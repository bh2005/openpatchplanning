import importlib.util
import json
import sys
from pathlib import Path

from app import checkmk
from conftest import make_token


def table(rows):
    return {"Attributes": {}, "Table": {"KeyColumns": [], "Rows": rows}, "Nodes": {}}


def inv(interfaces=None, chassis=None, product="", addresses=None, neighbors=None):
    """Inventarbaum im Format von Checkmk (var/check_mk/inventory/<host>.json), mit Beispieldaten."""
    nodes = {}
    if interfaces is not None:
        net = {"Attributes": {}, "Table": {}, "Nodes": {"interfaces": table(interfaces)}}
        if addresses is not None:
            net["Nodes"]["addresses"] = table(addresses)
        if neighbors is not None:
            net["Nodes"]["lldp_cache"] = {"Attributes": {}, "Table": {}, "Nodes": {"neighbors": table(neighbors)}}
        nodes["networking"] = net
    hw = {"Attributes": {}, "Table": {}, "Nodes": {}}
    if chassis is not None:
        hw["Nodes"]["components"] = {"Attributes": {}, "Table": {}, "Nodes": {"chassis": table(chassis)}}
    hw["Nodes"]["system"] = {"Attributes": {"Pairs": {"product": product}}, "Table": {}, "Nodes": {}}
    nodes["hardware"] = hw
    return {"Attributes": {}, "Table": {}, "Nodes": nodes}


IFACES = [
    {"index": 1, "name": "Mgmt-clip", "description": "Mgmt-clip", "alias": "Mgmt-clip", "speed": 0, "port_type": 24, "admin_status": 1, "oper_status": 1},
    {"index": 2, "name": "1/1", "description": "1/1", "alias": "Uplink Core", "speed": 1_000_000_000, "port_type": 6, "admin_status": 1, "oper_status": 1},
    {"index": 3, "name": "1/2", "description": "1/2", "alias": "1/2", "speed": 100_000_000, "port_type": 6, "admin_status": 1, "oper_status": 2},
    {"index": 4, "name": "1/49", "description": "1/49", "alias": "", "speed": 10_000_000_000, "port_type": 6, "admin_status": 2, "oper_status": 2},
    {"index": 5, "name": "1/3", "description": "1/3", "alias": "", "speed": 0, "port_type": 6, "admin_status": 1, "oper_status": 2},
    {"index": 6, "name": "Vlan 10", "description": "Vlan 10", "alias": "", "speed": 0, "port_type": 135, "admin_status": 1, "oper_status": 1},
]
CHASSIS = [{"index": "1", "name": "X-24 Switch", "model": "X-24-4XE", "serial": "SN-0001", "manufacturer": "Example Networks."}]
ADDR = [{"address": "192.0.2.50", "device": "Vlan 1", "type": "ipv4"}, {"address": "192.0.2.10", "device": "Mgmt-clip", "type": "ipv4"}]
NEIGHBORS = [
    {"local_port": "1/1", "neighbor_name": "core-01", "neighbor_port": "Te1/0/1", "neighbor_address": "192.0.2.1", "capabilities": "Bridge, Router"},
    {"local_port": "1/1", "neighbor_name": "core-01.example.com", "neighbor_port": "Te1/0/1", "capabilities": "Bridge, Router"},   # Dublette
    {"local_port": "1/2", "neighbor_name": "phone-7", "neighbor_port": "Port 1", "capabilities": "Phone"},
    {"local_port": "", "neighbor_name": "ohne-port"},
]


def sample():
    return inv(IFACES, CHASSIS, "X-24-4XE (9.4.2.1)", ADDR, NEIGHBORS)


def test_device_from_inventory_maps_fields_and_ports():
    d = checkmk.device_from_inventory("sw-demo-01", sample(), site_code="SITE-A")
    assert (d["hostname"], d["ext_id"], d["type"], d["vendor"], d["model"], d["serial"], d["mgmt_ip"], d["location"]) == \
        ("sw-demo-01", "sw-demo-01", "switch", "Example Networks", "X-24-4XE", "SN-0001", "192.0.2.10", "SITE-A")
    names = [p["name"] for p in d["ports"]]
    assert names == ["1/1", "1/2", "1/49", "1/3"]                                        # Loopback und VLAN sind keine Ports
    p = {x["name"]: x for x in d["ports"]}
    assert (p["1/1"]["speed_mbps"], p["1/1"]["description"], p["1/1"]["oper_status"]) == (1000, "Uplink Core", "up")
    assert p["1/2"]["description"] == "" and p["1/2"]["oper_status"] == "down"              # Alias == Name: keine Beschreibung
    assert (p["1/49"]["medium"], p["1/49"]["speed_mbps"], p["1/49"]["admin_status"]) == ("SFP+", 10000, "down")
    assert p["1/3"]["speed_mbps"] is None and p["1/3"]["medium"] == ""


def test_include_all_interfaces_keeps_loopback_and_vlan():
    d = checkmk.device_from_inventory("sw", sample(), include_all_interfaces=True)
    assert [p["name"] for p in d["ports"]][0] == "Mgmt-clip" and "Vlan 10" in [p["name"] for p in d["ports"]]


def test_type_guessing():
    ap = inv(IFACES[:2] * 2, [{"model": "AP305C", "manufacturer": "Example"}], "AP305C")
    assert checkmk.device_from_inventory("ap-1", ap)["type"] == "ap"
    fw = inv(IFACES, [{"model": "FortiGate 100F"}], "")
    assert checkmk.device_from_inventory("fw-1", fw)["type"] == "firewall"
    tiny = inv(IFACES[:2], [], "")
    assert checkmk.device_from_inventory("x", tiny)["type"] == "other"                  # weniger als 4 Ports
    assert checkmk.device_from_inventory("x", tiny)["model"] == ""


def test_model_falls_back_to_product_and_host_without_interfaces_is_none():
    d = checkmk.device_from_inventory("sw", inv(IFACES, [], "Y-48 (1.2.3)"))
    assert d["model"] == "Y-48"
    assert checkmk.device_from_inventory("srv", inv(None, None, "")) is None


def test_lldp_neighbors_are_deduplicated():
    nb = checkmk.lldp_neighbors(sample())
    assert [(n["local_port"], n["neighbor_name"], n["neighbor_port"]) for n in nb] == \
        [("1/1", "core-01", "Te1/0/1"), ("1/2", "phone-7", "Port 1")]


def test_records_from_hosts_skips_non_network_hosts():
    recs, lldp, skipped = checkmk.records_from_hosts(
        [{"host": "sw-1", "inventory": sample()}, {"host": "srv-1", "inventory": inv(None, None, "")}])
    assert [r["hostname"] for r in recs] == ["sw-1"] and skipped == ["srv-1"] and list(lldp) == ["sw-1"]
    recs, _, skipped = checkmk.records_from_hosts([{"host": "srv-1", "inventory": {}}], all_hosts=True)
    assert recs[0]["type"] == "other" and not skipped


# ── API ───────────────────────────────────────────────────────────────────────

def payload(**kw):
    return {"hosts": [{"host": "sw-demo-01", "inventory": sample()}, {"host": "srv-1", "inventory": inv(None, None, "")}], **kw}


def test_checkmk_import_dry_run_then_real_and_idempotent(client, admin):
    dry = client.post("/api/import/checkmk", headers=admin, json=payload(dry_run=True, site_code="SITE-A")).json()
    assert dry["dry_run"] and dry["stats"]["created"] == 1 and dry["skipped_hosts"] == ["srv-1"] and dry["lldp_hosts"] == 1
    assert client.get("/api/devices", headers=admin).json()["total"] == 0
    real = client.post("/api/import/checkmk", headers=admin, json=payload(site_code="SITE-A")).json()
    assert real["applied"] and real["stats"]["created"] == 1
    d = client.get("/api/devices", headers=admin).json()["items"][0]
    assert d["source"] == "checkmk" and d["port_count"] == 4 and d["location_path"] == "SITE-A / Allgemein" and d["mgmt_ip"] == "192.0.2.10"
    again = client.post("/api/import/checkmk", headers=admin, json=payload(site_code="SITE-A")).json()
    assert again["stats"] == {"created": 0, "updated": 0, "unchanged": 1, "errors": 0}


def test_checkmk_import_updates_changed_ports_without_deleting(client, admin):
    client.post("/api/import/checkmk", headers=admin, json=payload())
    changed = [dict(i) for i in IFACES]
    changed[1]["alias"] = "Uplink Core 2"
    changed[4]["oper_status"] = 1
    body = {"hosts": [{"host": "sw-demo-01", "inventory": inv(changed[:3], CHASSIS, "X-24-4XE (9.4.2.1)", ADDR)}]}
    res = client.post("/api/import/checkmk", headers=admin, json=body).json()
    assert res["stats"]["updated"] == 1
    d = client.get("/api/devices", headers=admin).json()["items"][0]
    ports = {p["name"]: p for p in client.get(f"/api/devices/{d['id']}/ports", headers=admin).json()}
    assert ports["1/1"]["description"] == "Uplink Core 2" and "1/49" in ports            # Port fehlt in der Quelle -> bleibt


def test_checkmk_import_nothing_importable_and_permissions(client, admin):
    r = client.post("/api/import/checkmk", headers=admin, json={"hosts": [{"host": "srv", "inventory": inv(None, None, "")}]})
    assert r.status_code == 400
    read = make_token(client, admin, "read", "lesen")
    assert client.post("/api/import/checkmk", headers=read, json=payload()).status_code == 403
    write = make_token(client, admin, "write")
    assert client.post("/api/import/checkmk", headers=write, json=payload()).status_code == 200


# ── Export-Skript ─────────────────────────────────────────────────────────────

def load_tool():
    path = Path(__file__).resolve().parents[2] / "tools" / "checkmk_export.py"
    spec = importlib.util.spec_from_file_location("checkmk_export", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["checkmk_export"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_export_tool_reads_only_hosts_with_interfaces(tmp_path):
    tool = load_tool()
    (tmp_path / "sw-1.json").write_text(json.dumps(sample()))
    (tmp_path / "sw-2.json").write_text(json.dumps(sample()))
    (tmp_path / "srv-1.json").write_text(json.dumps(inv(None, None, "")))
    (tmp_path / "sw-1.json.gz").write_bytes(b"\x1f\x8b")                                  # wird ignoriert
    (tmp_path / "kaputt.json").write_text("{nicht json")
    assert [h["host"] for h in tool.load_hosts(tmp_path)] == ["sw-1", "sw-2"]
    assert [h["host"] for h in tool.load_hosts(tmp_path, "^sw-2")] == ["sw-2"]
    assert len(tool.load_hosts(tmp_path, only_with_interfaces=False)) == 3


def test_export_tool_print_mode_roundtrips_into_the_api(tmp_path, capsys, client, admin):
    tool = load_tool()
    (tmp_path / "sw-demo-01.json").write_text(json.dumps(sample()))
    assert tool.main(["--inventory-dir", str(tmp_path), "--print"]) == 0
    exported = json.loads(capsys.readouterr().out)
    res = client.post("/api/import/checkmk", headers=admin, json={**exported, "dry_run": False}).json()
    assert res["applied"] and res["stats"]["created"] == 1

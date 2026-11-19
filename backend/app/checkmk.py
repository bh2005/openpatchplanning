"""Checkmk-Inventar (HW/SW-Inventory) -> Geräte-Datensätze für app.importer.

Eingabe ist der Inventarbaum eines Hosts, wie ihn Checkmk als JSON ablegt
(``var/check_mk/inventory/<host>.json``): ``{"Attributes": …, "Table": …, "Nodes": {"networking": {…}, …}}``.

Genutzte Knoten
  * ``networking.interfaces``            Ports (index, name, description, alias, speed [bit/s], admin_status, oper_status, port_type)
  * ``hardware.components.chassis``      Hersteller, Modell, Seriennummer
  * ``hardware.system``                  Produktbezeichnung (Fallback für das Modell)
  * ``networking.addresses``             Management-IP
  * ``networking.lldp_cache.neighbors``  LLDP-Nachbarn je Port (für den Soll/Ist-Abgleich, Etappe 3)
"""
from __future__ import annotations

import re
from typing import Any, Optional

# IANAifType: 6 ethernetCsmacd, 62 fastEther, 117 gigabitEthernet, 69 fastEtherFX, 71 ieee80211 (WLAN) bewusst nicht
ETHERNET_TYPES = {6, 62, 69, 117}
UP_DOWN = {1: "up", 2: "down", 3: "testing", 4: "unknown", 5: "dormant", 6: "notPresent", 7: "lowerLayerDown"}

_TYPE_HINTS = [
    (re.compile(r"\b(ap\d{2,4}[a-z]?|access ?point|wing|aerohive)\b", re.I), "ap"),
    (re.compile(r"(fortigate|fortinet|palo ?alto|pa-\d|checkpoint|firewall|asa\d)", re.I), "firewall"),
    (re.compile(r"(router|isr\d|asr\d|mx\d|vsp ?8)", re.I), "router"),
]


def node(tree: dict, path: str) -> dict:
    """Unterknoten über einen Punktpfad (``networking.interfaces``) holen; fehlende Knoten liefern {}."""
    cur: Any = tree
    for part in path.split("."):
        cur = (cur or {}).get("Nodes", {}).get(part, {})
    return cur or {}


def rows(tree: dict, path: str) -> list[dict]:
    return list(node(tree, path).get("Table", {}).get("Rows", []) or [])


def attrs(tree: dict, path: str) -> dict:
    return dict(node(tree, path).get("Attributes", {}).get("Pairs", {}) or {})


def _guess_type(model: str, product: str, port_count: int) -> str:
    text = f"{model} {product}"
    for rx, typ in _TYPE_HINTS:
        if rx.search(text):
            return typ
    return "switch" if port_count >= 4 else "other"


def _mgmt_ip(tree: dict) -> str:
    addrs = [a for a in rows(tree, "networking.addresses") if a.get("type") == "ipv4" and a.get("address")]
    if not addrs:
        return ""
    for pattern in (r"mgmt|manage|loop|clip", r"vlan\s*1"):         # Management/Loopback vor Vlan 1 vor der ersten Adresse
        for a in addrs:
            if re.search(pattern, str(a.get("device", "")), re.I):
                return str(a["address"])
    return str(addrs[0]["address"])


def _port(i: dict) -> Optional[dict]:
    name = str(i.get("name") or i.get("description") or "").strip()
    if not name:
        return None
    speed = i.get("speed")
    mbps = int(speed) // 1_000_000 if isinstance(speed, (int, float)) and speed else None
    alias = str(i.get("alias") or "").strip()
    return {
        "name": name,
        "idx": i.get("index") if isinstance(i.get("index"), int) else (int(i["index"]) if str(i.get("index", "")).isdigit() else None),
        "medium": "SFP+" if mbps and mbps >= 10000 else "",        # leer = Standard (RJ45); 10G und mehr sind meist Steckmodule
        "speed_mbps": mbps,
        "description": alias if alias and alias != name else "",
        "admin_status": UP_DOWN.get(i.get("admin_status"), str(i.get("admin_status") or "")),
        "oper_status": UP_DOWN.get(i.get("oper_status"), str(i.get("oper_status") or "")),
    }


def lldp_neighbors(tree: dict) -> list[dict]:
    """LLDP-Nachbarn je lokalem Port (Doppelte pro Port/Nachbar werden zusammengefasst)."""
    out, seen = [], set()
    for n in rows(tree, "networking.lldp_cache.neighbors"):
        local = str(n.get("local_port") or "").strip()
        name = str(n.get("neighbor_name") or n.get("neighbor_id") or "").strip()
        if not local or not name:
            continue
        key = (local, name.split(".")[0].lower(), str(n.get("neighbor_port") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append({"local_port": local, "neighbor_name": name, "neighbor_port": str(n.get("neighbor_port") or ""),
                    "neighbor_address": str(n.get("neighbor_address") or ""), "capabilities": str(n.get("capabilities") or "")})
    return out


def device_from_inventory(host: str, tree: dict, site_code: str = "", include_all_interfaces: bool = False) -> Optional[dict]:
    """Ein Gerät mit Ports aus dem Inventar; None, wenn der Host keine Interfaces hat (kein Netzwerkgerät)."""
    ifaces = rows(tree, "networking.interfaces")
    if not ifaces:
        return None
    ports = []
    for i in ifaces:
        if not include_all_interfaces and i.get("port_type") not in ETHERNET_TYPES:
            continue
        p = _port(i)
        if p:
            ports.append(p)
    chassis = rows(tree, "hardware.components.chassis")
    c0 = chassis[0] if chassis else {}
    product = str(attrs(tree, "hardware.system").get("product") or "")
    model = str(c0.get("model") or c0.get("name") or "").strip() or re.sub(r"\s*\(.*\)\s*$", "", product)
    vendor = str(c0.get("manufacturer") or "").strip().rstrip(".")
    rec: dict = {
        "hostname": host,
        "type": _guess_type(model, product, len(ports)),
        "vendor": vendor,
        "model": model,
        "serial": str(c0.get("serial") or "").strip(),
        "mgmt_ip": _mgmt_ip(tree),
        "ext_id": host,
        "ports": ports,
    }
    if site_code:
        rec["location"] = site_code
    return rec


def records_from_hosts(hosts: list[dict], site_code: str = "", include_all_interfaces: bool = False,
                       all_hosts: bool = False) -> tuple[list[dict], dict[str, list[dict]], list[str]]:
    """hosts: [{"host": "sw-1", "inventory": {…}}] -> (Geräte-Datensätze, LLDP je Host, übersprungene Hosts)."""
    records, lldp, skipped = [], {}, []
    for h in hosts:
        name = str(h.get("host") or "").strip()
        tree = h.get("inventory") or {}
        if not name:
            continue
        rec = device_from_inventory(name, tree, site_code, include_all_interfaces)
        if rec is None:
            if all_hosts:                                        # Host ohne Interfaces trotzdem als Gerät führen
                rec = {"hostname": name, "type": "other", "ext_id": name, "ports": []}
                if site_code:
                    rec["location"] = site_code
            else:
                skipped.append(name)
                continue
        records.append(rec)
        nb = lldp_neighbors(tree)
        if nb:
            lldp[name] = nb
    return records, lldp, skipped

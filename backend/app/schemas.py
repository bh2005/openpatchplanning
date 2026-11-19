"""Konstanten und Eingabemodelle der API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

DEVICE_TYPES = ("switch", "router", "firewall", "ap", "server", "patchpanel", "outlet", "endpoint", "other")
DEVICE_STATUS = ("planned", "active", "retired")
LOCATION_KINDS = ("building", "floor", "room", "rack")
PORT_MEDIA = ("RJ45", "SFP", "SFP+", "SFP28", "QSFP", "LWL", "other")
SOURCES = ("manual", "csv", "json", "api", "checkmk", "openplan")
CABLE_TYPES = ("Cat5e", "Cat6", "Cat6A", "Cat7", "Cat7A",
               "LWL-SM-OS2", "LWL-MM-OM3", "LWL-MM-OM4", "LWL-MM-OM5",
               "DAC", "AOC", "other")


class SiteIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    address: str = ""
    note: str = ""


class LocationIn(BaseModel):
    site_id: int
    parent_id: Optional[int] = None
    kind: str = "room"
    name: str = Field(min_length=1, max_length=120)
    rack_units: Optional[int] = Field(default=None, ge=1, le=100)
    note: str = ""


class DeviceIn(BaseModel):
    hostname: str = Field(min_length=1, max_length=120)
    type: str = "switch"
    vendor: str = ""
    model: str = ""
    serial: str = ""
    mgmt_ip: str = ""
    location_id: Optional[int] = None
    rack_position: Optional[int] = Field(default=None, ge=1, le=100)
    height_u: int = Field(default=1, ge=1, le=50)
    status: str = "active"
    note: str = ""


class PortIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    idx: Optional[int] = None
    medium: str = "RJ45"
    speed_mbps: Optional[int] = Field(default=None, ge=0)
    description: str = ""
    admin_status: str = ""
    oper_status: str = ""


class PortBulkIn(BaseModel):
    """Mehrere Ports anlegen. dual=True legt je einen Vorder- und Rückseiten-Port an und setzt automatisch den Peer."""
    prefix: str = Field(min_length=1, max_length=48)
    start: int = Field(default=1, ge=0)
    count: int = Field(ge=1, le=512)
    medium: str = "RJ45"
    speed_mbps: Optional[int] = Field(default=None, ge=0)
    dual: bool = False
    back_suffix: str = Field(default="-back", max_length=16)


class PeerIn(BaseModel):
    peer_port_id: Optional[int] = None          # None = Durchschleifung lösen


class CableIn(BaseModel):
    port_b_id: Optional[int] = None             # None = Kabel/Verbindung lösen
    cable_label: str = ""
    cable_type: str = "other"
    fiber_count: Optional[int] = Field(default=None, ge=1)
    length_m: Optional[float] = Field(default=None, ge=0)
    color: str = ""
    installed_at: Optional[str] = None          # ISO-Datum YYYY-MM-DD
    measurement_ref: str = ""
    measurement_ok: Optional[bool] = None       # None=nicht gemessen, True=bestanden, False=nicht bestanden
    note: str = ""


WORKORDER_STATUSES = ("draft", "submitted", "approved", "rejected", "in_progress", "done", "confirmed", "rework")
WORKITEM_ACTIONS   = ("connect", "disconnect", "move")
WORKITEM_STATUSES  = ("open", "done", "deviation")
PRIORITIES         = ("low", "normal", "high", "critical")


class WorkOrderIn(BaseModel):
    title:           str = Field(min_length=1, max_length=200)
    description:     str = ""
    priority:        str = "normal"
    location_id:     Optional[int] = None
    planned_from:    Optional[str] = None   # YYYY-MM-DD
    planned_to:      Optional[str] = None
    note:            str = ""
    openplan_project: str = ""
    openplan_task:   str = ""
    openplan_link:   str = ""


class WorkItemIn(BaseModel):
    action:       str = "connect"           # connect | disconnect | move
    port_a_id:    Optional[int] = None
    port_b_id:    Optional[int] = None
    old_port_b_id: Optional[int] = None     # nur bei move: alter Zielport
    cable_label:  str = ""
    cable_type:   str = "other"
    fiber_count:  Optional[int] = Field(default=None, ge=1)
    length_m:     Optional[float] = Field(default=None, ge=0)
    color:        str = ""
    note:         str = ""
    idx:          int = 0


class WorkItemExec(BaseModel):
    """Techniker hakt eine Position ab."""
    item_status:    str = "done"            # done | deviation
    deviation_note: str = ""


class UserCreate(BaseModel):
    username: str
    password: str
    roles: list[str] = ["viewer"]
    full_name: str = ""
    email: str = ""


class UserUpdate(BaseModel):
    roles: Optional[list[str]] = None
    active: Optional[bool] = None
    full_name: Optional[str] = None
    email: Optional[str] = None


class PasswordReset(BaseModel):
    new_password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scope: str = "read"                          # read | write
    expires_days: Optional[int] = Field(default=None, ge=1, le=3650)

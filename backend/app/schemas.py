"""Konstanten und Eingabemodelle der API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

DEVICE_TYPES = ("switch", "router", "firewall", "ap", "server", "patchpanel", "outlet", "endpoint", "other")
DEVICE_STATUS = ("planned", "active", "retired")
LOCATION_KINDS = ("building", "floor", "room", "rack")
PORT_MEDIA = ("RJ45", "SFP", "SFP+", "SFP28", "QSFP", "LWL", "other")
SOURCES = ("manual", "csv", "json", "api", "checkmk", "openplan")


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
    """Mehrere Ports auf einmal anlegen, z. B. prefix=\"Gi1/0/\", start=1, count=48."""
    prefix: str = Field(min_length=1, max_length=48)
    start: int = Field(default=1, ge=0)
    count: int = Field(ge=1, le=512)
    medium: str = "RJ45"
    speed_mbps: Optional[int] = Field(default=None, ge=0)


class PeerIn(BaseModel):
    peer_port_id: Optional[int] = None          # None = Durchschleifung lösen


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

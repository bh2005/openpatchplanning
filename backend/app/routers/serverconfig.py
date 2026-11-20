"""Verwaltung: Anmeldung über AD/LDAP und Server-Zertifikat per ACME (nur Administratoren)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from .. import acme_client, audit, ldap_auth
from ..auth import Principal, require_admin
from ..schemas import AcmeFetchCaIn, AcmeSettingsIn, LdapSettingsIn, LdapTestIn

router = APIRouter(prefix="/api/admin", tags=["verwaltung"])


# ── AD / LDAP ─────────────────────────────────────────────────────────────────

@router.get("/ldap")
def get_ldap(_: Principal = Depends(require_admin)):
    return ldap_auth.public()


@router.put("/ldap")
def put_ldap(body: LdapSettingsIn, me: Principal = Depends(require_admin)):
    out = ldap_auth.save(body.model_dump(exclude_unset=True))
    audit.log(me.name, "settings.ldap.save", "settings", "ldap",
              f"aktiv={out['enabled']}, url={out['url']}, Pflichtgruppe={out['required_group'] or '-'}")
    return out


@router.post("/ldap/test")
def test_ldap(body: LdapTestIn, me: Principal = Depends(require_admin)):
    """Verbindungstest mit den (auch ungespeicherten) Formularwerten; Schritt-für-Schritt-Protokoll."""
    cfg = ldap_auth.merge(body.settings.model_dump(exclude_unset=True) if body.settings else {})
    try:
        ldap_auth.validate({**cfg, "enabled": False})        # Formfehler melden, ohne Pflichtfelder bei „aus“ zu verlangen
    except HTTPException:
        raise
    audit.log(me.name, "settings.ldap.test", "settings", "ldap", f"Test-Benutzer: {body.username or '-'}")
    return ldap_auth.diagnose(cfg, body.username, body.password)


# ── Server-Zertifikat (ACME) ──────────────────────────────────────────────────

@router.get("/tls")
def get_tls(_: Principal = Depends(require_admin)):
    return acme_client.public()


@router.put("/tls")
def put_tls(body: AcmeSettingsIn, me: Principal = Depends(require_admin)):
    out = acme_client.save_settings(body.model_dump(exclude_unset=True))
    audit.log(me.name, "settings.acme.save", "settings", "acme", "Domains: " + ", ".join(out["settings"]["domains"]))
    return out


@router.post("/tls/fetch-ca")
def fetch_tls_ca(body: AcmeFetchCaIn, _: Principal = Depends(require_admin)):
    """CA-Kette (PEM) von einer URL abrufen und prüfen; wird erst mit „Speichern“ übernommen."""
    return acme_client.fetch_ca_chain(body.url.strip())


@router.post("/tls/issue", status_code=202)
def issue_tls(me: Principal = Depends(require_admin)):
    """Zertifikat jetzt anfordern/erneuern (läuft im Hintergrund; Status über GET /api/admin/tls)."""
    s = acme_client.settings()
    if not s["domains"] or not s["directory_url"]:
        raise HTTPException(422, "Zuerst ACME-Directory-URL und mindestens eine Domain eintragen und speichern")
    if not acme_client.start_issue_thread("manuell"):
        raise HTTPException(409, "Es läuft bereits eine Zertifikatsanforderung")
    audit.log(me.name, "tls.issue", "settings", "acme", "Domains: " + ", ".join(s["domains"]))
    return {"started": True}


@router.get("/tls/cert")
def download_tls_cert(_: Principal = Depends(require_admin)):
    """Öffentliche Zertifikatskette (nie der private Schlüssel)."""
    if not acme_client.CERT_FILE.exists():
        raise HTTPException(404, "Noch kein Zertifikat vorhanden")
    return Response(acme_client.CERT_FILE.read_bytes(), media_type="application/x-pem-file",
                    headers={"Content-Disposition": 'attachment; filename="portwerk-fullchain.pem"'})

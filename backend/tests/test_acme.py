import base64
import datetime as dt
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.x509.oid import NameOID

from conftest import make_user, login
from app import acme_client

BASE = "https://ca.test"


def ub64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class FakeCA:
    """Minimale ACME-Server-Attrappe: prüft JWS-Signaturen und die HTTP-01-Antwort der App, signiert CSRs."""

    def __init__(self, fail_validation=False, bad_nonce_once=False):
        self.key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Fake Test CA")])
        now = dt.datetime.now(dt.timezone.utc)
        self.cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(self.key.public_key())
                     .serial_number(1).not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
                     .sign(self.key, hashes.SHA256()))
        self.fail_validation, self.bad_nonce_once = fail_validation, bad_nonce_once
        self.accounts, self.orders, self.authz, self.nonce_n = {}, {}, {}, 0
        self.new_accounts = 0
        self.leaf_pem = ""

    def _nonce(self):
        self.nonce_n += 1
        return "n%d" % self.nonce_n

    def __call__(self, method, url, headers, data, ca_pem):
        path = url[len(BASE):]
        h = {"replay-nonce": self._nonce()}
        if method == "HEAD":
            return 200, h, b""
        if path == "/directory":
            return 200, h, json.dumps({"newNonce": BASE + "/nonce", "newAccount": BASE + "/acct", "newOrder": BASE + "/order"}).encode()
        env = json.loads(data)
        prot = json.loads(ub64(env["protected"]))
        if self.bad_nonce_once:
            self.bad_nonce_once = False
            return 400, h, json.dumps({"type": "urn:ietf:params:acme:error:badNonce", "detail": "bad nonce"}).encode()
        assert prot["url"] == url and prot["alg"] == "ES256" and prot["nonce"].startswith("n")
        jwk = prot.get("jwk") or self.accounts[prot["kid"]]
        pub = ec.EllipticCurvePublicNumbers(int.from_bytes(ub64(jwk["x"]), "big"), int.from_bytes(ub64(jwk["y"]), "big"), ec.SECP256R1()).public_key()
        sig = ub64(env["signature"])
        pub.verify(encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")),
                   ("%s.%s" % (env["protected"], env["payload"])).encode(), ec.ECDSA(hashes.SHA256()))   # wirft bei falscher Signatur
        payload = json.loads(ub64(env["payload"])) if env["payload"] else None
        if path == "/acct":
            self.new_accounts += 1
            self.accounts["/acct/%d" % self.new_accounts] = prot["jwk"]
            h["location"] = BASE + "/acct/%d" % self.new_accounts
            self.accounts[h["location"]] = prot["jwk"]
            return 201, h, b"{}"
        if path == "/order":
            doms = [i["value"] for i in payload["identifiers"]]
            self.orders["/o/1"] = {"doms": doms, "status": "pending"}
            for i, d in enumerate(doms):
                self.authz["/az/%d" % i] = {"dom": d, "status": "pending", "token": "tok%d" % i, "jwk": jwk}
            h["location"] = BASE + "/o/1"
            return 201, h, json.dumps({"status": "pending", "authorizations": [BASE + "/az/%d" % i for i in range(len(doms))], "finalize": BASE + "/fin"}).encode()
        if path.startswith("/az/"):
            a = self.authz[path]
            return 200, h, json.dumps({"status": a["status"], "identifier": {"type": "dns", "value": a["dom"]},
                                       "challenges": [{"type": "dns-01", "url": BASE + "/x", "token": "x"},
                                                      {"type": "http-01", "url": BASE + "/ch" + path[3:], "token": a["token"]}]}).encode()
        if path.startswith("/ch/"):
            a = self.authz["/az/" + path[4:]]
            thumb = acme_client.b64u(__import__("hashlib").sha256(json.dumps(a["jwk"], sort_keys=True, separators=(",", ":")).encode()).digest())
            ok = acme_client.CHALLENGES.get(a["token"]) == "%s.%s" % (a["token"], thumb) and not self.fail_validation
            a["status"] = "valid" if ok else "invalid"
            return 200, h, b"{}"
        if path == "/fin":
            csr = x509.load_der_x509_csr(ub64(payload["csr"]))
            doms = self.orders["/o/1"]["doms"]
            san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
            assert san == doms
            now = dt.datetime.now(dt.timezone.utc)
            leaf = (x509.CertificateBuilder().subject_name(csr.subject).issuer_name(self.cert.subject).public_key(csr.public_key())
                    .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=1)).not_valid_after(now + dt.timedelta(days=90))
                    .add_extension(x509.SubjectAlternativeName([x509.DNSName(d) for d in doms]), critical=False).sign(self.key, hashes.SHA256()))
            self.leaf_pem = leaf.public_bytes(serialization.Encoding.PEM).decode() + self.cert.public_bytes(serialization.Encoding.PEM).decode()
            self.orders["/o/1"]["status"] = "valid"
            return 200, h, json.dumps({"status": "processing"}).encode()
        if path == "/o/1":
            return 200, h, json.dumps({"status": self.orders["/o/1"]["status"], "certificate": BASE + "/cert"}).encode()
        if path == "/cert":
            return 200, h, self.leaf_pem.encode()
        return 404, h, b"{}"


@pytest.fixture()
def acme(client, tmp_path, monkeypatch):
    from app import acme_client
    monkeypatch.setattr(acme_client, "TLS_DIR", tmp_path)
    monkeypatch.setattr(acme_client, "CERT_FILE", tmp_path / "fullchain.pem")
    monkeypatch.setattr(acme_client, "KEY_FILE", tmp_path / "privkey.pem")
    monkeypatch.setattr(acme_client, "ACCOUNT_KEY", tmp_path / "account.key")
    monkeypatch.setattr(acme_client.time, "sleep", lambda s: None)
    ca = FakeCA()
    monkeypatch.setattr(acme_client, "_fetch", ca)
    return acme_client, ca


def cfg(client, admin, **kw):
    body = {"directory_url": BASE + "/directory", "domains": ["host.example.test", "host"], "email": "ops@example.test", **kw}
    r = client.put("/api/admin/tls", headers=admin, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_tls_defaults_are_neutral_and_admin_only(client, admin):
    s = client.get("/api/admin/tls", headers=admin).json()
    assert s["settings"]["directory_url"] == "" and s["settings"]["domains"] == [] and s["cert"] is None
    make_user(client, admin, "p1", roles=("planer",))
    h = login(client, "p1", "Passwort-123")
    assert client.get("/api/admin/tls", headers=h).status_code == 403
    assert client.put("/api/admin/tls", headers=h, json={}).status_code == 403
    assert client.post("/api/admin/tls/issue", headers=h).status_code == 403


def test_tls_validation(client, admin):
    put = lambda **kw: client.put("/api/admin/tls", headers=admin, json=kw).status_code  # noqa: E731
    assert put(directory_url="http://ca.test/directory") == 422            # nur https
    assert put(domains=["a.test"]) == 422                                    # Domain ohne Directory-URL
    assert put(directory_url=BASE + "/d", domains=["*.test"]) == 422         # Wildcards gehen mit HTTP-01 nicht
    assert put(directory_url=BASE + "/d", email="kaputt") == 422
    assert put(directory_url=BASE + "/d", ca_pem="kein pem") == 422
    assert put(directory_url=BASE + "/d", domains=["a.test", "10.1.2.3"]) == 200   # IP-Adresse erlaubt


def test_issue_certificate_with_fake_ca(client, admin, acme):
    mod, ca = acme
    cfg(client, admin)
    assert mod.run_issue("test") is True
    st = client.get("/api/admin/tls", headers=admin).json()
    assert st["cert"]["san"] == ["host.example.test", "host"] and st["cert"]["days_left"] > 80
    assert st["state"]["ok"] and st["settings"]["registered"] is True
    assert (mod.KEY_FILE.stat().st_size > 0) and mod.CHALLENGES == {}         # Tokens werden wieder entfernt
    pem = client.get("/api/admin/tls/cert", headers=admin)
    assert pem.status_code == 200 and b"BEGIN CERTIFICATE" in pem.content and b"PRIVATE KEY" not in pem.content
    assert ca.new_accounts == 1
    assert mod.run_issue("nochmal") is True and ca.new_accounts == 1           # Account wird wiederverwendet


def test_failed_validation_is_reported(client, admin, acme, monkeypatch):
    mod, ca = acme
    ca.fail_validation = True
    cfg(client, admin)
    assert mod.run_issue("test") is False
    st = client.get("/api/admin/tls", headers=admin).json()
    assert st["cert"] is None and st["state"]["ok"] is False and "Validierung" in st["state"]["message"]


def test_issue_endpoint_requires_config_and_renew_due(client, admin, acme):
    mod, ca = acme
    assert client.post("/api/admin/tls/issue", headers=admin).status_code == 422
    cfg(client, admin)
    assert mod.renew_due() is True                                              # noch kein Zertifikat
    mod.run_issue("t")
    assert mod.renew_due() is False
    cfg(client, admin, domains=["host.example.test", "andere"])
    assert mod.renew_due() is True                                              # Domainliste geändert -> neu ausstellen
    cfg(client, admin, auto_renew=False)
    assert mod.renew_due() is False


def test_acme_challenge_route_serves_only_active_tokens(client, acme):
    mod, _ = acme
    mod.CHALLENGES["abc"] = "abc.thumb"
    assert client.get("/.well-known/acme-challenge/abc").text == "abc.thumb"
    assert client.get("/.well-known/acme-challenge/unbekannt").status_code == 404
    mod.CHALLENGES.clear()


def test_san_includes_ip_address(acme):
    mod, _ = acme
    assert isinstance(mod._san_entry("10.1.2.3"), x509.IPAddress) and isinstance(mod._san_entry("a.test"), x509.DNSName)

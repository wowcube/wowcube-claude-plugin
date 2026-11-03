#!/usr/bin/env python3
"""Upload one finished .oct to the WowCube store backend and make the install QR code (Stage 5 delivery).

The user installs the game from their phone: they scan the QR code (or open the link) and the WowCube app
puts the game on the cube connected to that phone. Nothing goes to the cube from this computer.

    python store_upload.py <ws>/dist/app_<game>.oct --yes [--verify] [--qr <png>] [--terminal-qr] [--json]

- `--yes` is required: it says the user agreed to send this file to WowCube's servers (ask once:
  "Upload the game to the WowCube store to get an install QR code?"). Without it nothing is sent (exit 1).
- The endpoint is open (no account, no token): `POST https://wowcube.com/api/v3/upload`, multipart fields
  name / blobType=oct_app / publisher=WowCube / description / file; a User-Agent header is required
  (403 without it); an `icon` field is never sent (the server hangs, 504); timeout 5 minutes.
- The response's `url` (`https://store.wowcube.com/uploads/<id>?password=<pw>`) is the install link; the
  `?password=` part is part of the link and is kept. Every upload makes a new link; old ones keep working.
- The QR code (segno, error level M) is written next to the .oct as `<name>_qr.png` (or `--qr`), and the
  link is printed. `--terminal-qr` also draws it with text characters.
- `--verify`: GET `<endpoint>/<id>?password=<pw>`, download its `file` and compare the SHA-256 (exit 3 on a
  mismatch: upload again).
- `--endpoint` exists for the tests (a local mock server); never point it anywhere the user did not name.

Exit: 0 uploaded (and verified with --verify); 1 bad arguments, no --yes, segno missing (nothing sent);
2 the upload failed (HTTP or network error; reported, retried once only on a 504); 3 verification mismatch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

DEFAULT_ENDPOINT = "https://wowcube.com/api/v3/upload"
HEADERS = {"User-Agent": "Mozilla/5.0 (wowcube-skills store_upload)", "Accept": "application/json"}
TIMEOUT_UPLOAD = 300
TIMEOUT_META = 60


class UploadError(Exception):
    pass


def multipart_body(path: Path, name: str, blob_type: str = "oct_app") -> tuple[bytes, str]:
    """The request body and its Content-Type. Fields as the store expects them; never an `icon` field."""
    data = path.read_bytes()
    boundary = "----wcup" + uuid.uuid4().hex
    parts = []
    for key, value in (("name", name), ("blobType", blob_type), ("publisher", "WowCube"), ("description", name)):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                  'Content-Type: application/octet-stream\r\n\r\n').encode())
    parts.append(data)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def upload(path: Path, endpoint: str = DEFAULT_ENDPOINT, retries_on_504: int = 1) -> str:
    """POST the file; return the install link (with its ?password= part)."""
    body, ctype = multipart_body(path, path.name)
    attempt = 0
    while True:
        req = urllib.request.Request(endpoint, data=body, method="POST", headers={**HEADERS, "Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_UPLOAD) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 504 and attempt < retries_on_504:
                attempt += 1
                print("the store answered 504 (gateway timeout); retrying once", file=sys.stderr)
                continue
            hint = {403: " (forbidden: the User-Agent header is missing or refused)",
                    504: " (gateway timeout: the file was not accepted; try again later)"}.get(e.code, "")
            raise UploadError(f"upload failed: HTTP {e.code}{hint}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise UploadError(f"upload failed: {getattr(e, 'reason', e)}") from None
        except ValueError:
            raise UploadError("upload failed: the store's answer is not JSON") from None
    url = payload.get("url") if isinstance(payload, dict) else None
    if not isinstance(url, str) or "/uploads/" not in url or "password=" not in url:
        raise UploadError(f"upload failed: no install link in the store's answer: {payload!r}")
    return url


def split_link(url: str) -> tuple[str, str]:
    """(upload id, password) from https://store.wowcube.com/uploads/<id>?password=<pw>."""
    parsed = urllib.parse.urlparse(url)
    upload_id = parsed.path.rstrip("/").rsplit("/uploads/", 1)[-1]
    password = urllib.parse.parse_qs(parsed.query).get("password", [""])[0]
    if not upload_id or not password:
        raise UploadError(f"cannot read the upload id and password from {url}")
    return upload_id, password


def verify(url: str, data: bytes, endpoint: str = DEFAULT_ENDPOINT) -> bool:
    """Download what the store holds for this link and compare its SHA-256 with the local file."""
    upload_id, password = split_link(url)
    meta_url = f"{endpoint.rstrip('/')}/{urllib.parse.quote(upload_id)}?password={urllib.parse.quote(password)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(meta_url, headers=HEADERS), timeout=TIMEOUT_META) as r:
            meta = json.loads(r.read().decode("utf-8"))
        with urllib.request.urlopen(urllib.request.Request(meta["file"], headers=HEADERS), timeout=TIMEOUT_UPLOAD) as r:
            remote = r.read()
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as e:
        raise UploadError(f"verification failed: {e}") from None
    return hashlib.sha256(remote).hexdigest() == hashlib.sha256(data).hexdigest()


def make_qr(url: str, out_png: Path):
    import segno
    qr = segno.make(url, error="m")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    qr.save(str(out_png), scale=10, border=4)
    return qr


def terminal_qr(qr) -> str:
    """The QR code drawn with two characters per module (plain ASCII, readable in any terminal font)."""
    rows = []
    matrix = list(qr.matrix_iter(scale=1, border=2))
    for row in matrix:
        rows.append("".join("##" if dark else "  " for dark in row))
    return "\n".join(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("oct", help="the verified .oct (normally <ws>/dist/app_<game>.oct)")
    ap.add_argument("--yes", action="store_true", help="the user agreed to upload this file to the WowCube store")
    ap.add_argument("--verify", action="store_true", help="download the uploaded file and compare its SHA-256")
    ap.add_argument("--qr", help="QR PNG path (default: <oct folder>/<name>_qr.png)")
    ap.add_argument("--terminal-qr", action="store_true", help="also print the QR code with text characters")
    ap.add_argument("--json", action="store_true", help="print one JSON line instead of the text report")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    path = Path(a.oct)
    if path.suffix.lower() != ".oct" or not path.is_file():
        print(f"not an .oct file: {path}", file=sys.stderr)
        return 1
    if not a.yes:
        print(f"nothing sent: uploading puts {path.name} on WowCube's servers; ask the user once, then pass --yes",
              file=sys.stderr)
        return 1
    try:
        import segno  # noqa: F401  (checked before anything is sent: no store entry without its QR code)
    except ImportError:
        print("segno is missing (the QR code): python -m pip install -r <skills>/scripts/requirements.txt",
              file=sys.stderr)
        return 1

    data = path.read_bytes()
    try:
        url = upload(path, a.endpoint)
    except UploadError as e:
        print(str(e), file=sys.stderr)
        return 2
    qr_png = Path(a.qr) if a.qr else path.with_name(path.stem + "_qr.png")
    qr = make_qr(url, qr_png)
    verified = None
    if a.verify:
        try:
            verified = verify(url, data, a.endpoint)
        except UploadError as e:
            print(str(e), file=sys.stderr)
            verified = False
    record = {"oct": str(path.resolve()), "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
              "url": url, "qr": str(qr_png.resolve()), "verified": verified}
    if a.json:
        print(json.dumps(record))
    else:
        print(f"{path.name} - {len(data) / 1048576:.2f} MB - uploaded to the WowCube store")
        print(f"install link: {url}")
        print(f"QR code: {qr_png.resolve()}")
        if verified is not None:
            print("verified: the store holds the same file (SHA-256)" if verified
                  else "MISMATCH: the store's file differs from the local one; upload again")
        if a.terminal_qr:
            print(terminal_qr(qr))
    return 3 if verified is False else 0


if __name__ == "__main__":
    sys.exit(main())

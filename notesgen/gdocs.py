"""Push the notes into Google Docs.

Builds one .docx and uploads it to Drive asking for conversion to a native
Google Doc. That is far more faithful than rebuilding the formatting through
documents.batchUpdate: heading styles become the Docs outline, and the
rendered diagram images come along inside the file.

Note on tabs: the Docs API cannot create them. Both it and Apps Script expose
only getTab / getTabs / getActiveTab / setActiveTab - there is no addTab in
either - so navigation here is the heading outline (View > Show outline),
not tabs.
"""

from __future__ import annotations

import json
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# A whole-course document runs to a couple of MB with diagrams embedded.
# httplib2's default socket timeout is short enough that one slow leg kills
# the transfer, hence the generous timeout and retries.
#
# Deliberately NOT a resumable upload: at this size it buys nothing, and
# httplib2 mishandles the 308 "Resume Incomplete" that chunked uploads reply
# with, failing as RedirectMissingLocation.
UPLOAD_TIMEOUT = 600
UPLOAD_RETRIES = 5
GDOC_MIME = "application/vnd.google-apps.document"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
HTML_MIME = "text/html"

CREDENTIALS_HELP = """\
Google Docs upload needs a one-time OAuth client:

  1. Go to https://console.cloud.google.com/ and create (or pick) a project.
  2. APIs & Services > Library > enable "Google Drive API".
  3. APIs & Services > Credentials > Create credentials > OAuth client ID
     > Application type: Desktop app.
  4. Download the JSON and save it as:
         {path}

Then re-run. A browser opens once to authorise; the token is cached next to
that file so later runs are silent. The scope requested is drive.file, which
only grants access to files this tool itself creates.
"""


class GDocsError(RuntimeError):
    pass


def _paths(config_dir: Path) -> tuple[Path, Path]:
    return config_dir / "google-credentials.json", config_dir / "google-token.json"


def _service(config_dir: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GDocsError(
            "Google Docs upload needs:\n"
            "    pip install google-api-python-client google-auth-oauthlib"
        ) from exc

    creds_file, token_file = _paths(config_dir)
    if not creds_file.exists():
        raise GDocsError(CREDENTIALS_HELP.format(path=creds_file))

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            print("  opening a browser to authorise Google Drive access...")
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        token_file.chmod(0o600)

    import google_auth_httplib2
    import httplib2

    http = google_auth_httplib2.AuthorizedHttp(
        creds, http=httplib2.Http(timeout=UPLOAD_TIMEOUT)
    )
    return build("drive", "v3", http=http, cache_discovery=False)


def _folder(service, name: str) -> str:
    """Find or create a Drive folder owned by this tool."""
    safe = name.replace("'", "\\'")
    existing = service.files().list(
        q=f"name='{safe}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id,name)", pageSize=1,
    ).execute().get("files", [])
    if existing:
        return existing[0]["id"]

    created = service.files().create(
        body={"name": name, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    return created["id"]


def push_file(
    path: Path,
    title: str,
    config_dir: Path,
    manifest,
    *,
    mime: str,
    convert: bool,
    folder_name: str | None = None,
    key: str | None = None,
) -> str:
    """Upload any file to Drive, optionally converting it to a Google Doc.

    `convert=False` keeps the file as-is, which is what the HTML page wants:
    the exported page embeds its diagrams and needs no JavaScript, so Drive
    renders it in preview and the link is shareable as it stands.
    """
    service = _service(config_dir)
    from googleapiclient.http import MediaFileUpload

    key = key or f"__gdoc__/{title}"
    existing = manifest.entries.get(key, {}).get("doc_id")
    media = MediaFileUpload(str(path), mimetype=mime, resumable=False)

    if existing:
        try:
            service.files().get(fileId=existing, fields="id").execute()
            service.files().update(
                fileId=existing, media_body=media
            ).execute(num_retries=UPLOAD_RETRIES)
            url = _url(existing, convert)
            manifest.record(key, hash="", output=str(path), doc_id=existing,
                            status="ok", url=url)
            return url
        except Exception:  # noqa: BLE001 - deleted upstream; recreate below
            pass

    body: dict = {"name": title}
    if convert:
        body["mimeType"] = GDOC_MIME
    if folder_name:
        body["parents"] = [_folder(service, folder_name)]

    created = service.files().create(
        body=body, media_body=media, fields="id"
    ).execute(num_retries=UPLOAD_RETRIES)
    doc_id = created["id"]

    url = _url(doc_id, convert)
    manifest.record(key, hash="", output=str(path), doc_id=doc_id,
                    status="ok", url=url)
    return url


def push(
    docx_path: Path,
    title: str,
    config_dir: Path,
    manifest,
    *,
    folder_name: str | None = None,
    key: str | None = None,
) -> str:
    """Upload one .docx as a Google Doc, updating in place on re-runs."""
    # _service() first: it raises the actionable "pip install ..." / "create an
    # OAuth client" message before any bare ImportError can surface.
    service = _service(config_dir)
    from googleapiclient.http import MediaFileUpload

    key = key or f"__gdoc__/{title}"
    existing = manifest.entries.get(key, {}).get("doc_id")

    media = MediaFileUpload(str(docx_path), mimetype=DOCX_MIME, resumable=False)

    if existing:
        try:
            service.files().get(fileId=existing, fields="id").execute()
            # Re-uploading media to the same file id keeps the URL stable, so
            # links already shared keep working.
            service.files().update(
                fileId=existing, media_body=media
            ).execute(num_retries=UPLOAD_RETRIES)
            manifest.record(key, hash="", output=str(docx_path), doc_id=existing,
                            status="ok", url=_url(existing, True))
            return _url(existing, True)
        except Exception:  # noqa: BLE001 - the doc was deleted; fall through and recreate
            pass

    body = {"name": title, "mimeType": GDOC_MIME}
    if folder_name:
        body["parents"] = [_folder(service, folder_name)]

    created = service.files().create(
        body=body, media_body=media, fields="id"
    ).execute(num_retries=UPLOAD_RETRIES)
    doc_id = created["id"]
    manifest.record(key, hash="", output=str(docx_path), doc_id=doc_id,
                    status="ok", url=_url(doc_id, True))
    return _url(doc_id)


def _url(doc_id: str, convert: bool = True) -> str:
    if convert:
        return f"https://docs.google.com/document/d/{doc_id}/edit"
    # A non-converted file has no Docs editor; this is its Drive preview.
    return f"https://drive.google.com/file/d/{doc_id}/view"

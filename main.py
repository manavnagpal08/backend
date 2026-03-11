from datetime import date, datetime, time as dt_time, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
import os
import smtplib
import time
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import uvicorn


DEFAULT_FIREBASE_PROJECT_ID = "candiatescr"
DEFAULT_FIREBASE_WEB_API_KEY = "AIzaSyAEIgrHYW7PN7CUL_UbY2_j7B3eKbz4IyA"
DEFAULT_RENDER_BASE_URL = "https://backend-x8j1.onrender.com"
DEFAULT_DIGEST_TIMEZONE = "Asia/Kolkata"
APP_NAME = "Candiatescr"

_TOKEN_CACHE = {"id_token": "", "expiry_epoch": 0}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EmailRequest(BaseModel):
    name: str
    email: str
    message: str
    category: str


class ApplicationEmailRequest(BaseModel):
    applicant_name: str
    applicant_email: str
    job_title: str
    company_name: str
    ai_score: float
    ai_decision: str


class InterviewAssignmentEmailRequest(BaseModel):
    candidate_name: str
    candidate_email: str
    topic: str
    company_name: str
    hr_name: str
    question_count: int
    interview_link: str
    assignment_id: str


class CustomEmailRequest(BaseModel):
    to_email: str
    subject: str
    body: str
    html_body: Optional[str] = None
    from_name: Optional[str] = "ScreenerPro"


class DailyDigestRequest(BaseModel):
    force: bool = False
    dry_run: bool = False
    test_email: Optional[str] = None
    triggered_by: Optional[str] = "render_api"
    ignore_disabled: bool = False
    timezone: str = DEFAULT_DIGEST_TIMEZONE


def _env_value(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return default


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _sender_email() -> str:
    return _env_value("EMAIL_USER", default="screenerpro.ai@gmail.com")


def _sender_password() -> str:
    return _env_value("EMAIL_PASS", default="udwi life nbdv kgdt")


def _feedback_receiver_email() -> str:
    return _env_value("FEEDBACK_RECEIVER_EMAIL", default="screenerpro.ai@gmail.com")


def _firestore_project_id() -> str:
    return _env_value(
        "CANDIATESCR_FIREBASE_PROJECT_ID",
        "FLUTTER_FIREBASE_PROJECT_ID",
        default=DEFAULT_FIREBASE_PROJECT_ID,
    )


def _firestore_web_api_key() -> str:
    return _env_value(
        "CANDIATESCR_FIREBASE_WEB_API_KEY",
        "FLUTTER_FIREBASE_WEB_API_KEY",
        default=DEFAULT_FIREBASE_WEB_API_KEY,
    )


def _firestore_root() -> str:
    project_id = _firestore_project_id()
    return f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)"


def _fetch_firestore_id_token() -> str:
    explicit_token = _env_value(
        "FLUTTER_FIREBASE_ID_TOKEN",
        "CANDIATESCR_FIREBASE_ID_TOKEN",
    )
    if explicit_token:
        return explicit_token

    now = int(time.time())
    if _TOKEN_CACHE["id_token"] and now < int(_TOKEN_CACHE["expiry_epoch"]):
        return str(_TOKEN_CACHE["id_token"])

    email = _env_value("FLUTTER_SYNC_EMAIL", "CANDIATESCR_SYNC_EMAIL")
    password = _env_value("FLUTTER_SYNC_PASSWORD", "CANDIATESCR_SYNC_PASSWORD")
    if not email or not password:
        return ""

    auth_url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={_firestore_web_api_key()}"
    )
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True,
    }
    response = requests.post(auth_url, json=payload, timeout=20)
    if response.status_code != 200:
        raise RuntimeError(
            f"Firebase sign-in failed ({response.status_code}): {response.text}"
        )

    body = response.json()
    id_token = str(body.get("idToken", "")).strip()
    expires_in = int(body.get("expiresIn", 0) or 0)
    if id_token and expires_in > 0:
        _TOKEN_CACHE["id_token"] = id_token
        _TOKEN_CACHE["expiry_epoch"] = int(time.time()) + max(expires_in - 120, 60)
    return id_token


def _extract_bearer_token(auth_header: str) -> str:
    value = auth_header.strip()
    if not value:
        return ""
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def _firestore_headers(auth_token: str = "") -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = auth_token.strip() or _fetch_firestore_id_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _python_to_firestore_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return {"timestampValue": value.isoformat()}
    if isinstance(value, date):
        return {"timestampValue": f"{value.isoformat()}T00:00:00+00:00"}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, dict):
        return {
            "mapValue": {
                "fields": {
                    key: _python_to_firestore_value(child)
                    for key, child in value.items()
                }
            }
        }
    if isinstance(value, list):
        return {
            "arrayValue": {
                "values": [_python_to_firestore_value(item) for item in value]
            }
        }
    return {"stringValue": str(value)}


def _to_firestore_document(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "fields": {
            key: _python_to_firestore_value(value)
            for key, value in data.items()
        }
    }


def _firestore_to_python_value(value: dict[str, Any]) -> Any:
    if "nullValue" in value:
        return None
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "timestampValue" in value:
        return str(value["timestampValue"])
    if "stringValue" in value:
        return str(value["stringValue"])
    if "mapValue" in value:
        fields = value.get("mapValue", {}).get("fields", {})
        return {
            key: _firestore_to_python_value(child_value)
            for key, child_value in fields.items()
        }
    if "arrayValue" in value:
        values = value.get("arrayValue", {}).get("values", [])
        return [_firestore_to_python_value(item) for item in values]
    return value


def _from_firestore_document(document: dict[str, Any]) -> dict[str, Any]:
    full_name = str(document.get("name", ""))
    doc_id = full_name.split("/")[-1] if full_name else ""
    doc_path = (
        full_name.split("/documents/", 1)[-1]
        if "/documents/" in full_name
        else ""
    )
    fields = document.get("fields", {})
    parsed = {
        key: _firestore_to_python_value(value)
        for key, value in fields.items()
    }
    parsed["doc_id"] = doc_id
    parsed["doc_path"] = doc_path
    return parsed


def _get_document(
    collection_path: str,
    doc_id: str,
    auth_token: str = "",
) -> dict[str, Any]:
    url = f"{_firestore_root()}/documents/{collection_path}/{doc_id}"
    response = requests.get(
        url,
        params={"key": _firestore_web_api_key()},
        headers=_firestore_headers(auth_token),
        timeout=20,
    )
    if response.status_code == 404:
        return {}
    if response.status_code != 200:
        raise RuntimeError(
            f"Firestore read failed for {collection_path}/{doc_id} "
            f"({response.status_code}): {response.text}"
        )
    return _from_firestore_document(response.json())


def _list_documents(
    collection_path: str,
    page_size: int = 200,
    max_documents: int = 1000,
    auth_token: str = "",
) -> list[dict[str, Any]]:
    url = f"{_firestore_root()}/documents/{collection_path}"
    documents: list[dict[str, Any]] = []
    page_token = ""

    while len(documents) < max_documents:
        params = {
            "key": _firestore_web_api_key(),
            "pageSize": min(page_size, max_documents - len(documents)),
        }
        if page_token:
            params["pageToken"] = page_token

        response = requests.get(
            url,
            params=params,
            headers=_firestore_headers(auth_token),
            timeout=30,
        )
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise RuntimeError(
                f"Firestore read failed for {collection_path} "
                f"({response.status_code}): {response.text}"
            )

        payload = response.json()
        page_documents = payload.get("documents", []) or []
        documents.extend(_from_firestore_document(doc) for doc in page_documents)
        page_token = str(payload.get("nextPageToken", "")).strip()
        if not page_token or not page_documents:
            break

    return documents


def _upsert_document(
    collection_path: str,
    doc_id: str,
    data: dict[str, Any],
    auth_token: str = "",
) -> None:
    url = (
        f"{_firestore_root()}/documents/{collection_path}/{doc_id}"
        f"?key={_firestore_web_api_key()}"
    )
    response = requests.patch(
        url,
        json=_to_firestore_document(data),
        headers=_firestore_headers(auth_token),
        timeout=20,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Firestore write failed for {collection_path}/{doc_id} "
            f"({response.status_code}): {response.text}"
        )


def _add_document(
    collection_path: str,
    data: dict[str, Any],
    auth_token: str = "",
) -> None:
    url = f"{_firestore_root()}/documents/{collection_path}?key={_firestore_web_api_key()}"
    response = requests.post(
        url,
        json=_to_firestore_document(data),
        headers=_firestore_headers(auth_token),
        timeout=20,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Firestore create failed for {collection_path} "
            f"({response.status_code}): {response.text}"
        )


def _send_email_message(
    to_email: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    from_name: str = "ScreenerPro",
) -> None:
    sender_email = _sender_email()
    sender_password = _sender_password()
    if not sender_email or not sender_password:
        raise RuntimeError("EMAIL_USER and EMAIL_PASS must be configured.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{sender_email}>"
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, [to_email], msg.as_string())


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_key(value: Any) -> str:
    return _normalize_text(value).lower()


def _is_true(value: Any) -> bool:
    return value is True or _normalize_key(value) in {"true", "1", "yes", "y", "on"}


def _parse_date(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, dt_time.min)
    elif isinstance(value, (int, float)):
        raw_value = float(value)
        if raw_value > 1_000_000_000_000:
            raw_value = raw_value / 1000.0
        parsed = datetime.fromtimestamp(raw_value, tz=timezone.utc)
    else:
        raw = str(value).strip()
        if not raw:
            return None
        if raw.isdigit():
            return _parse_date(int(raw))
        candidate = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            parsed = None
            for pattern in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%d-%m-%Y %H:%M:%S",
                "%d-%m-%Y",
            ):
                try:
                    parsed = datetime.strptime(raw, pattern)
                    break
                except ValueError:
                    continue
            if parsed is None:
                return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _pick_date(data: dict[str, Any], fields: list[str]) -> Optional[datetime]:
    for field in fields:
        parsed = _parse_date(data.get(field))
        if parsed:
            return parsed
    return None


def _role_bucket(user: dict[str, Any]) -> str:
    role = _normalize_key(user.get("orgRole") or user.get("role"))
    if role in {"hr", "recruiter"}:
        return "hr"
    if "mentor" in role:
        return "mentor"
    if "admin" in role:
        return "admin"
    if role in {"candidate", "student", "learner", "user", ""}:
        return "candidate"
    return role or "candidate"


def _user_matches_digest_roles(
    user: dict[str, Any],
    allowed_roles: list[str],
) -> bool:
    if not allowed_roles:
        return True
    normalized_allowed = {_normalize_key(role) for role in allowed_roles}
    primary = _normalize_key(user.get("role"))
    org_role = _normalize_key(user.get("orgRole"))
    bucket = _role_bucket(user)
    candidates = {primary, org_role, bucket}
    if bucket == "candidate":
        candidates.update({"candidate", "student"})
    if bucket == "hr":
        candidates.update({"hr", "recruiter"})
    return bool(candidates & normalized_allowed)


def _truncate_text(value: Any, max_length: int = 160) -> str:
    text = _normalize_text(value)
    if len(text) <= max_length:
        return text
    return f"{text[:max_length - 3]}..."


def _is_open_job(data: dict[str, Any]) -> bool:
    status = _normalize_key(data.get("status"))
    return status in {"", "active", "open", "published", "live", "ongoing", "recruiting"}


def _is_open_hackathon(data: dict[str, Any]) -> bool:
    status = _normalize_key(data.get("status"))
    return status in {
        "",
        "active",
        "open",
        "published",
        "live",
        "ongoing",
        "registration_open",
        "draft",
    }


def _format_run_key(timezone_name: str) -> str:
    return datetime.now(ZoneInfo(timezone_name)).strftime("%Y-%m-%d")


def _default_digest_config() -> dict[str, Any]:
    return {
        "enabled": False,
        "audienceRoles": ["candidate", "student"],
        "includeJobs": True,
        "includeHackathons": True,
        "maxItems": 6,
        "jobLookbackDays": 7,
        "hackathonLookbackDays": 10,
        "subjectPrefix": "Daily Opportunity Digest",
        "introText": "Fresh opportunities selected for you today.",
        "jobsUrl": "https://candiatescr.web.app/#/jobs",
        "hackathonsUrl": "https://candiatescr.web.app/#/hackathons",
        "deliveryProvider": "render_backend",
        "deliveryTimezone": DEFAULT_DIGEST_TIMEZONE,
        "renderBackendUrl": DEFAULT_RENDER_BASE_URL,
    }


def _build_digest_subject(
    prefix: Any,
    jobs: list[dict[str, Any]],
    hackathons: list[dict[str, Any]],
) -> str:
    safe_prefix = _normalize_text(prefix) or "Daily Opportunity Digest"
    parts = []
    if jobs:
        parts.append(f"{len(jobs)} jobs")
    if hackathons:
        parts.append(f"{len(hackathons)} hackathons")
    return f"{safe_prefix} | {' & '.join(parts)}" if parts else safe_prefix


def _render_opportunity_html(
    items: list[dict[str, Any]],
    item_type: str,
    fallback_url: str,
) -> str:
    safe_url = escape(fallback_url or "#", quote=True)
    rows: list[str] = []
    for item in items:
        if item_type == "job":
            title = _normalize_text(item.get("jobTitle") or item.get("title") or item.get("doc_id") or "Untitled Job")
            company = _normalize_text(item.get("companyName") or item.get("company") or "Candiatescr")
            meta = f"{_normalize_text(item.get('location') or 'Remote')} | {_normalize_text(item.get('experienceLevel') or item.get('jobType') or 'Open')}"
        else:
            title = _normalize_text(item.get("name") or item.get("title") or item.get("doc_id") or "Untitled Hackathon")
            company = _normalize_text(item.get("companyName") or item.get("company") or "Candiatescr")
            meta = f"{_normalize_text(item.get('prize') or 'Opportunity')} | {_normalize_text(item.get('status') or 'active')}"
        summary = _truncate_text(item.get("description") or item.get("summary") or item.get("tagline") or "")
        rows.append(
            f"""
            <tr>
              <td style="padding:14px 0;border-bottom:1px solid #e5e7eb;">
                <div style="font-size:16px;font-weight:700;color:#111827;">{escape(title)}</div>
                <div style="font-size:13px;color:#2563eb;font-weight:600;margin-top:4px;">{escape(company)}</div>
                <div style="font-size:12px;color:#6b7280;margin-top:4px;">{escape(meta)}</div>
                {f'<div style="font-size:13px;color:#374151;margin-top:8px;">{escape(summary)}</div>' if summary else ''}
                <div style="margin-top:10px;">
                  <a href="{safe_url}" style="display:inline-block;background:#0f172a;color:#ffffff;text-decoration:none;padding:8px 12px;border-radius:8px;font-size:12px;font-weight:700;">
                    View {"Jobs" if item_type == "job" else "Hackathons"}
                  </a>
                </div>
              </td>
            </tr>
            """
        )
    return "".join(rows)


def _build_digest_html(
    recipient: dict[str, Any],
    jobs: list[dict[str, Any]],
    hackathons: list[dict[str, Any]],
    config: dict[str, Any],
) -> str:
    first_name = _normalize_text(recipient.get("name")).split(" ")[0] or "there"
    intro_text = _normalize_text(config.get("introText")) or "Fresh opportunities selected for you today."
    jobs_url = escape(_normalize_text(config.get("jobsUrl")) or "#", quote=True)
    hackathons_url = escape(_normalize_text(config.get("hackathonsUrl")) or "#", quote=True)
    jobs_html = (
        f"""
        <h3 style="margin:28px 0 10px 0;color:#0f172a;">Latest Jobs</h3>
        <table style="width:100%;border-collapse:collapse;">{_render_opportunity_html(jobs, "job", _normalize_text(config.get("jobsUrl")))}</table>
        """
        if jobs
        else ""
    )
    hackathons_html = (
        f"""
        <h3 style="margin:28px 0 10px 0;color:#0f172a;">Live Hackathons</h3>
        <table style="width:100%;border-collapse:collapse;">{_render_opportunity_html(hackathons, "hackathon", _normalize_text(config.get("hackathonsUrl")))}</table>
        """
        if hackathons
        else ""
    )

    return f"""
    <html>
      <body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,sans-serif;">
        <div style="max-width:700px;margin:24px auto;background:#ffffff;border-radius:18px;overflow:hidden;box-shadow:0 8px 30px rgba(15,23,42,0.12);">
          <div style="background:linear-gradient(135deg,#0f172a,#0ea5e9);padding:28px 24px;color:#ffffff;">
            <div style="font-size:12px;letter-spacing:1.2px;font-weight:700;opacity:0.85;">CANDIATESCR DAILY DIGEST</div>
            <h2 style="margin:10px 0 0 0;">Fresh opportunities for {escape(first_name)}</h2>
            <p style="margin:10px 0 0 0;opacity:0.9;">{escape(intro_text)}</p>
          </div>
          <div style="padding:26px 24px;color:#1f2937;line-height:1.6;">
            {jobs_html}
            {hackathons_html}
            <div style="margin-top:26px;padding:16px;border-radius:14px;background:#eff6ff;border:1px solid #bfdbfe;">
              <div style="font-size:13px;color:#1d4ed8;font-weight:700;">Quick links</div>
              <div style="margin-top:10px;">
                <a href="{jobs_url}" style="margin-right:10px;color:#0f172a;font-weight:700;">Browse jobs</a>
                <a href="{hackathons_url}" style="color:#0f172a;font-weight:700;">Browse hackathons</a>
              </div>
            </div>
          </div>
          <div style="background:#f8fafc;padding:14px 24px;font-size:12px;color:#6b7280;">
            You are receiving this because your Candiatescr digest is enabled.
          </div>
        </div>
      </body>
    </html>
    """


def _build_digest_text(
    recipient: dict[str, Any],
    jobs: list[dict[str, Any]],
    hackathons: list[dict[str, Any]],
    config: dict[str, Any],
) -> str:
    first_name = _normalize_text(recipient.get("name")).split(" ")[0] or "there"
    lines = [
        f"Hello {first_name},",
        "",
        _normalize_text(config.get("introText")) or "Fresh opportunities selected for you today.",
        "",
    ]

    if jobs:
        lines.append("Latest Jobs:")
        for job in jobs:
            lines.append(
                f"- {_normalize_text(job.get('jobTitle') or job.get('title') or 'Untitled Job')} | "
                f"{_normalize_text(job.get('companyName') or job.get('company') or 'Candiatescr')}"
            )
        lines.append(f"Browse all jobs: {_normalize_text(config.get('jobsUrl'))}")
        lines.append("")

    if hackathons:
        lines.append("Live Hackathons:")
        for hackathon in hackathons:
            lines.append(
                f"- {_normalize_text(hackathon.get('name') or hackathon.get('title') or 'Untitled Hackathon')} | "
                f"{_normalize_text(hackathon.get('companyName') or hackathon.get('company') or 'Candiatescr')}"
            )
        lines.append(f"Browse all hackathons: {_normalize_text(config.get('hackathonsUrl'))}")
        lines.append("")

    lines.extend(["See you in the platform,", "The Candiatescr Team"])
    return "\n".join(lines)


def _load_digest_jobs(
    config: dict[str, Any],
    auth_token: str = "",
) -> list[dict[str, Any]]:
    if config.get("includeJobs") is False:
        return []

    lookback_days = int(config.get("jobLookbackDays") or 7)
    max_items = int(config.get("maxItems") or 6)
    threshold = _now_utc() - timedelta(days=lookback_days)
    documents = _list_documents(
        "jobs",
        page_size=200,
        max_documents=400,
        auth_token=auth_token,
    )

    rows = []
    for job in documents:
        if not _is_open_job(job):
            continue
        event_at = _pick_date(job, ["postedAt", "createdAt", "timestamp"])
        deadline = _pick_date(job, ["deadline", "applicationDeadline", "closingDate"])
        if deadline and deadline < _now_utc():
            continue
        if event_at and event_at < threshold:
            continue
        rows.append(job)

    rows.sort(
        key=lambda item: _pick_date(item, ["postedAt", "createdAt", "timestamp"]) or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )
    return rows[:max_items]


def _load_digest_hackathons(
    config: dict[str, Any],
    auth_token: str = "",
) -> list[dict[str, Any]]:
    if config.get("includeHackathons") is False:
        return []

    lookback_days = int(config.get("hackathonLookbackDays") or 10)
    max_items = int(config.get("maxItems") or 6)
    threshold = _now_utc() - timedelta(days=lookback_days)
    documents = _list_documents(
        "hackathons",
        page_size=200,
        max_documents=400,
        auth_token=auth_token,
    )

    rows = []
    for hackathon in documents:
        if not _is_open_hackathon(hackathon):
            continue
        event_at = _pick_date(
            hackathon,
            ["createdAt", "registrationDeadline", "deadline", "startDate"],
        )
        deadline = _pick_date(
            hackathon,
            ["registrationDeadline", "deadline", "endDate", "lastDate"],
        )
        if deadline and deadline < _now_utc() and _normalize_key(hackathon.get("status")) != "draft":
            continue
        if event_at and event_at < threshold:
            continue
        rows.append(hackathon)

    rows.sort(
        key=lambda item: _pick_date(
            item,
            ["createdAt", "registrationDeadline", "deadline", "startDate"],
        ) or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )
    return rows[:max_items]


def _load_digest_recipients(
    config: dict[str, Any],
    auth_token: str = "",
) -> list[dict[str, Any]]:
    documents = _list_documents(
        "users",
        page_size=250,
        max_documents=5000,
        auth_token=auth_token,
    )
    recipients = []
    for user in documents:
        if _normalize_key(user.get("status")) != "active":
            continue
        if not _normalize_text(user.get("email")):
            continue
        if _is_true(user.get("digestOptOut")):
            continue
        if not _user_matches_digest_roles(user, list(config.get("audienceRoles") or [])):
            continue
        recipients.append(user)
    return recipients


@app.post("/send-email")
async def send_email(request: EmailRequest):
    body = (
        "New Feedback Received\n"
        "---------------------\n"
        f"Name: {request.name}\n"
        f"Email: {request.email}\n"
        f"Category: {request.category}\n\n"
        f"Message:\n{request.message}\n"
    )
    try:
        _send_email_message(
            to_email=_feedback_receiver_email(),
            subject=f"ScreenerPro Feedback: {request.category}",
            body=body,
            from_name="ScreenerPro Feedback",
        )
        return {"status": "success"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/send-application-email")
async def send_application_email(request: ApplicationEmailRequest):
    plain_body = (
        f"Hello {request.applicant_name},\n\n"
        f"We received your application for {request.job_title} at {request.company_name}.\n"
        f"AI Match Score: {request.ai_score:.1f}%\n"
        f"Decision: {request.ai_decision}\n\n"
        "Our team will review your profile and get back to you soon.\n"
    )
    html_body = f"""
    <html>
      <body style="margin:0;padding:0;background-color:#f3f4f6;font-family:Arial,sans-serif;">
        <div style="max-width:600px;margin:20px auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.1);">
          <div style="background:linear-gradient(135deg,#2563eb,#1d4ed8);color:white;text-align:center;padding:30px 20px;">
            <h2 style="margin:0;">Application Received</h2>
            <p style="margin-top:5px;opacity:0.9;">{escape(request.job_title)} at {escape(request.company_name)}</p>
          </div>
          <div style="padding:30px;color:#374151;line-height:1.6;">
            <p>Dear {escape(request.applicant_name)},</p>
            <p>We have received your application for the <b>{escape(request.job_title)}</b> role.</p>
            <div style="background:#f9fafb;border:1px solid #e5e7eb;padding:15px;border-radius:10px;text-align:center;margin:20px 0;">
              <div style="font-size:14px;color:#6b7280;">Your AI Match Score</div>
              <div style="font-size:28px;font-weight:700;color:#059669;">{request.ai_score:.1f}%</div>
              <div style="font-size:16px;font-weight:600;color:#065f46;">Decision: {escape(request.ai_decision)}</div>
            </div>
            <p>Our team will review your profile and get back to you soon.</p>
          </div>
          <div style="background:#f9fafb;padding:15px;text-align:center;font-size:12px;color:#6b7280;">
            2026 {escape(request.company_name)} Careers | Automated Message
          </div>
        </div>
      </body>
    </html>
    """

    try:
        _send_email_message(
            to_email=request.applicant_email,
            subject=f"Application Received - {request.job_title} at {request.company_name}",
            body=plain_body,
            html_body=html_body,
            from_name="ScreenerPro Careers",
        )
        return {"status": "success"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/send-interview-assignment-email")
async def send_interview_assignment_email(request: InterviewAssignmentEmailRequest):
    plain_body = (
        f"Hello {request.candidate_name},\n\n"
        "You have been assigned a mock interview.\n\n"
        f"Company: {request.company_name}\n"
        f"Assigned by: {request.hr_name}\n"
        f"Topic: {request.topic}\n"
        f"Question Count: {request.question_count}\n"
        f"Assignment ID: {request.assignment_id}\n\n"
        f"Open interview:\n{request.interview_link}\n\n"
        "Please complete it at the earliest.\n"
    )
    html_body = f"""
    <html>
      <body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,sans-serif;">
        <div style="max-width:620px;margin:24px auto;background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 4px 14px rgba(0,0,0,0.12);">
          <div style="background:linear-gradient(135deg,#0f172a,#1d4ed8);padding:24px 20px;color:#ffffff;">
            <h2 style="margin:0;">Mock Interview Assigned</h2>
            <p style="margin:8px 0 0 0;opacity:0.9;">Topic: {escape(request.topic)}</p>
          </div>
          <div style="padding:24px;color:#1f2937;line-height:1.6;">
            <p>Hello <strong>{escape(request.candidate_name)}</strong>,</p>
            <p>You have received a new interview assignment.</p>
            <table style="width:100%;border-collapse:collapse;background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;">
              <tr><td style="padding:10px 12px;"><strong>Company</strong></td><td style="padding:10px 12px;">{escape(request.company_name)}</td></tr>
              <tr><td style="padding:10px 12px;"><strong>Assigned by</strong></td><td style="padding:10px 12px;">{escape(request.hr_name)}</td></tr>
              <tr><td style="padding:10px 12px;"><strong>Questions</strong></td><td style="padding:10px 12px;">{request.question_count}</td></tr>
              <tr><td style="padding:10px 12px;"><strong>Assignment ID</strong></td><td style="padding:10px 12px;">{escape(request.assignment_id)}</td></tr>
            </table>
            <div style="margin-top:20px;text-align:center;">
              <a href="{escape(request.interview_link, quote=True)}" style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;padding:12px 18px;border-radius:10px;font-weight:700;">
                Start Interview
              </a>
            </div>
          </div>
          <div style="background:#f9fafb;padding:12px;text-align:center;font-size:12px;color:#6b7280;">
            Automated Interview Assignment Notice
          </div>
        </div>
      </body>
    </html>
    """

    try:
        _send_email_message(
            to_email=request.candidate_email,
            subject=f"Mock Interview Assigned - {request.topic}",
            body=plain_body,
            html_body=html_body,
            from_name="ScreenerPro Interviews",
        )
        return {"status": "success"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/send-custom-email")
async def send_custom_email(request: CustomEmailRequest):
    try:
        _send_email_message(
            to_email=request.to_email,
            subject=request.subject,
            body=request.body,
            html_body=request.html_body,
            from_name=request.from_name or "ScreenerPro",
        )
        return {"status": "success"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/send-daily-digest")
async def send_daily_digest(
    payload: DailyDigestRequest,
    request: Request,
):
    auth_token = _extract_bearer_token(request.headers.get("Authorization", ""))
    time_zone = payload.timezone or DEFAULT_DIGEST_TIMEZONE
    run_key = _format_run_key(time_zone)
    run_doc_id = run_key if not payload.test_email else f"{run_key}-test"
    started_at = _now_utc()

    try:
        existing_run = _get_document(
            "digest_runs",
            run_doc_id,
            auth_token=auth_token,
        )
        if (
            existing_run
            and existing_run.get("status") == "completed"
            and not payload.force
            and not payload.test_email
            and not payload.dry_run
        ):
            return {
                "status": "skipped",
                "reason": "already_completed",
                "runKey": run_doc_id,
                "sentCount": existing_run.get("sentCount", 0),
            }

        config = {
            **_default_digest_config(),
            **_get_document(
                "system_config",
                "daily_digest",
                auth_token=auth_token,
            ),
        }
        config["deliveryProvider"] = "render_backend"
        config["deliveryTimezone"] = time_zone
        config["renderBackendUrl"] = _env_value(
            "DIGEST_BACKEND_URL",
            "RENDER_EMAIL_BACKEND_URL",
            default=DEFAULT_RENDER_BASE_URL,
        )

        if (
            not _is_true(config.get("enabled"))
            and not payload.ignore_disabled
            and not payload.test_email
        ):
            _upsert_document(
                "digest_runs",
                run_doc_id,
                {
                    "status": "skipped",
                    "reason": "disabled",
                    "finishedAt": _now_utc(),
                    "triggeredBy": payload.triggered_by or "render_api",
                    "deliveryProvider": "render_backend",
                    "timeZone": time_zone,
                },
                auth_token=auth_token,
            )
            return {
                "status": "skipped",
                "reason": "disabled",
                "runKey": run_doc_id,
            }

        jobs = _load_digest_jobs(config, auth_token=auth_token)
        hackathons = _load_digest_hackathons(config, auth_token=auth_token)
        recipients = _load_digest_recipients(config, auth_token=auth_token)

        if payload.test_email:
            recipients = [
                {
                    "email": payload.test_email,
                    "name": "Digest Tester",
                    "role": "admin",
                    "doc_id": "digest-test",
                }
            ]

        if payload.dry_run:
            return {
                "status": "dry_run",
                "runKey": run_doc_id,
                "recipientCount": len(recipients),
                "jobsIncluded": len(jobs),
                "hackathonsIncluded": len(hackathons),
                "sampleRecipients": [
                    {
                        "name": _normalize_text(user.get("name")),
                        "email": _normalize_text(user.get("email")),
                    }
                    for user in recipients[:10]
                ],
                "sampleJobs": [
                    _normalize_text(job.get("jobTitle") or job.get("title"))
                    for job in jobs[:6]
                ],
                "sampleHackathons": [
                    _normalize_text(hackathon.get("name") or hackathon.get("title"))
                    for hackathon in hackathons[:6]
                ],
            }

        _upsert_document(
            "digest_runs",
            run_doc_id,
                {
                    "status": "running",
                    "startedAt": started_at,
                    "triggeredBy": payload.triggered_by or "render_api",
                    "deliveryProvider": "render_backend",
                    "timeZone": time_zone,
                },
                auth_token=auth_token,
            )

        if not jobs and not hackathons:
            _upsert_document(
                "digest_runs",
                run_doc_id,
                {
                    "status": "skipped",
                    "reason": "no_content",
                    "finishedAt": _now_utc(),
                    "triggeredBy": payload.triggered_by or "render_api",
                    "deliveryProvider": "render_backend",
                    "timeZone": time_zone,
                },
                auth_token=auth_token,
            )
            return {
                "status": "skipped",
                "reason": "no_content",
                "runKey": run_doc_id,
            }

        if not recipients:
            _upsert_document(
                "digest_runs",
                run_doc_id,
                {
                    "status": "skipped",
                    "reason": "no_recipients",
                    "finishedAt": _now_utc(),
                    "triggeredBy": payload.triggered_by or "render_api",
                    "deliveryProvider": "render_backend",
                    "timeZone": time_zone,
                },
                auth_token=auth_token,
            )
            return {
                "status": "skipped",
                "reason": "no_recipients",
                "runKey": run_doc_id,
            }

        subject = _build_digest_subject(config.get("subjectPrefix"), jobs, hackathons)
        sent_count = 0
        failed: list[dict[str, str]] = []

        for recipient in recipients:
            email = _normalize_text(recipient.get("email"))
            if not email:
                continue
            try:
                _send_email_message(
                    to_email=email,
                    subject=subject,
                    body=_build_digest_text(recipient, jobs, hackathons, config),
                    html_body=_build_digest_html(recipient, jobs, hackathons, config),
                    from_name="Candiatescr Opportunities",
                )
                sent_count += 1
            except Exception as exc:
                failed.append({"email": email, "error": str(exc)})

        status = "completed" if not failed else "completed_with_errors"
        finished_at = _now_utc()

        _upsert_document(
            "digest_runs",
            run_doc_id,
            {
                "status": status,
                "startedAt": started_at,
                "finishedAt": finished_at,
                "triggeredBy": payload.triggered_by or "render_api",
                "deliveryProvider": "render_backend",
                "timeZone": time_zone,
                "totalRecipients": len(recipients),
                "sentCount": sent_count,
                "failedCount": len(failed),
                "jobsIncluded": len(jobs),
                "hackathonsIncluded": len(hackathons),
                "sampleErrors": failed[:20],
                "subject": subject,
            },
            auth_token=auth_token,
        )

        try:
            _add_document(
                "notifications",
                {
                    "title": "Daily digest dispatched",
                    "message": (
                        f"Sent {sent_count} daily digests with {len(jobs)} jobs and "
                        f"{len(hackathons)} hackathons via Render backend."
                    ),
                    "timestamp": finished_at,
                    "type": "digest_job",
                    "recipientCount": sent_count,
                    "deliveryProvider": "render_backend",
                },
                auth_token=auth_token,
            )
        except Exception:
            pass

        return {
            "status": status,
            "runKey": run_doc_id,
            "totalRecipients": len(recipients),
            "sentCount": sent_count,
            "failedCount": len(failed),
            "jobsIncluded": len(jobs),
            "hackathonsIncluded": len(hackathons),
        }
    except Exception as exc:
        try:
            _upsert_document(
                "digest_runs",
                run_doc_id,
                {
                    "status": "failed",
                    "error": str(exc),
                    "finishedAt": _now_utc(),
                    "triggeredBy": payload.triggered_by or "render_api",
                    "deliveryProvider": "render_backend",
                    "timeZone": time_zone,
                },
                auth_token=auth_token,
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)

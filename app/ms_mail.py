"""微软邮箱取件核心：refresh_token -> access_token -> Graph / IMAP 拉信。

支持两种通道：
1. Microsoft Graph（首选，速度快、JSON 友好）
2. IMAP XOAUTH2（回退，scope 仅有 IMAP.AccessAsUser.All 时使用）

设计为无状态：每次调用传入凭据，不在进程内持久化。
"""
from __future__ import annotations

import asyncio
import email as email_lib
import imaplib
import re
from dataclasses import dataclass
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx

MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
IMAP_HOST = "outlook.office365.com"
IMAP_PORT = 993

DEFAULT_TIMEOUT = 30.0


@dataclass
class Credential:
    email: str
    client_id: str
    refresh_token: str
    password: str = ""  # 仅供 IMAP 标识 / 用户参考，刷新令牌不需要
    master_email: str = ""  # 裂变别名场景下的主邮箱

    @property
    def login_email(self) -> str:
        return (self.master_email or self.email).strip()


# ---------------------------------------------------------------------------
# 凭据解析
# ---------------------------------------------------------------------------

def parse_bundle(line: str) -> Credential:
    """email----password----client_id----refresh_token"""
    parts = [p.strip() for p in (line or "").split("----")]
    if len(parts) < 4:
        raise ValueError("凭据格式必须是 email----password----client_id----refresh_token")
    return Credential(
        email=parts[0],
        password=parts[1],
        client_id=parts[2],
        refresh_token="----".join(parts[3:]),
        master_email=parts[0],
    )


# ---------------------------------------------------------------------------
# Token 刷新
# ---------------------------------------------------------------------------

async def refresh_access_token(
    client_id: str,
    refresh_token: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """返回 {access_token, token_type: graph|imap, scope, expires_in, raw}.

    优先尝试 Graph scope，失败回退到 IMAP scope。
    """
    if not client_id or not refresh_token:
        raise ValueError("client_id / refresh_token 不能为空")

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as cli:
        async def _post(scope: str) -> httpx.Response:
            return await cli.post(
                MS_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "scope": scope,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        # 1. Graph 优先
        resp = await _post("https://graph.microsoft.com/.default offline_access")
        data = resp.json() if resp.content else {}
        if resp.status_code == 200 and data.get("access_token"):
            scope = str(data.get("scope", "")).lower()
            kind = "imap" if "imap.accessasuser.all" in scope and "mail.read" not in scope else "graph"
            return {
                "access_token": data["access_token"],
                "token_type": kind,
                "scope": data.get("scope", ""),
                "expires_in": data.get("expires_in", 3600),
                "raw": data,
            }

        body = str(data)
        if "AADSTS70000" in body or "invalid_scope" in body or "AADSTS500011" in body:
            # 2. 回退 IMAP scope
            resp = await _post("https://outlook.office.com/IMAP.AccessAsUser.All offline_access")
            data = resp.json() if resp.content else {}
            if resp.status_code == 200 and data.get("access_token"):
                return {
                    "access_token": data["access_token"],
                    "token_type": "imap",
                    "scope": data.get("scope", ""),
                    "expires_in": data.get("expires_in", 3600),
                    "raw": data,
                }

        raise RuntimeError(f"刷新令牌失败: HTTP {resp.status_code} {data}")


# ---------------------------------------------------------------------------
# 统一邮件结构
# ---------------------------------------------------------------------------

def _normalize_graph(msg: Dict[str, Any]) -> Dict[str, Any]:
    body = msg.get("body") or {}
    body_content = str(body.get("content") or "")
    body_type = str(body.get("contentType") or "html").lower()
    if body_type == "html":
        body_html = body_content
        body_text = re.sub(r"<[^>]+>", " ", body_content)
    else:
        body_html = ""
        body_text = body_content
    return {
        "id": str(msg.get("id", "")),
        "subject": str(msg.get("subject", "") or ""),
        "from": str((msg.get("from") or {}).get("emailAddress", {}).get("address", "") or "").lower(),
        "from_name": str((msg.get("from") or {}).get("emailAddress", {}).get("name", "") or ""),
        "to": [
            str(r.get("emailAddress", {}).get("address", "") or "").lower()
            for r in (msg.get("toRecipients") or [])
        ],
        "date": str(msg.get("receivedDateTime", "") or ""),
        "preview": str(msg.get("bodyPreview", "") or "")[:500],
        "body_html": body_html,
        "body_text": body_text,
        "folder": str(msg.get("parentFolderId", "") or ""),
        "source": "graph",
    }


def _decode_header(value: str) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out: List[str] = []
    for raw, enc in parts:
        if isinstance(raw, bytes):
            try:
                out.append(raw.decode(enc or "utf-8", errors="replace"))
            except Exception:
                out.append(raw.decode("utf-8", errors="replace"))
        else:
            out.append(raw or "")
    return "".join(out)


def _normalize_imap(uid: bytes, raw_bytes: bytes, folder: str) -> Optional[Dict[str, Any]]:
    try:
        msg = email_lib.message_from_bytes(raw_bytes)
    except Exception:
        return None

    subject = _decode_header(msg.get("Subject", ""))
    sender = _decode_header(msg.get("From", ""))
    to = _decode_header(msg.get("To", ""))
    try:
        iso_date = parsedate_to_datetime(msg.get("Date")).isoformat()
    except Exception:
        iso_date = ""

    body_html = ""
    body_text = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/html" and not body_html:
                try:
                    body_html = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    pass
            elif ctype == "text/plain" and not body_text:
                try:
                    body_text = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload is not None:
                decoded = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                if (msg.get_content_type() or "").lower() == "text/html":
                    body_html = decoded
                else:
                    body_text = decoded
        except Exception:
            pass

    if not body_text and body_html:
        body_text = re.sub(r"<[^>]+>", " ", body_html)

    # 提取纯地址
    m = re.search(r"<([^>]+)>", sender)
    sender_addr = (m.group(1) if m else sender).strip().lower()

    to_addrs: List[str] = []
    for tup in re.findall(r"<([^>]+)>|([\w.+-]+@[\w.-]+)", to):
        for x in tup:
            if x:
                to_addrs.append(x.strip().lower())

    return {
        "id": f"imap_{folder}_{uid.decode(errors='replace')}",
        "subject": subject,
        "from": sender_addr,
        "from_name": re.sub(r"<[^>]+>", "", sender).strip(),
        "to": to_addrs,
        "date": iso_date,
        "preview": body_text[:500],
        "body_html": body_html,
        "body_text": body_text,
        "folder": folder,
        "source": "imap",
    }


# ---------------------------------------------------------------------------
# Graph 拉信
# ---------------------------------------------------------------------------

GRAPH_FOLDER_MAP = {
    "inbox": "inbox",
    "junk": "junkemail",
    "junkemail": "junkemail",
    "sent": "sentitems",
    "drafts": "drafts",
    "deleted": "deleteditems",
}


async def fetch_via_graph(
    access_token: str,
    *,
    folder: str = "all",
    top: int = 20,
    timeout: float = DEFAULT_TIMEOUT,
) -> List[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "$select": "id,subject,from,toRecipients,receivedDateTime,bodyPreview,body,parentFolderId",
        "$orderby": "receivedDateTime desc",
        "$top": str(min(max(int(top), 1), 100)),
    }

    async with httpx.AsyncClient(timeout=timeout) as cli:
        async def _query(url: str) -> List[Dict[str, Any]]:
            r = await cli.get(url, headers=headers, params=params)
            if r.status_code != 200:
                raise RuntimeError(f"Graph 拉信失败 HTTP {r.status_code}: {r.text[:200]}")
            return r.json().get("value", [])

        folder_l = (folder or "all").lower()
        if folder_l == "all":
            # 默认 /me/messages 跨所有文件夹
            items = await _query(f"{GRAPH_BASE}/me/messages")
        elif folder_l == "inbox_junk":
            inbox = await _query(f"{GRAPH_BASE}/me/mailFolders/inbox/messages")
            junk = await _query(f"{GRAPH_BASE}/me/mailFolders/junkemail/messages")
            items = (inbox or []) + (junk or [])
        else:
            mapped = GRAPH_FOLDER_MAP.get(folder_l, folder_l)
            items = await _query(f"{GRAPH_BASE}/me/mailFolders/{mapped}/messages")

    return [_normalize_graph(m) for m in items]


# ---------------------------------------------------------------------------
# IMAP XOAUTH2 拉信（同步，放进 to_thread 里跑）
# ---------------------------------------------------------------------------

def _imap_fetch_blocking(
    login_email: str,
    access_token: str,
    folders: List[str],
    top: int,
) -> List[Dict[str, Any]]:
    auth_string = f"user={login_email}\x01auth=Bearer {access_token}\x01\x01"
    out: List[Dict[str, Any]] = []
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        imap.authenticate("XOAUTH2", lambda _: auth_string.encode("ascii"))
        for folder in folders:
            try:
                status, _data = imap.select(folder, readonly=True)
                if status != "OK":
                    continue
                _typ, search = imap.search(None, "ALL")
                uids = search[0].split()
                if not uids:
                    continue
                # 取最近 top 封
                want = uids[-top:]
                for uid in reversed(want):
                    _t, raw = imap.fetch(uid, "(RFC822)")
                    if not raw or not raw[0]:
                        continue
                    norm = _normalize_imap(uid, raw[0][1], folder)
                    if norm:
                        out.append(norm)
            except Exception:
                continue
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return out


IMAP_FOLDER_MAP = {
    "all": ["INBOX", "Junk"],
    "inbox": ["INBOX"],
    "junk": ["Junk"],
    "junkemail": ["Junk"],
    "inbox_junk": ["INBOX", "Junk"],
    "sent": ["Sent"],
}


async def fetch_via_imap(
    login_email: str,
    access_token: str,
    *,
    folder: str = "all",
    top: int = 20,
) -> List[Dict[str, Any]]:
    folders = IMAP_FOLDER_MAP.get((folder or "all").lower(), ["INBOX", "Junk"])
    top = min(max(int(top), 1), 100)
    return await asyncio.to_thread(
        _imap_fetch_blocking, login_email, access_token, folders, top
    )


# ---------------------------------------------------------------------------
# 高层入口：自动选择通道
# ---------------------------------------------------------------------------

async def fetch_messages(
    cred: Credential,
    *,
    folder: str = "all",
    top: int = 20,
    timeout: float = DEFAULT_TIMEOUT,
) -> Tuple[List[Dict[str, Any]], str]:
    """返回 (messages, channel)，channel 为 'graph' 或 'imap'。"""
    token_info = await refresh_access_token(
        cred.client_id, cred.refresh_token, timeout=timeout
    )
    access_token = token_info["access_token"]
    kind = token_info["token_type"]

    if kind == "graph":
        try:
            msgs = await fetch_via_graph(access_token, folder=folder, top=top, timeout=timeout)
            return msgs, "graph"
        except Exception:
            # Graph 失败时再尝试 IMAP（部分账号 Graph 权限被吊销但 IMAP 仍可用）
            pass

    # IMAP 通道：如果当前 token 不是 IMAP scope，则单独再要一次 IMAP scope token
    if kind != "imap":
        async with httpx.AsyncClient(timeout=timeout) as cli:
            r = await cli.post(
                MS_TOKEN_URL,
                data={
                    "client_id": cred.client_id,
                    "grant_type": "refresh_token",
                    "refresh_token": cred.refresh_token,
                    "scope": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            d = r.json() if r.content else {}
            if r.status_code == 200 and d.get("access_token"):
                access_token = d["access_token"]
            else:
                raise RuntimeError(f"获取 IMAP token 失败: {d}")

    msgs = await fetch_via_imap(cred.login_email, access_token, folder=folder, top=top)
    return msgs, "imap"

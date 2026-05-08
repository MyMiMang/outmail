"""FastAPI 入口：无状态纯转发。

环境变量：
- ACCESS_PASSWORD : 可选共享密码。若设置，则所有 /api/* 必须带 X-Access-Password 头。
- ALLOWED_ORIGINS : 逗号分隔的 CORS 允许来源，默认 *。
- BIND_HOST       : 监听地址，默认 0.0.0.0。
- BIND_PORT       : 监听端口，默认 8765。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .code_extract import extract_code
from .ms_mail import (
    Credential,
    fetch_messages,
    parse_bundle,
    refresh_access_token,
)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("webmail")

ACCESS_PASSWORD = os.environ.get("ACCESS_PASSWORD", "").strip()
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Outlook WebMail Fetcher", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 鉴权（可选共享密码）
# ---------------------------------------------------------------------------

async def require_access(
    x_access_password: Optional[str] = Header(default=None, alias="X-Access-Password"),
) -> None:
    if not ACCESS_PASSWORD:
        return
    if (x_access_password or "").strip() != ACCESS_PASSWORD:
        raise HTTPException(status_code=401, detail="invalid access password")


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

class CredIn(BaseModel):
    email: str = Field(..., description="登录邮箱（裂变别名时仍填主邮箱用于 IMAP 登录）")
    client_id: str
    refresh_token: str
    password: str = ""
    master_email: str = ""
    alias: str = Field(
        default="",
        description="裂变别名收件目标地址；若填写则只返回 toRecipients 命中此地址的邮件",
    )


class FetchIn(CredIn):
    folder: str = "all"  # all | inbox | junk | inbox_junk
    top: int = 20
    sender_contains: str = ""
    subject_contains: str = ""


class CodeIn(FetchIn):
    only_latest: bool = True


class BatchCodeIn(BaseModel):
    mailboxes: List[CredIn]
    folder: str = "all"
    top: int = 10
    sender_contains: str = ""
    subject_contains: str = ""


class BundleParseIn(BaseModel):
    text: str


# ---------------------------------------------------------------------------
# 过滤工具
# ---------------------------------------------------------------------------

def _match(msg: Dict[str, Any], *, alias: str, sender: str, subject: str) -> bool:
    if alias:
        a = alias.strip().lower()
        recipients = [r for r in (msg.get("to") or []) if r]
        if not any(a in r for r in recipients):
            return False
    if sender:
        if sender.strip().lower() not in (msg.get("from", "") or "").lower():
            return False
    if subject:
        if subject.strip().lower() not in (msg.get("subject", "") or "").lower():
            return False
    return True


def _to_credential(c: CredIn) -> Credential:
    return Credential(
        email=c.email.strip(),
        password=c.password,
        client_id=c.client_id.strip(),
        refresh_token=c.refresh_token.strip(),
        master_email=(c.master_email or c.email).strip(),
    )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "auth_required": bool(ACCESS_PASSWORD)}


@app.post("/api/parse_bundle", dependencies=[Depends(require_access)])
async def api_parse_bundle(payload: BundleParseIn) -> Dict[str, Any]:
    """把多行 email----password----client_id----refresh_token 文本解析为结构化列表。"""
    items: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for idx, raw in enumerate((payload.text or "").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            cred = parse_bundle(line)
            items.append(
                {
                    "email": cred.email,
                    "password": cred.password,
                    "client_id": cred.client_id,
                    "refresh_token": cred.refresh_token,
                    "master_email": cred.master_email,
                }
            )
        except Exception as e:
            errors.append({"line": idx, "error": str(e), "raw": line[:120]})
    return {"items": items, "errors": errors, "count": len(items)}


@app.post("/api/refresh", dependencies=[Depends(require_access)])
async def api_refresh(payload: CredIn) -> Dict[str, Any]:
    try:
        info = await refresh_access_token(
            payload.client_id.strip(), payload.refresh_token.strip()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 不回传 access_token 全量给前端没必要——但前端可能需要展示，这里返回类型与作用域
    return {
        "token_type": info["token_type"],
        "scope": info["scope"],
        "expires_in": info["expires_in"],
        "access_token_preview": info["access_token"][:24] + "..." if info["access_token"] else "",
    }


@app.post("/api/messages", dependencies=[Depends(require_access)])
async def api_messages(payload: FetchIn) -> Dict[str, Any]:
    cred = _to_credential(payload)
    try:
        msgs, channel = await fetch_messages(
            cred, folder=payload.folder, top=payload.top
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    filtered = [
        m for m in msgs
        if _match(
            m,
            alias=payload.alias or "",
            sender=payload.sender_contains,
            subject=payload.subject_contains,
        )
    ]
    return {"channel": channel, "count": len(filtered), "messages": filtered}


@app.post("/api/code", dependencies=[Depends(require_access)])
async def api_code(payload: CodeIn) -> Dict[str, Any]:
    cred = _to_credential(payload)
    try:
        msgs, channel = await fetch_messages(
            cred, folder=payload.folder, top=payload.top
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    msgs = [
        m for m in msgs
        if _match(
            m,
            alias=payload.alias or "",
            sender=payload.sender_contains,
            subject=payload.subject_contains,
        )
    ]
    msgs.sort(key=lambda m: m.get("date") or "", reverse=True)
    target_msgs = msgs[:1] if payload.only_latest else msgs

    code: Optional[str] = None
    hit_msg: Optional[Dict[str, Any]] = None
    for m in target_msgs:
        c = extract_code(
            f"{m.get('subject','')}\n{m.get('preview','')}\n{m.get('body_text','')}",
            subject=m.get("subject", ""),
        )
        if c:
            code = c
            hit_msg = m
            break

    return {
        "channel": channel,
        "code": code,
        "matched_subject": hit_msg.get("subject") if hit_msg else None,
        "matched_from": hit_msg.get("from") if hit_msg else None,
        "matched_date": hit_msg.get("date") if hit_msg else None,
        "scanned": len(target_msgs),
    }


@app.post("/api/batch_code", dependencies=[Depends(require_access)])
async def api_batch_code(payload: BatchCodeIn, request: Request) -> Dict[str, Any]:
    sem = asyncio.Semaphore(8)  # 限制并发，避免触发限流

    async def _one(c: CredIn) -> Dict[str, Any]:
        async with sem:
            cred = _to_credential(c)
            try:
                msgs, channel = await fetch_messages(
                    cred, folder=payload.folder, top=payload.top
                )
                msgs = [
                    m for m in msgs
                    if _match(
                        m,
                        alias=c.alias or "",
                        sender=payload.sender_contains,
                        subject=payload.subject_contains,
                    )
                ]
                msgs.sort(key=lambda m: m.get("date") or "", reverse=True)
                code = None
                subj = None
                for m in msgs[:5]:
                    code = extract_code(
                        f"{m.get('subject','')}\n{m.get('preview','')}\n{m.get('body_text','')}",
                        subject=m.get("subject", ""),
                    )
                    if code:
                        subj = m.get("subject")
                        break
                return {
                    "email": c.email,
                    "alias": c.alias or "",
                    "ok": True,
                    "code": code,
                    "channel": channel,
                    "matched_subject": subj,
                    "scanned": len(msgs),
                }
            except Exception as e:
                return {"email": c.email, "alias": c.alias or "", "ok": False, "error": str(e)}

    results = await asyncio.gather(*[_one(c) for c in payload.mailboxes])
    return {"count": len(results), "results": results}


# ---------------------------------------------------------------------------
# 静态资源
# ---------------------------------------------------------------------------

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.exception_handler(Exception)
async def _all_exc(request: Request, exc: Exception):
    log.exception("unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})

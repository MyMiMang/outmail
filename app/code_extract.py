"""验证码提取：兼容多种验证码邮件常见话术。"""
from __future__ import annotations

import re
from typing import Optional

# 常见模式（中英文）。从最具体到最宽松依次尝试。
_PATTERNS = [
    r"(?is)verification code below[^0-9]{0,80}(\d{4,8})",
    r"(?is)use the verification code[^0-9]{0,80}(\d{4,8})",
    r"(?is)code below[^0-9]{0,40}(\d{4,8})",
    r"(?is)login verification code[^0-9]{0,40}(\d{4,8})",
    r"(?is)your\s+\w[\w\s\.]{0,40}\s+(?:login\s+)?verification code[^0-9]{0,80}(\d{4,8})",
    r"(?is)verification code[^0-9]{0,40}(\d{4,8})",
    r"(?is)security code[^0-9]{0,40}(\d{4,8})",
    r"(?is)one[-\s]?time (?:password|code|passcode)[^0-9]{0,40}(\d{4,8})",
    r"(?is)otp[^0-9]{0,40}(\d{4,8})",
    r"(?is)access code[^0-9]{0,40}(\d{4,8})",
    r"(?is)\bcode\b[^0-9]{0,40}(\d{4,8})",
    r"(?is)验证码[^0-9]{0,40}(\d{4,8})",
    r"(?is)校验码[^0-9]{0,40}(\d{4,8})",
    r"(?is)动态码[^0-9]{0,40}(\d{4,8})",
]


def extract_code(text: str, subject: str = "") -> Optional[str]:
    """从主题 + 正文中尽力提取一个验证码（4-8 位数字）。"""
    subject = subject or ""
    text = text or ""
    # 主题里直接出现 6 位数字优先（最常见）
    m = re.search(r"\b(\d{6})\b", subject)
    if m:
        return m.group(1)
    merged = f"{subject}\n{text}"
    for pat in _PATTERNS:
        m = re.search(pat, merged)
        if m:
            return m.group(1)
    # 兜底：找一个独立 6 位数字
    m = re.search(r"(?<!\d)(\d{6})(?!\d)", merged)
    if m:
        return m.group(1)
    return None

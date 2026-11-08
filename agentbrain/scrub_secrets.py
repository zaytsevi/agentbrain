"""
ScrubSecrets: Automated Credential and Token Sanitizer
======================================================
Sanitizes strings before they are persisted into memory stores, event logs,
or markdown digests, preventing accidental credential leakage.
"""

import re
from typing import Tuple, List

SECRET_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b")),
    ("OPENAI_API_KEY", re.compile(r"\bsk-[A-Za-z0-9-_]{32,}\b")),
    ("ANTHROPIC_API_KEY", re.compile(r"\bsk-ant-[A-Za-z0-9-_]{32,}\b")),
    ("GITHUB_PAT", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b")),
    ("GITHUB_FINE_GRAINED", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b")),
    ("BEARER_TOKEN", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*\b")),
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("AWS_KEY", re.compile(r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("ENV_SECRET", re.compile(r"(?i)\b([A-Za-z0-9_]*(?:password|secret|api_key|token|auth_key|passwd|credential)[A-Za-z0-9_]*)\s*[:=]\s*['\"]([^'\"\s]{4,})['\"]")),
]

def scrub_text(text: str) -> Tuple[str, int]:
    if not text or not isinstance(text, str):
        return text, 0
    
    total_redacted = 0
    sanitized = text

    for name, pattern in SECRET_PATTERNS:
        if name == "ENV_SECRET":
            def env_replace(match):
                nonlocal total_redacted
                total_redacted += 1
                key_name = match.group(1)
                return f'{key_name}="[REDACTED:{name}]"'
            sanitized = pattern.sub(env_replace, sanitized)
        else:
            matches = list(pattern.finditer(sanitized))
            if matches:
                total_redacted += len(matches)
                sanitized = pattern.sub(f"[REDACTED:{name}]", sanitized)

    return sanitized, total_redacted

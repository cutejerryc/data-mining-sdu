"""Adapter that lets HALLMARK's LLM baselines talk to the OpenCode Go gateway.

Why this exists
---------------
HALLMARK's LLM baselines were published against OpenAI / Anthropic / OpenRouter.
The reproduction in this project runs against a different, OpenAI-compatible
gateway (``https://opencode.ai/zen/go/v1``), because the OpenAI and Anthropic
endpoints are not reachable from the machine used here.  That makes every LLM
number in this project an **adaptation** rather than a reproduction of the
published figure, and the write-up says so explicitly.

Two mechanical differences have to be handled:

1. The gateway wants an ``x-opencode-session`` header on every request.  The
   upstream code constructs ``openai.OpenAI(...)`` itself and does not expose a
   ``default_headers`` argument, so we wrap the class and inject the header for
   every client built after ``patch_openai_sdk()`` runs.
2. The gateway's reasoning models spend completion tokens on a hidden
   ``reasoning_content`` field, so ``max_tokens`` must be generous or the
   visible answer is truncated to an empty string with ``finish_reason=length``.

Credentials are read from the environment so that nothing is hard-coded:
``OPENCODE_API_KEY`` (required) and ``OPENCODE_BASE_URL`` (optional).
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"

#: Models that were verified to answer the verification prompt on this gateway.
KNOWN_MODELS = [
    "deepseek-v4.1-flash",
    "glm-5.3-flash",
    "kimi-k3",
    "deepseek-v4-pro",
]

#: A stable session id keeps gateway-side routing/caching consistent across the
#: whole experiment; the header is a routing hint, not an authentication token.
SESSION_ID = os.environ.get("OPENCODE_SESSION_ID", "hallmark-repro-2026")


@dataclass
class LLMConfig:
    base_url: str = field(default_factory=lambda: os.environ.get("OPENCODE_BASE_URL", DEFAULT_BASE_URL))
    api_key: str | None = field(default_factory=lambda: os.environ.get("OPENCODE_API_KEY"))
    model: str = field(default_factory=lambda: os.environ.get("OPENCODE_MODEL", "deepseek-v4.1-flash"))
    session_id: str = SESSION_ID

    def require(self) -> "LLMConfig":
        if not self.api_key:
            raise RuntimeError(
                "OPENCODE_API_KEY is not set. Export it before running any LLM baseline, e.g.\n"
                "  export OPENCODE_API_KEY=oc_sk_...\n"
                "Deterministic baselines (exp1/exp2 stage 1) do not need it."
            )
        return self

    @property
    def slug(self) -> str:
        """Filesystem-safe identifier used in prediction/metric filenames."""
        return self.model.replace("/", "_").replace(".", "")


def patch_openai_sdk(session_id: str | None = None) -> None:
    """Make every ``openai.OpenAI`` client send the gateway session header.

    Idempotent: patching twice would double-wrap the class, so the original is
    stashed on the class object and reused.
    """
    import openai

    if getattr(openai.OpenAI, "_hallmark_patched", False):
        return

    original = openai.OpenAI
    sid = session_id or SESSION_ID

    class _PatchedOpenAI(original):                     # type: ignore[misc,valid-type]
        _hallmark_patched = True

        def __init__(self, *args, **kwargs):
            headers = dict(kwargs.pop("default_headers", None) or {})
            headers.setdefault("x-opencode-session", sid)
            kwargs["default_headers"] = headers
            super().__init__(*args, **kwargs)

    openai.OpenAI = _PatchedOpenAI                     # type: ignore[assignment]


def configure_environment(cfg: LLMConfig | None = None) -> LLMConfig:
    """Export credentials under the names HALLMARK's registry looks for.

    The registry auto-injects ``OPENAI_API_KEY`` into baselines that declare it,
    so pointing that variable at the gateway key is what makes the upstream
    runners work unmodified.
    """
    cfg = (cfg or LLMConfig()).require()
    os.environ["OPENAI_API_KEY"] = cfg.api_key or ""
    os.environ["OPENAI_BASE_URL"] = cfg.base_url
    os.environ["OPENCODE_MODEL"] = cfg.model
    patch_openai_sdk(cfg.session_id)
    return cfg


def smoke_test(cfg: LLMConfig | None = None, max_tokens: int = 64) -> dict:
    """One round-trip that proves the credentials and the header work."""
    cfg = (cfg or LLMConfig()).require()
    patch_openai_sdk(cfg.session_id)
    import openai

    client = openai.OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
    resp = client.chat.completions.create(
        model=cfg.model,
        messages=[{"role": "user", "content": 'Reply with only this JSON: {"ok":true}'}],
        max_tokens=max_tokens,
        temperature=0.0,
    )
    return {
        "model": cfg.model,
        "base_url": cfg.base_url,
        "content": resp.choices[0].message.content,
        "finish_reason": resp.choices[0].finish_reason,
        "usage": resp.usage.model_dump() if resp.usage else None,
        "session": cfg.session_id,
    }


if __name__ == "__main__":                              # pragma: no cover
    import json

    print(json.dumps(smoke_test(), indent=2, ensure_ascii=False))

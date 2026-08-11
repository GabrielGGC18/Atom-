"""HTTP simples (stdlib) para consultar APIs e paginas."""

from __future__ import annotations

import json as _json
import re
import urllib.error
import urllib.request

from atom.core.registry import register

UA = "ATOM/0.1 (+local agent)"
MAX_BODY = 20_000


def _strip_html(html: str) -> str:
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html,
                  flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


@register("http_get", "GET em URL. text=True limpa HTML e devolve so texto.",
          {"url": "str", "text": "bool (opcional)"})
def http_get(url: str, text: bool = True) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="replace")
            ctype = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return f"ERRO HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        return f"ERRO: {exc}"
    if text and "html" in ctype:
        body = _strip_html(body)
    return body[:MAX_BODY]


@register("http_post", "POST JSON em URL.",
          {"url": "str", "json": "dict", "headers": "dict (opcional)"}, dangerous=True)
def http_post(url: str, json: dict | None = None, headers: dict | None = None) -> str:
    data = _json.dumps(json or {}).encode("utf-8")
    hdrs = {"User-Agent": UA, "Content-Type": "application/json"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")[:MAX_BODY]
    except urllib.error.HTTPError as exc:
        return f"ERRO HTTP {exc.code}: {exc.read()[:500]!r}"
    except Exception as exc:
        return f"ERRO: {exc}"

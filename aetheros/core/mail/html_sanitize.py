"""Allowlist HTML sanitiser for mail bodies.

The output is inert markup: no scripts, no style, no event handlers, no
active URL schemes. Remote images are replaced by a fixed inline placeholder
unless the caller explicitly enables them.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

ALLOWED_TAGS = frozenset({
    "a", "b", "i", "u", "strong", "em", "small", "p", "br", "div", "span",
    "ul", "ol", "li", "blockquote", "pre", "code", "hr", "table", "thead",
    "tbody", "tfoot", "tr", "th", "td", "h1", "h2", "h3", "h4", "h5", "h6",
    "img",
})
DROP_WITH_CONTENT = frozenset({
    "script", "style", "iframe", "object", "embed", "noscript", "template",
    "svg", "math", "form", "button", "input", "select", "textarea", "video", "audio",
})
VOID_TAGS = frozenset({"br", "hr", "img"})
ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "title"}),
    "img": frozenset({"src", "alt", "width", "height"}),
}
MAX_INPUT_CHARS = 4 * 1024 * 1024
MAX_OUTPUT_CHARS = 8 * 1024 * 1024
PLACEHOLDER_SRC = "data:image/gif;base64,R0lGODlhAQABAAAAACw="
PLACEHOLDER_ALT = "[remote image blocked]"
_SCHEME_RE = re.compile(r"^([a-z][a-z0-9+.-]*):")


def _sanitize_url(value: str | None, *, image: bool) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or any(ord(ch) < 0x20 for ch in value):
        return None
    low = value.lower()
    if low.startswith(("javascript:", "data:", "vbscript:", "file:", "blob:", "//")):
        return None
    match = _SCHEME_RE.match(low)
    if match:
        allowed = {"http", "https"} if image else {"http", "https", "mailto"}
        if match.group(1) not in allowed:
            return None
    return value


class _AllowlistParser(HTMLParser):
    def __init__(self, allow_remote_images: bool):
        super().__init__(convert_charrefs=True)
        self.allow_remote_images = allow_remote_images
        self.parts: list[str] = []
        self.length = 0
        self.drop_depth = 0
        self.open_tags: list[str] = []

    def _emit(self, chunk: str) -> None:
        room = MAX_OUTPUT_CHARS - self.length
        if room <= 0:
            return
        if len(chunk) > room:
            chunk = chunk[:room]
        self.parts.append(chunk)
        self.length += len(chunk)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            self.drop_depth += 1
            return
        if self.drop_depth or tag not in ALLOWED_TAGS:
            return

        rendered: list[str] = []
        for key, raw in attrs:
            key = key.lower()
            if key.startswith("on") or key not in ALLOWED_ATTRS.get(tag, frozenset()):
                continue
            if key in ("href", "src"):
                safe = _sanitize_url(raw, image=(key == "src"))
                if safe is None:
                    continue
                if key == "src" and not self.allow_remote_images:
                    rendered.append(' src="' + PLACEHOLDER_SRC + '"')
                    rendered.append(' data-aether-blocked="1"')
                    rendered.append(' alt="' + html.escape(PLACEHOLDER_ALT, quote=True) + '"')
                    continue
                rendered.append(f' {key}="{html.escape(safe, quote=True)}"')
            elif key == "alt":
                rendered.append(f' alt="{html.escape((raw or "")[:512], quote=True)}"')
            elif key in ("width", "height", "title"):
                value = raw or ""
                if len(value) <= 64 and not any(ord(ch) < 0x20 for ch in value):
                    rendered.append(f' {key}="{html.escape(value, quote=True)}"')
        self._emit("<" + tag + "".join(rendered) + ">")
        if tag not in VOID_TAGS:
            self.open_tags.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            if self.drop_depth:
                self.drop_depth -= 1
            return
        if self.drop_depth or tag in VOID_TAGS:
            return
        while tag in self.open_tags:
            opened = self.open_tags.pop()
            self._emit(f"</{opened}>")
            if opened == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self.drop_depth:
            self._emit(html.escape(data, quote=False))


def sanitize(html_text: str, allow_remote_images: bool = True) -> str:
    """Return an inert allowlisted rendering of ``html_text``."""
    if not isinstance(html_text, str):
        raise TypeError("html_text must be a string")
    if len(html_text) > MAX_INPUT_CHARS:
        html_text = html_text[:MAX_INPUT_CHARS] + "..."
    parser = _AllowlistParser(bool(allow_remote_images))
    try:
        parser.feed(html_text)
        parser.close()
    except Exception:
        return ""
    return "".join(parser.parts)

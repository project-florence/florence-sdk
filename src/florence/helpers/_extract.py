"""HTML metin cikarimi: trafilatura (opsiyonel) + stdlib ``html.parser`` fallback.

Tasarim (helpers-design.md Bolum 3.2): trafilatura ``florence-sdk[news]``
extra'si ile gelir; kurulu degilse stdlib fallback calisir — davranis
bozulmaz, yalnizca cikarim kalitesi duser. ``extract_html`` her iki yolu da
dener; trafilatura hata verirse fallback'e dusulur.
"""

from __future__ import annotations

from html.parser import HTMLParser

__all__ = ["TRAFILATURA_AVAILABLE", "clean_text", "extract_html"]

try:  # opsiyonel bagimlilik: pip install florence-sdk[news]
    import trafilatura  # type: ignore[import-untyped]

    TRAFILATURA_AVAILABLE = True
except ImportError:  # pragma: no cover — opsiyonel extra yokken
    trafilatura = None  # type: ignore[assignment]
    TRAFILATURA_AVAILABLE = False

#: Fallback toplayicinin metin etiketleri (h1-h6/p/li/blockquote — tasarim 3.2).
_TEXT_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote"})

#: Icerigi atlanacak etiketler (reklam/nav/script temizligi, fallback duzeyi).
# ``head`` bilincli olarak DISARIDA: ``<title>`` oradan toplanir.
_SKIP_TAGS = frozenset({"script", "style", "noscript", "iframe", "svg", "template", "nav", "footer"})


class _FallbackExtractor(HTMLParser):
    """Basit metin toplayici: ``<h1..h6>``/``<p>``/``<li>``/``<blockquote>`` + ``<title>``."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._text_tags = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in _TEXT_TAGS:
            self._text_tags += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in _TEXT_TAGS:
            self._text_tags = max(0, self._text_tags - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            if self.title is None:
                self.title = text
            return
        if self._text_tags:
            self.parts.append(text)


def _extract_fallback(html: str) -> tuple[str | None, str]:
    parser = _FallbackExtractor()
    parser.feed(html or "")
    return parser.title, clean_text("\n".join(parser.parts))


def _extract_trafilatura(html: str) -> tuple[str | None, str]:
    assert trafilatura is not None
    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    title: str | None = None
    try:
        meta = trafilatura.extract_metadata(html)
        if meta and meta.get("title"):
            title = str(meta["title"])
    except Exception:  # noqa: BLE001 — metadata hatasi metni dusurmez
        title = None
    return title, clean_text(text or "")


def extract_html(html: str) -> tuple[str | None, str]:
    """Sayfadan ``(title, text)`` cikarir; trafilatura yoksa stdlib fallback."""
    if TRAFILATURA_AVAILABLE:
        try:
            return _extract_trafilatura(html)
        except Exception:  # noqa: BLE001 — trafilatura hatasinda fallback guvencesi
            return _extract_fallback(html)
    return _extract_fallback(html)


def clean_text(text: str) -> str:
    """Bosluklari sikistirir ve bos satirlari atar (duz metin normalizasyonu)."""
    lines = [" ".join(line.split()) for line in (text or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()

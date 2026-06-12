#!/usr/bin/env python3
"""
Post-processor: enrich search_index.json with extracted headings and
extended excerpts. Run after any source rebuild.

For every entry in the index, find the matching processed .json page,
extract all H1–H4 heading text, and write it back as a 'headings' field.
Also bumps excerpts to 500 chars.
"""
import json, re
from pathlib import Path

ROOT      = Path(__file__).parent.parent
INDEX     = ROOT / "static" / "search_index.json"
PROCESSED = ROOT / "content" / "processed"

_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE  = re.compile(r'\s+')
_HEAD_RE = re.compile(r'<h[1-4][^>]*>(.*?)</h[1-4]>', re.I | re.S)
_INNER_RE = re.compile(r'<[^>]+>')


def _strip(html: str) -> str:
    return _WS_RE.sub(' ', _TAG_RE.sub(' ', html)).strip()


def _headings(html: str) -> str:
    """Return all H1–H4 text joined by space, HTML-stripped."""
    heads = []
    for m in _HEAD_RE.finditer(html):
        text = _INNER_RE.sub('', m.group(1)).strip()
        if text:
            heads.append(text)
    return ' | '.join(heads)


def _build_page_map() -> dict:
    """Map path → processed JSON file."""
    page_map = {}
    for f in PROCESSED.rglob('*.json'):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        path = data.get('path', '')
        if path:
            page_map[path] = data
    return page_map


def enhance():
    idx = json.loads(INDEX.read_text(encoding='utf-8'))
    page_map = _build_page_map()

    updated = 0
    for entry in idx:
        path = entry.get('path', '')
        page = page_map.get(path)
        if not page:
            continue
        html = page.get('html', '')
        if not html:
            continue

        # Bump excerpt to 500 chars
        plain = _strip(html)
        entry['excerpt'] = plain[:500]

        # Add headings
        heads = _headings(html)
        if heads:
            entry['headings'] = heads
            updated += 1

    INDEX.write_text(json.dumps(idx, ensure_ascii=False), encoding='utf-8')
    print(f"Enhanced {updated}/{len(idx)} entries with headings.")
    print(f"Total index entries: {len(idx)}")


if __name__ == '__main__':
    enhance()

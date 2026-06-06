#!/usr/bin/env python3
"""
Convert HTB Obsidian cheat sheets → p3ta-tricks processed JSON.

Handles two formats:
  1. Academy Cheat Sheets — markdown tables (Command | Description)
     → h3(description) + code block per row
  2. Reference notes    — already have fenced ```code``` blocks
     → rendered as standard markdown HTML

Hardcoded lab values (IPs, domains, passwords) are replaced with
<placeholder> variables that p3ta-tricks can substitute.

Usage:
    python3 scripts/import_htb_obsidian.py
"""
import re, json, html, sys
from pathlib import Path

ROOT        = Path(__file__).parent.parent
OUT_DIR     = ROOT / "content" / "processed" / "cheatsheet"
NAV_DIR     = ROOT / "content" / "nav"
SOURCE_ID   = "cheatsheet"
SOURCE_LABEL = "Cheat Sheets"

VAULT_CHEATSHEETS = Path("/home/p3ta/Documents/uWu/HTB/HTB Academy Cheat Sheets")
VAULT_REFERENCE   = Path("/home/p3ta/Documents/uWu/HTB/Reference")

OUT_DIR.mkdir(parents=True, exist_ok=True)
NAV_DIR.mkdir(parents=True, exist_ok=True)

# ── Variable substitutions (most specific first) ──────────────────────────────
VAR_SUBS = [
    # Subnets
    (r'\b172\.16\.\d+\.\d+/\d+\b',          '<subnet>'),
    (r'\b10\.129\.\d+\.\d+/\d+\b',          '<subnet>'),
    # DC / specific lab IPs
    (r'\b172\.16\.5\.5\b',                   '<dc-ip>'),
    (r'\b172\.16\.5\.\d+\b',                 '<target-ip>'),
    (r'\b10\.129\.\d+\.\d+\b',              '<target-ip>'),
    (r'\b192\.168\.\d+\.\d+\b',             '<target-ip>'),
    # Domains (case-sensitive variants)
    (r'\bINLANEFREIGHT\.LOCAL\b',            '<DOMAIN>'),
    (r'\binlanefreight\.local\b',            '<domain>'),
    (r'\bINLANEFREIGHT\b',                  '<domain-name>'),
    (r'\binlanefreight\b',                   '<domain-name>'),
    (r'\bhtb\.local\b',                      '<domain>'),
    (r'\bHTB\.LOCAL\b',                      '<DOMAIN>'),
    (r'\bfreelancer\.htb\b',                 '<domain>'),
    # Passwords (common lab passwords)
    (r'\bKlmcargo2\b',                       '<password>'),
    (r'\bPassword123!?\b',                   '<password>'),
    (r'\bWelcome1!?\b',                       '<password>'),
    (r'\bInlanefreight01!\b',                '<password>'),
    (r'\bHunting_s3cr3ts\b',                 '<password>'),
    (r'\bProofpoint@2022\b',                 '<password>'),
    (r'\bAcademy_sspr_test1!\b',             '<password>'),
    # Usernames (common lab accounts — don't replace 'administrator' alone,
    # it's too generic and often illustrative)
    (r'\bforend\b',                           '<username>'),
    (r'\bavazquez\b',                         '<username>'),
    (r'\bdamundsen\b',                        '<username>'),
    (r'\btpetty\b',                           '<username>'),
    (r'\bsvc-sql\b',                          '<username>'),
    (r'\bbwilliamson\b',                      '<username>'),
    (r'\bjsmith\b',                           '<username>'),
    # Hostnames (keep generic ones as examples, replace specific lab hostnames)
    (r'\bACADEMY-EA-MS01\b',                 '<hostname>'),
    (r'\bACADEMY-EA-DC01\b',                 '<dc-hostname>'),
    (r'\bACADEMY-EA-CA01\b',                 '<ca-hostname>'),
    (r'\bMS01\b',                             '<hostname>'),
    (r'\bDC01\b',                             '<dc-hostname>'),
    (r'\bWS01\b',                             '<hostname>'),
]


def _apply_vars(text: str) -> str:
    for pat, repl in VAR_SUBS:
        text = re.sub(pat, repl, text)
    return text


def _slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'\s+', '-', s.strip())
    return re.sub(r'-+', '-', s)[:80]


def _detect_lang(cmd: str) -> str:
    cmd = cmd.strip()
    if cmd.startswith(('PS ', 'PS>', 'powershell', 'Import-Module', 'Get-', 'Set-',
                        'Invoke-', 'New-', 'Remove-', '$', 'IEX', 'Add-')):
        return 'powershell'
    if re.match(r'^reg\b|^sc\b|^net\b|^icacls\b|^runas\b|^certutil\b|^wmic\b', cmd, re.I):
        return 'batch'
    if re.match(r'^msfconsole|^use |^set |^exploit|^run |msf\d?>', cmd):
        return 'bash'
    return 'bash'


def _code_block(cmd: str) -> str:
    cmd = _apply_vars(cmd)
    lang = _detect_lang(cmd)
    escaped = html.escape(cmd)
    return f'<pre><code class="language-{lang}">{escaped}</code></pre>'


def _excerpt(html_str: str, n: int = 200) -> str:
    text = re.sub(r'<[^>]+>', ' ', html_str)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:n] + ('…' if len(text) > n else '')


# ── Academy Cheat Sheet parser (table format) ──────────────────────────────────

def _strip_markdown(text: str) -> str:
    """Remove markdown formatting (bold, italic, links)."""
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # strip links
    text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)  # strip bold/italic
    text = re.sub(r'`([^`]+)`', r'\1', text)               # strip inline code
    return text.strip()


def _is_header_row(parts: list) -> bool:
    """Detect header rows: all cells are short title-case labels (may be backtick-wrapped)."""
    for cell in parts:
        if not cell.strip():
            continue
        # Strip all markdown formatting for the content check
        clean = _strip_markdown(cell)
        if len(clean) > 40:
            return False
        if not re.match(r'^[A-Z][a-zA-Z0-9\s\-/():?]+$', clean):
            return False
    return True


def _parse_table_rows(table_text: str) -> list:
    """Extract (command, description) pairs from a markdown table."""
    raw_rows = []

    for line in table_text.splitlines():
        line = line.strip()
        if not line or re.match(r'^\|[-\s|:]+\|$', line):
            continue
        if not line.startswith('|'):
            continue
        # Replace escaped pipes \| before splitting so they don't split columns
        line_clean = line.replace('\\|', '\x00')
        parts = [p.strip().replace('\x00', '|') for p in line_clean.strip('|').split('|')]
        if len(parts) < 2:
            continue

        col0 = parts[0].strip()
        col1 = parts[1].strip() if len(parts) > 1 else ''
        col2 = parts[2].strip() if len(parts) > 2 else ''

        # Skip header rows
        if _is_header_row(parts[:3]):
            continue
        # Also skip the classic Command/Description header
        if re.match(r'^\*{0,2}[Cc]ommand[/\w]*\*{0,2}$', col0):
            continue

        if col0 or col1:
            raw_rows.append((col0, col1, col2))

    if not raw_rows:
        return []

    # Handle 3-column tables
    has_3_cols = any(row[2] for row in raw_rows)
    if has_3_cols:
        # Detect if col2 is reference URLs → col1 is the code/example, col0 is label
        col2_link_count = sum(1 for r in raw_rows if re.search(r'\[.+\]\(.+\)', r[2]))
        if col2_link_count > len(raw_rows) / 2:
            # col0 = label, col1 = code example, col2 = ref (drop)
            return [(r[1], r[0]) for r in raw_rows if r[0] or r[1]]
        else:
            # col0 = instruction name, col1 = description, col2 = example command
            return [(r[2], r[1]) for r in raw_rows if r[2] or r[1]]

    # 2-column: detect orientation by backtick frequency
    col0_bt = sum(1 for r in raw_rows if r[0].startswith('`') and r[0].endswith('`'))
    col1_bt = sum(1 for r in raw_rows if r[1].startswith('`') and r[1].endswith('`'))

    if col1_bt > col0_bt:
        # col1 has backtick commands, col0 has descriptions → swap
        return [(r[1], r[0]) for r in raw_rows if r[0] or r[1]]
    else:
        return [(r[0], r[1]) for r in raw_rows if r[0]]


def _looks_like_code(text: str) -> bool:
    """Heuristic: does text look like executable code vs natural language prose?"""
    if len(text) < 200:
        return True
    if '\n' in text:
        return True  # multi-line is always code
    if re.search(r'\b(SELECT|FROM|WHERE|JOIN|EXEC|INSERT|UPDATE|DELETE|RECONFIGURE|DECLARE)\b', text, re.I):
        return True
    if re.search(r'[/\\$@]|\b(python|python3|curl|wget|Get-|Set-|Invoke-|Add-|Remove-)\b', text):
        return True
    return False


def _render_rows(rows: list) -> str:
    """Render table rows as: description h3 + code block pairs."""
    if not rows:
        return ''
    out = []
    for cmd, desc in rows:
        cmd = cmd.strip()

        # Normalize all <br> variants to <br> before splitting
        cmd = re.sub(r'\s*<br\s*/?>\s*', '<br>', cmd, flags=re.I)

        # Reconstruct <br>-joined multi-line commands (Obsidian table line breaks)
        if '<br>' in cmd:
            segments = cmd.split('<br>')
            lines = []
            for seg in segments:
                seg = seg.strip()
                if seg.startswith('`') and seg.endswith('`') and seg.count('`') == 2:
                    seg = seg[1:-1]
                lines.append(seg)
            cmd = '\n'.join(lines)
        else:
            # Strip single surrounding backtick pair
            if cmd.startswith('`') and cmd.endswith('`') and cmd.count('`') == 2:
                cmd = cmd[1:-1]

        # Strip markdown links and bold/italic from cmd
        cmd = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', cmd)
        cmd = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', cmd)
        cmd = cmd.strip()
        if not cmd:
            continue

        # Clean description
        desc_clean = _strip_markdown(desc).strip() if desc else ''

        if len(desc_clean) > 120:
            # Reference table (e.g. Tools of the Trade): h3(cmd-label) + p(desc)
            slug = _slugify(cmd)[:60]
            out.append(f'<h3 id="{slug}">{html.escape(cmd)}</h3>')
            trunc = desc_clean[:400] + ('…' if len(desc_clean) > 400 else '')
            out.append(f'<p>{html.escape(trunc)}</p>')
        elif not _looks_like_code(cmd):
            # Long natural-language cmd (comparison table) → show as prose
            if desc_clean:
                slug = _slugify(desc_clean)[:60]
                out.append(f'<h3 id="{slug}">{html.escape(desc_clean)}</h3>')
            out.append(f'<p>{html.escape(cmd[:400])}{"…" if len(cmd) > 400 else ""}</p>')
        else:
            # Normal: h3 = description, code block = command
            if desc_clean:
                slug = _slugify(desc_clean)[:60]
                out.append(f'<h3 id="{slug}">{html.escape(desc_clean)}</h3>')
            out.append(_code_block(cmd))

    return '\n'.join(out)


def _process_body(body: str) -> str:
    """Process a section body: extract tables → rows format + fenced blocks."""
    chunks = []
    other_lines = []
    current_table = []
    in_fence = False

    for line in body.splitlines():
        # Track fenced block state so blank lines inside fences are preserved
        if line.strip().startswith('```'):
            in_fence = not in_fence

        if not in_fence and line.strip().startswith('|'):
            if other_lines:
                non_table = _convert_fenced_blocks('\n'.join(other_lines))
                if non_table:
                    chunks.append(non_table)
                other_lines = []
            current_table.append(line)
        else:
            if current_table:
                rows = _parse_table_rows('\n'.join(current_table))
                if rows:
                    chunks.append(_render_rows(rows))
                current_table = []
            # Preserve blank lines inside fenced blocks; drop outside
            if line.strip() or in_fence:
                other_lines.append(line)

    if current_table:
        rows = _parse_table_rows('\n'.join(current_table))
        if rows:
            chunks.append(_render_rows(rows))
    if other_lines:
        non_table = _convert_fenced_blocks('\n'.join(other_lines))
        if non_table:
            chunks.append(non_table)

    return '\n'.join(chunks)


def _split_on_h1(md_text: str) -> list:
    """Split markdown on H1 headings that are NOT inside fenced code blocks.
    Returns [preamble, title1, body1, title2, body2, ...]"""
    result = []
    current = []
    in_fence = False

    for line in md_text.splitlines(keepends=True):
        stripped = line.strip()
        # Track fenced code block state
        if stripped.startswith('```'):
            in_fence = not in_fence
        if not in_fence and re.match(r'^# (.+)$', stripped):
            result.append(''.join(current))
            result.append(re.match(r'^# (.+)$', stripped).group(1))
            current = []
        else:
            current.append(line)

    result.append(''.join(current))
    return result


def convert_academy_sheet(md_text: str, title: str) -> str:
    """Convert Academy cheat sheet (table format) to HTML."""
    md_text = re.sub(r'^---\n.*?\n---\n', '', md_text, flags=re.S)

    chunks = []
    sections = _split_on_h1(md_text)

    # Preamble before first H1 — may itself contain tables
    preamble = sections[0].strip()
    if preamble:
        chunks.append(_process_body(preamble))

    it = iter(sections[1:])
    for sec_title, sec_body in zip(it, it):
        sec_title = sec_title.strip()
        chunks.append(f'<h2>{html.escape(sec_title)}</h2>')
        chunks.append(_process_body(sec_body))

    return '\n'.join(chunks)


# ── Reference note parser (fenced code block format) ──────────────────────────

def _convert_fenced_blocks(md_text: str) -> str:
    """Convert markdown with fenced code blocks to HTML."""
    if not md_text.strip():
        return ''

    # Normalize inline triple-backtick spans (same line, no newline inside)
    # e.g. ```payload``` → `payload`  Must run before block split to avoid
    # the regex matching across lines on the closing/opening ``` boundary.
    md_text = re.sub(r'```([^`\n]+)```', r'`\1`', md_text)

    parts = []
    # Split on fenced code blocks
    segments = re.split(r'```(\w*)\n(.*?)```', md_text, flags=re.S)
    # segments: [text, lang, code, text, lang, code, ...]

    i = 0
    while i < len(segments):
        if i % 3 == 0:
            # Prose segment
            prose = segments[i].strip()
            if prose:
                parts.append(_prose_to_html(prose))
        elif i % 3 == 1:
            lang = segments[i].strip() or 'bash'
            code = segments[i + 1] if i + 1 < len(segments) else ''
            code = _apply_vars(code.rstrip())
            escaped = html.escape(code)
            parts.append(f'<pre><code class="language-{lang}">{escaped}</code></pre>')
            i += 1  # skip the code segment (consumed above)
        i += 1

    return '\n'.join(parts)


def _prose_to_html(text: str) -> str:
    """Convert plain prose to HTML paragraphs/headings/code blocks."""
    lines = [l.rstrip() for l in text.splitlines()]
    out = []
    para = []

    def flush_para():
        if para:
            joined = ' '.join(para).strip()
            if joined:
                joined = html.escape(joined)
                joined = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', joined)
                joined = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', joined)
                joined = re.sub(r'`([^`]+)`', r'<code>\1</code>', joined)
                joined = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', joined)
                out.append(f'<p>{joined}</p>')
            para.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Normalize triple-backtick inline spans to single-backtick
        # e.g. ```payload``` → `payload` (on a single line)
        stripped = re.sub(r'```([^`\n]+)```', r'`\1`', stripped)

        # Skip Obsidian "Code: lang" labels before fenced blocks
        if re.match(r'^Code:\s+\w+$', stripped):
            i += 1
            continue

        m4 = re.match(r'^#### (.+)$', stripped)
        m3 = re.match(r'^### (.+)$', stripped)
        m2 = re.match(r'^## (.+)$', stripped)
        m1 = re.match(r'^# (.+)$', stripped)

        if m1:
            flush_para()
            out.append(f'<h2>{html.escape(m1.group(1))}</h2>')
            i += 1
        elif m2:
            flush_para()
            out.append(f'<h3>{html.escape(m2.group(1))}</h3>')
            i += 1
        elif m3:
            flush_para()
            out.append(f'<h4>{html.escape(m3.group(1))}</h4>')
            i += 1
        elif m4:
            flush_para()
            out.append(f'<h4>{html.escape(m4.group(1))}</h4>')
            i += 1
        elif stripped == '' or stripped == '---' or re.match(r'^-{3,}$', stripped):
            flush_para()
            i += 1
        else:
            # Single backtick code span on its own line → code block
            m_code = re.match(r'^`([^`]+)`$', stripped)
            if m_code:
                flush_para()
                cmd = m_code.group(1)

                # Look ahead: is next non-blank line a short description?
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                next_stripped = lines[j].strip() if j < len(lines) else ''
                is_desc = bool(
                    next_stripped and
                    not re.match(r'^`[^`]+`$', next_stripped) and
                    not re.match(r'^#{1,4}\s', next_stripped) and
                    not next_stripped.startswith('|') and
                    not next_stripped.startswith('```') and
                    not re.match(r'^Code:\s+\w+$', next_stripped) and
                    not re.match(r'^-{3,}$', next_stripped)
                )

                cmd = _apply_vars(cmd)
                lang = _detect_lang(cmd)

                if is_desc:
                    # cmd + desc pair → h3(desc) + code(cmd)
                    desc_text = next_stripped
                    desc_text = re.sub(r'`([^`]+)`', r'\1', desc_text)
                    desc_text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', desc_text)
                    slug = _slugify(desc_text)[:60]
                    out.append(f'<h3 id="{slug}">{html.escape(desc_text)}</h3>')
                    out.append(f'<pre><code class="language-{lang}">{html.escape(cmd)}</code></pre>')
                    i = j + 1  # consume both lines
                else:
                    out.append(f'<pre><code class="language-{lang}">{html.escape(cmd)}</code></pre>')
                    i += 1
            else:
                para.append(stripped)
                i += 1

    flush_para()
    return '\n'.join(out)


def convert_reference_note(md_text: str, title: str) -> str:
    """Convert a reference note (code-block format) to HTML."""
    md_text = re.sub(r'^---\n.*?\n---\n', '', md_text, flags=re.S)
    # Top-level H1 becomes the page title, skip it
    md_text = re.sub(r'^# .+\n', '', md_text, count=1, flags=re.M)
    return _convert_fenced_blocks(md_text)


# ── File processors ────────────────────────────────────────────────────────────

def process_academy_sheets() -> list:
    """Process all Academy Cheat Sheet .md files."""
    nav_items = []
    for fpath in sorted(VAULT_CHEATSHEETS.glob('*.md')):
        if fpath.name.startswith('1. Rename') or fpath.name.startswith('HTB Academy to'):
            continue

        title = fpath.stem
        slug  = _slugify(title)
        out_name = f'{slug}.json'
        out_path  = OUT_DIR / out_name

        md_text = fpath.read_text(encoding='utf-8', errors='replace')
        body_html = convert_academy_sheet(md_text, title)

        if not body_html.strip():
            print(f'  SKIP (empty): {title}')
            continue

        full_html = f'<h1 id="{slug}">{html.escape(title)}</h1>\n{body_html}'

        data = {
            'title':        title,
            'source':       SOURCE_ID,
            'source_label': SOURCE_LABEL,
            'path':         f'{SOURCE_ID}/{slug}',
            'html':         full_html,
            'excerpt':      _excerpt(full_html),
            'tags':         ['htb', 'cheatsheet'],
        }
        out_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        print(f'  academy: {title}')

        nav_items.append({
            'type':  'link',
            'title': title,
            'url':   f'/page/{SOURCE_ID}/{slug}',
            'items': [],
        })

    return nav_items


def process_reference_notes() -> dict:
    """Process all Reference .md files (recursive)."""
    nav_sections: dict = {}

    for fpath in sorted(VAULT_REFERENCE.rglob('*.md')):
        if fpath.name.startswith('Reference Index'):
            continue

        # Section = immediate subdirectory of Reference
        rel = fpath.relative_to(VAULT_REFERENCE)
        parts = rel.parts
        section = parts[0] if len(parts) > 1 else 'General'

        title = fpath.stem
        slug  = _slugify(section + '-' + title)
        out_name = f'ref-{slug}.json'
        out_path  = OUT_DIR / out_name

        md_text = fpath.read_text(encoding='utf-8', errors='replace')
        # Detect format: if it has mostly tables, use academy converter, else reference
        table_lines = sum(1 for l in md_text.splitlines() if l.strip().startswith('|'))
        code_blocks = md_text.count('```')
        if table_lines > code_blocks * 3:
            body_html = convert_academy_sheet(md_text, title)
        else:
            body_html = convert_reference_note(md_text, title)

        if not body_html.strip():
            print(f'  SKIP (empty): {title}')
            continue

        full_html = f'<h1 id="{slug}">{html.escape(title)}</h1>\n{body_html}'

        data = {
            'title':        title,
            'source':       SOURCE_ID,
            'source_label': SOURCE_LABEL,
            'path':         f'{SOURCE_ID}/ref-{slug}',
            'html':         full_html,
            'excerpt':      _excerpt(full_html),
            'tags':         ['reference', section.lower().replace(' ', '-')],
        }
        out_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        print(f'  ref [{section}]: {title}')

        if section not in nav_sections:
            nav_sections[section] = []
        nav_sections[section].append({
            'type':  'link',
            'title': title,
            'url':   f'/page/{SOURCE_ID}/ref-{slug}',
            'items': [],
        })

    return nav_sections


def update_search_index(source_id: str) -> None:
    idx_path = ROOT / 'static' / 'search_index.json'
    idx = json.loads(idx_path.read_text(encoding='utf-8'))
    idx = [e for e in idx if e.get('source') != source_id]
    for fpath in sorted((OUT_DIR).glob('*.json')):
        d = json.loads(fpath.read_text())
        text = re.sub(r'<[^>]+>', ' ', d.get('html', ''))
        text = re.sub(r'\s+', ' ', text).strip()
        idx.append({
            'title':        d['title'],
            'source':       d['source'],
            'source_label': d['source_label'],
            'path':         d['path'],
            'url':          f"/page/{d['source']}/{fpath.stem}",
            'excerpt':      text[:300],
            'tags':         d.get('tags', []),
        })
    idx_path.write_text(json.dumps(idx, ensure_ascii=False), encoding='utf-8')
    print(f'\nSearch index: {len(idx)} entries')


def main():
    print('=== Academy Cheat Sheets ===')
    academy_nav = process_academy_sheets()

    print('\n=== Reference Notes ===')
    ref_sections = process_reference_notes()

    # Build nav JSON
    nav = [
        {
            'type':  'section',
            'title': 'Cheat Sheets',
            'items': sorted(academy_nav, key=lambda x: x['title']),
        },
    ]
    for section_name, items in sorted(ref_sections.items()):
        nav.append({
            'type':  'section',
            'title': section_name,
            'items': sorted(items, key=lambda x: x['title']),
        })

    nav_path = NAV_DIR / f'{SOURCE_ID}.json'
    nav_path.write_text(json.dumps(nav, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\nNav: {nav_path}')

    update_search_index(SOURCE_ID)

    total = len(list(OUT_DIR.glob('*.json')))
    print(f'Total pages: {total}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Convert HTB Obsidian cheat sheets → p3ta-tricks processed JSON.

Handles two formats:
  1. Academy Cheat Sheets — markdown tables (Command | Description)
     → two-column HTML table, command cells become <pre><code> blocks
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
OUT_DIR     = ROOT / "content" / "processed" / "htb-academy"
NAV_DIR     = ROOT / "content" / "nav"
SOURCE_ID   = "htb-academy"
SOURCE_LABEL = "HTB Academy"

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

def _parse_table_rows(table_text: str) -> list[tuple[str, str]]:
    """Extract (command, description) pairs from a markdown table."""
    rows = []
    for line in table_text.splitlines():
        line = line.strip()
        if not line or line.startswith('|--') or line.startswith('| --') or line.startswith('| Command') or line.startswith('| command'):
            continue
        if not line.startswith('|'):
            continue
        parts = [p.strip() for p in line.strip('|').split('|')]
        if len(parts) >= 2:
            cmd  = parts[0].strip()
            desc = ' | '.join(parts[1:]).strip()
            if cmd:
                rows.append((cmd, desc))
    return rows


def _render_table(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return ''
    out = ['<table class="cheatsheet-table"><thead><tr><th>Command</th><th>Description</th></tr></thead><tbody>']
    for cmd, desc in rows:
        # Strip surrounding backticks if present (single-line inline code)
        if cmd.startswith('`') and cmd.endswith('`') and cmd.count('`') == 2:
            cmd = cmd[1:-1]
        desc_html = html.escape(desc)
        # Re-linkify backtick spans in description
        desc_html = re.sub(r'`([^`]+)`', r'<code>\1</code>', desc_html)
        out.append(f'<tr><td>{_code_block(cmd)}</td><td class="cmd-desc">{desc_html}</td></tr>')
    out.append('</tbody></table>')
    return '\n'.join(out)


def convert_academy_sheet(md_text: str, title: str) -> str:
    """Convert Academy cheat sheet (table format) to HTML."""
    # Remove Obsidian front matter if present
    md_text = re.sub(r'^---\n.*?\n---\n', '', md_text, flags=re.S)

    chunks = []
    # Split on H1 sections
    sections = re.split(r'^# (.+)$', md_text, flags=re.M)
    # sections[0] is preamble (usually empty), then [title, content, title, content ...]

    preamble = sections[0].strip()
    if preamble:
        chunks.append(f'<p>{html.escape(preamble)}</p>')

    it = iter(sections[1:])
    for sec_title, sec_body in zip(it, it):
        sec_title = sec_title.strip()
        chunks.append(f'<h2>{html.escape(sec_title)}</h2>')

        # Extract tables from section body
        # A table is a block of lines starting with |
        table_block = []
        other_lines = []
        current_table = []

        for line in sec_body.splitlines():
            if line.strip().startswith('|'):
                current_table.append(line)
            else:
                if current_table:
                    rows = _parse_table_rows('\n'.join(current_table))
                    if rows:
                        table_block.append(_render_table(rows))
                    current_table = []
                stripped = line.strip()
                if stripped:
                    other_lines.append(stripped)

        if current_table:
            rows = _parse_table_rows('\n'.join(current_table))
            if rows:
                table_block.append(_render_table(rows))

        # Non-table text as paragraphs (fenced code blocks, notes, etc.)
        non_table_html = _convert_fenced_blocks('\n'.join(other_lines))
        if non_table_html:
            chunks.append(non_table_html)

        chunks.extend(table_block)

    return '\n'.join(chunks)


# ── Reference note parser (fenced code block format) ──────────────────────────

def _convert_fenced_blocks(md_text: str) -> str:
    """Convert markdown with fenced code blocks to HTML."""
    if not md_text.strip():
        return ''

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
    """Convert plain prose to HTML paragraphs/headings."""
    lines = text.splitlines()
    out = []
    para = []

    def flush_para():
        if para:
            joined = ' '.join(para).strip()
            if joined:
                joined = re.sub(r'`([^`]+)`', r'<code>\1</code>', html.escape(joined))
                out.append(f'<p>{joined}</p>')
            para.clear()

    for line in lines:
        m2 = re.match(r'^## (.+)$', line)
        m3 = re.match(r'^### (.+)$', line)
        m1 = re.match(r'^# (.+)$', line)
        if m1:
            flush_para()
            out.append(f'<h2>{html.escape(m1.group(1))}</h2>')
        elif m2:
            flush_para()
            out.append(f'<h3>{html.escape(m2.group(1))}</h3>')
        elif m3:
            flush_para()
            out.append(f'<h4>{html.escape(m3.group(1))}</h4>')
        elif line.strip() == '' or line.strip() == '---':
            flush_para()
        else:
            para.append(line.strip())

    flush_para()
    return '\n'.join(out)


def convert_reference_note(md_text: str, title: str) -> str:
    """Convert a reference note (code-block format) to HTML."""
    md_text = re.sub(r'^---\n.*?\n---\n', '', md_text, flags=re.S)
    # Top-level H1 becomes the page title, skip it
    md_text = re.sub(r'^# .+\n', '', md_text, count=1, flags=re.M)
    return _convert_fenced_blocks(md_text)


# ── File processors ────────────────────────────────────────────────────────────

def process_academy_sheets() -> list[dict]:
    """Process all Academy Cheat Sheet .md files."""
    nav_items = []
    for fpath in sorted(VAULT_CHEATSHEETS.glob('*.md')):
        if fpath.name.startswith('1. Rename') or fpath.name.startswith('HTB Academy to'):
            continue

        title = fpath.stem
        slug  = _slugify(title)
        out_name = f'academy-{slug}.json'
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
            'path':         f'{SOURCE_ID}/academy-{slug}',
            'html':         full_html,
            'excerpt':      _excerpt(full_html),
            'tags':         ['htb-academy', 'cheatsheet'],
        }
        out_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        print(f'  academy: {title}')

        nav_items.append({
            'type':  'link',
            'title': title,
            'url':   f'/page/{SOURCE_ID}/academy-{slug}',
            'items': [],
        })

    return nav_items


def process_reference_notes() -> list[dict]:
    """Process all Reference .md files (recursive)."""
    nav_sections: dict[str, list] = {}

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
            'title': 'HTB Academy Cheat Sheets',
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

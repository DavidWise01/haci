#!/usr/bin/env python3
"""
hmd.py — HMD v0.1 reference parser + HTML renderer.

Usage:
    python3 hmd.py <file.hmd>              # parse and print blocks
    python3 hmd.py <file.hmd> --html       # render to HTML
    python3 hmd.py <file.hmd> --stats      # role statistics
    python3 hmd.py <file.hmd> --test       # self-hosting verification
"""

import re, sys, json
from html import escape

# ── lexer ──────────────────────────────────────────────────────────────

def classify_line(line):
    """Classify a single line per HMD v0.1 Rules 1-7."""
    s = line.strip()
    if not s:
        return ('BLANK', '', None)

    # Rule 1: ! = human command
    if s.startswith('!'):
        body = s[1:].strip()
        # also handle ?! and !? (Rule 7)
        if body.startswith('?'):
            return ('HUMAN_QUESTION', body[1:].strip(), '!?')
        return ('HUMAN', body, '!')

    # Rule 2 + 7: ? = question (subtyped by case)
    if s.startswith('?'):
        body = s[1:].strip()
        if body.startswith('!'):
            return ('HUMAN_QUESTION', body[1:].strip(), '?!')
        # case subtyping
        for ch in body:
            if ch.isalpha():
                if ch.isupper():
                    return ('HUMAN_QUESTION', body, '?')
                else:
                    return ('AI_QUESTION', body, '?')
                break
        return ('AI_QUESTION', body, '?')

    # Rule 3: > = evidence
    if s.startswith('>'):
        return ('EVIDENCE', s[1:].strip(), '>')

    # Rule 4: code fence (open/close tracked by parse())
    if re.match(r'^(`{3,}|~{3,})', s):
        return ('CODE_FENCE', s, None)

    # Rule 5: # heading
    if re.match(r'^#{1,6}\s', s):
        return ('HEADING', s.lstrip('#').strip(), '#')

    # HTML comment (version header, metadata)
    if s.startswith('<!--'):
        return ('META', s, None)

    # Rule 6: case convention
    for ch in s:
        if ch.isalpha():
            if ch.isupper():
                return ('DOCUMENTATION', s, None)
            else:
                return ('AI', s, None)

    # fallback: no alpha
    return ('DOCUMENTATION', s, None)


def parse(text):
    """Parse an HMD document into blocks."""
    lines = text.split('\n')
    blocks = []
    in_fence = False
    fence_buf = []
    fence_start = 0
    warnings = []

    for i, line in enumerate(lines, 1):
        s = line.strip()

        # fence tracking (Rule 4)
        if re.match(r'^\s*(`{3,}|~{3,})', line):
            if in_fence:
                fence_buf.append(line)
                blocks.append({
                    'role': 'CODE',
                    'content': '\n'.join(fence_buf),
                    'line': fence_start,
                })
                fence_buf = []
                in_fence = False
                continue
            else:
                in_fence = True
                fence_buf = [line]
                fence_start = i
                continue

        if in_fence:
            fence_buf.append(line)
            continue

        role, content, sym = classify_line(line)
        if role == 'BLANK':
            continue
        blocks.append({
            'role': role,
            'content': content,
            'line': i,
        })

    # unclosed fence warning
    if fence_buf:
        warnings.append(f"unclosed code fence starting at line {fence_start}")
        blocks.append({
            'role': 'CODE',
            'content': '\n'.join(fence_buf),
            'line': fence_start,
        })

    return blocks, warnings


# ── stats ──────────────────────────────────────────────────────────────

def stats(blocks):
    counts = {}
    chars = {}
    for b in blocks:
        r = b['role']
        counts[r] = counts.get(r, 0) + 1
        chars[r] = chars.get(r, 0) + len(b['content'])
    return counts, chars


# ── HTML renderer ──────────────────────────────────────────────────────

ROLE_COLORS = {
    'HUMAN':          ('#8a2be2', 'bold', 'HUMAN'),
    'HUMAN_QUESTION': ('#8a2be2', 'bold', 'HUMAN ?'),
    'AI':             ('#1db954', 'normal', 'AI'),
    'AI_QUESTION':    ('#1db954', 'normal', 'AI ?'),
    'DOCUMENTATION':  ('#c8c0b0', 'normal', 'DOC'),
    'EVIDENCE':       ('#d9a441', 'normal', 'EVIDENCE'),
    'CODE':           ('#73b3a3', 'normal', 'CODE'),
    'HEADING':        ('#e9e2d2', 'bold', 'HEADING'),
    'META':           ('#5b5868', 'normal', 'META'),
}

def render_html(blocks, title="HMD Document"):
    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)}</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;700&family=Spectral:wght@300;400&display=swap" rel="stylesheet">
<style>
body{{margin:0;background:#170d20;color:#c8c0b0;font-family:"Spectral",serif;line-height:1.6;display:flex;justify-content:center}}
.doc{{max-width:720px;width:100%;padding:32px 24px 60px}}
.block{{display:flex;gap:12px;margin:3px 0;align-items:baseline}}
.tag{{font-family:"IBM Plex Mono",monospace;font-size:9px;letter-spacing:.08em;min-width:72px;text-align:right;
  opacity:.5;flex-shrink:0;padding-top:2px}}
.content{{flex:1;font-size:15px}}
.content.bold{{font-weight:bold}}
pre{{background:rgba(0,0,0,.25);border:1px solid rgba(154,152,166,.15);border-radius:6px;padding:12px;
  font-family:"IBM Plex Mono",monospace;font-size:13px;overflow-x:auto;margin:0;white-space:pre-wrap}}
.heading{{font-size:22px;font-weight:bold;margin-top:18px;color:#e9e2d2}}
.h2{{font-size:18px}} .h3{{font-size:15px}}
</style>
</head>
<body>
<div class="doc">
""")
    for b in blocks:
        role = b['role']
        color, weight, label = ROLE_COLORS.get(role, ('#9a98a6', 'normal', role))
        content = escape(b['content'])

        if role == 'CODE':
            # strip fence markers for display
            lines = b['content'].split('\n')
            code_body = '\n'.join(lines[1:-1]) if len(lines) > 2 else b['content']
            parts.append(f'<div class="block"><span class="tag" style="color:{color}">{label}</span>'
                        f'<pre style="color:{color}">{escape(code_body)}</pre></div>')
        elif role == 'HEADING':
            level = 'heading'
            # detect level from original content
            raw = b.get('content', '')
            parts.append(f'<div class="block"><span class="tag" style="color:{color}">{label}</span>'
                        f'<div class="content heading" style="color:{color}">{content}</div></div>')
        else:
            bold = ' bold' if weight == 'bold' else ''
            parts.append(f'<div class="block"><span class="tag" style="color:{color}">{label}</span>'
                        f'<div class="content{bold}" style="color:{color}">{content}</div></div>')

    parts.append('</div>\n</body>\n</html>')
    return '\n'.join(parts)


# ── self-hosting test ──────────────────────────────────────────────────

def self_host_test(blocks):
    """Verify that the spec parsed in its own format has the expected role distribution."""
    counts, chars = stats(blocks)
    print("\n  Self-hosting verification:")
    print(f"  Total blocks: {len(blocks)}")
    print(f"  Role distribution:")
    for role in sorted(counts.keys()):
        print(f"    {role:20s}  {counts[role]:3d} blocks  {chars[role]:5d} chars")

    # check that all five roles are present (the spec uses all of them)
    required = {'HUMAN', 'AI', 'DOCUMENTATION', 'EVIDENCE', 'CODE', 'HEADING'}
    present = set(counts.keys())
    missing = required - present
    extra = present - required - {'META', 'AI_QUESTION', 'HUMAN_QUESTION'}

    has_human = counts.get('HUMAN', 0) >= 3      # at least 3 ! directives
    has_ai = counts.get('AI', 0) >= 3             # at least 3 lowercase proposals
    has_evidence = counts.get('EVIDENCE', 0) >= 1
    has_code = counts.get('CODE', 0) >= 3         # several code blocks
    has_docs = counts.get('DOCUMENTATION', 0) >= 5
    has_questions = counts.get('AI_QUESTION', 0) + counts.get('HUMAN_QUESTION', 0) >= 1

    checks = [
        (not missing, f"all required roles present (missing: {missing})" if missing else "all required roles present"),
        (has_human, f"human commands: {counts.get('HUMAN', 0)}"),
        (has_ai, f"AI proposals: {counts.get('AI', 0)}"),
        (has_evidence, f"evidence blocks: {counts.get('EVIDENCE', 0)}"),
        (has_code, f"code blocks: {counts.get('CODE', 0)}"),
        (has_docs, f"documentation blocks: {counts.get('DOCUMENTATION', 0)}"),
        (has_questions, f"questions: {counts.get('AI_QUESTION', 0) + counts.get('HUMAN_QUESTION', 0)}"),
    ]

    all_pass = True
    for ok, desc in checks:
        mark = '✓' if ok else '✗'
        if not ok: all_pass = False
        print(f"    {mark} {desc}")

    print(f"\n  {'✓ SELF-HOSTING TEST PASSED — the spec parses in its own format' if all_pass else '✗ SELF-HOSTING TEST FAILED'}")
    return all_pass


# ── main ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("usage: python3 hmd.py <file.hmd> [--html | --stats | --test]")
        sys.exit(1)

    path = sys.argv[1]
    with open(path) as f:
        text = f.read()

    blocks, warnings = parse(text)

    if warnings:
        for w in warnings:
            print(f"  ⚠ {w}")

    mode = sys.argv[2] if len(sys.argv) > 2 else '--print'

    if mode == '--html':
        html = render_html(blocks, title=path)
        out_path = path.rsplit('.', 1)[0] + '.html'
        with open(out_path, 'w') as f:
            f.write(html)
        print(f"  rendered to {out_path}")

    elif mode == '--stats':
        counts, chars = stats(blocks)
        print(json.dumps({'counts': counts, 'chars': chars}, indent=2))

    elif mode == '--test':
        self_host_test(blocks)

    else:
        for b in blocks:
            preview = b['content'][:65].replace('\n', ' ↵ ')
            if len(b['content']) > 65: preview += '…'
            print(f"  {b['role']:20s} L{b['line']:>3}  {preview}")

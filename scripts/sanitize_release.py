"""sanitize_release.py
Strip local secrets and create a shareable archive.

Usage:
  python scripts/sanitize_release.py --src . --out osoul-share.zip

It will:
- delete .streamlit/secrets.toml if present
- delete .env, .env.* (except .env.example)
- redact any accidental DATABASE_URL / API keys in text files (best-effort)
"""
from __future__ import annotations
import argparse, os, re, zipfile
from pathlib import Path

REDACTIONS = [
    (re.compile(r'(?i)(postgres(?:ql)?://[^\s:/@]+:)([^@\s]+)(@)'), r'\1***\3'),
    (re.compile(r'(?i)(TWELVEDATA_API_KEY\s*[:=]\s*)([^\s\n\r]+)'), r'\1***'),
    (re.compile(r'(?i)(AUTH_SECRET\s*[:=]\s*)([^\s\n\r]+)'), r'\1***'),
]

TEXT_EXTS = {'.py','.md','.txt','.toml','.yaml','.yml','.env','.example','.ini','.cfg'}

def redact_text(s: str) -> str:
    out = s
    for rx, rep in REDACTIONS:
        out = rx.sub(rep, out)
    return out

def should_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTS

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default='.', help='project root')
    ap.add_argument('--out', default='osoul-share.zip', help='output zip')
    args = ap.parse_args()

    root = Path(args.src).resolve()
    out = Path(args.out).resolve()

    # delete local-only secrets files if present
    for p in [root/'.streamlit'/'secrets.toml', root/'.env']:
        if p.exists():
            p.unlink()

    # delete .env.* except .env.example
    for p in root.glob('.env.*'):
        if p.name != '.env.example':
            try:
                p.unlink()
            except Exception:
                pass

    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for path in root.rglob('*'):
            if path.is_dir():
                continue
            rel = path.relative_to(root)
            # extra safety: never include secrets.toml
            if rel.as_posix() == '.streamlit/secrets.toml':
                continue
            # read text and redact
            if should_text(path):
                try:
                    data = path.read_text(encoding='utf-8', errors='ignore')
                    data = redact_text(data)
                    z.writestr(rel.as_posix(), data)
                    continue
                except Exception:
                    pass
            z.write(path, rel.as_posix())

    print(f'Wrote: {out}')

if __name__ == '__main__':
    main()

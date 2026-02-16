# How to apply this patch

1) **Copy/merge** the files from this patch into your `osoul-app-main/` project, keeping the same paths:
- `PATCH_MANIFEST`
- `SECURITY_NOTE.md`
- `scripts/sanitize_release.py`

2) **Delete** the following file(s) from your project (and from any shared archives):
- `.streamlit/secrets.toml`

3) **Rotate secrets immediately** (DB password / AUTH_SECRET / API keys) if that file was ever shared.

## Tip
Run the sanitizer script before sharing:
```bash
python scripts/sanitize_release.py --src . --out dist/osoul-app-main_sanitized.zip
```

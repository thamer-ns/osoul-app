import re
import streamlit as st


def _strip_html_to_text(html: str) -> str:
    """
    Convert basic HTML to readable text (safe fallback),
    used when we *don't* want to render raw HTML.
    """
    if not isinstance(html, str):
        return str(html)

    # Replace breaks and paragraphs with newlines
    text = re.sub(r"(?i)<br\s*/?>", "\n", html)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?i)<p\s*>", "", text)

    # Remove style/script tags
    text = re.sub(r"(?is)<script.*?>.*?</script>", "", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", "", text)

    # Remove other tags
    text = re.sub(r"(?s)<[^>]+>", "", text)

    # Unescape common entities
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )

    # Normalize whitespace
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def render_note(label: str, body: str):
    """
    Show a clean readable note box (instead of st.code()).
    """
    safe_text = _strip_html_to_text(body)
    st.markdown(
        f"""
<div class="os-note">
  <div class="label">{label}</div>
  <div>{safe_text.replace("\n", "<br>")}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_scenario(title: str, html_or_text: str):
    """
    Render a scenario block:
    - If content looks like HTML, render it as HTML
    - Otherwise render markdown text
    """
    st.markdown(f"### {title}")

    if isinstance(html_or_text, str) and ("<div" in html_or_text or "<span" in html_or_text or "<p" in html_or_text):
        st.markdown(html_or_text, unsafe_allow_html=True)
    else:
        st.markdown(str(html_or_text))


def render_recommendation_section(reco: dict):
    """
    Example renderer for recommendation output where previous UI showed HTML raw.
    This function keeps your logic but ensures HTML is rendered properly and
    the explanation is readable.
    """
    if not isinstance(reco, dict):
        st.warning("Recommendation output is not a dict.")
        st.write(reco)
        return

    # Main summary
    summary = reco.get("summary", "")
    if summary:
        render_note("سبب التوصية", summary)

    # Scenarios
    scenarios = reco.get("scenarios", None)
    if scenarios and isinstance(scenarios, list):
        st.markdown("## السيناريوهات")
        for idx, sc in enumerate(scenarios, start=1):
            title = sc.get("title", f"سيناريو {idx}")
            content = sc.get("html", sc.get("content", sc))
            render_scenario(title, content)

    # Any extra fields
    extras = {k: v for k, v in reco.items() if k not in ("summary", "scenarios")}
    if extras:
        with st.expander("تفاصيل إضافية", expanded=False):
            st.json(extras)

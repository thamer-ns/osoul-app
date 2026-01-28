import streamlit as st
import pandas as pd

def safe_fmt(val, suffix=""):
    try: return f"{float(val):,.2f}{suffix}"
    except: return str(val)

def render_kpi(label, value, color_class="neutral", icon="📊"):
    val_color = {"success":"#059669", "danger":"#DC2626", "blue":"#2563EB"}.get(color_class, "#1E293B")
    st.markdown(f"""<div class="kpi-card"><div class="kpi-icon-bg">{icon}</div><div class="kpi-label">{label}</div><div class="kpi-value" style="color: {val_color} !important;">{value}</div></div>""", unsafe_allow_html=True)

def render_ticker_card(symbol, name, price, change):
    col, bg = ("#059669","#DCFCE7") if change>=0 else ("#DC2626","#FEE2E2")
    st.markdown(f"""<div class="kpi-card" style="padding:15px;min-height:120px;"><div style="display:flex;justify-content:space-between;"><div style="font-weight:900;">{symbol}</div><div style="color:{col};background:{bg};padding:2px 8px;border-radius:8px;font-size:0.8rem;">{change:+.2f}%</div></div><div style="font-size:1.5rem;font-weight:900;">{price:,.2f}</div><div style="font-size:0.75rem;color:#94A3B8;">{name}</div></div>""", unsafe_allow_html=True)

def render_custom_table(df, config):
    if df is None or df.empty: st.info("📭 لا توجد بيانات"); return
    headers = "".join([f'<th>{l}</th>' for _, l, _ in config])
    rows = []
    for _, r in df.iterrows():
        cells = []
        for k, _, t in config:
            v = r.get(k, ""); d = v; c = ""
            try:
                if t=='money': d=f"{float(v):,.2f}"; c="txt-blue"
                elif t=='percent': d=f"{float(v):.2f}%"; c="txt-green" if float(v)>=0 else "txt-red"
                elif t=='colorful': d=f"{float(v):+,.2f}"; c="txt-green" if float(v)>=0 else "txt-red"
                elif t=='badge': d=f'<span class="badge badge-{"open" if str(v)=="مفتوحة" else "closed"}">{v}</span>'
                elif t=='date': d=str(v).split(" ")[0]
            except: pass
            cells.append(f'<td><span class="{c}">{d}</span></td>')
        rows.append(f'<tr>{"".join(cells)}</tr>')
    st.markdown(f'<div style="overflow-x:auto;"><table class="finance-table"><thead><tr>{headers}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>', unsafe_allow_html=True)

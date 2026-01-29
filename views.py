import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from config import DEFAULT_COLORS
from components import render_kpi, render_custom_table, render_ticker_card, safe_fmt
from analytics import calculate_portfolio_metrics, update_prices, generate_equity_curve, create_smart_backup
from database import execute_query, fetch_table
from market_data import get_static_info, get_tasi_data, get_chart_history, fetch_batch_data
from data_source import get_company_details 
from security import validate_trade_inputs 

# --- استيراد آمن للوحدات ---
try:
    from charts import render_technical_chart
    from backtester import run_backtest
    from financial_analysis import render_financial_dashboard_ui, get_fundamental_ratios, get_thesis, save_thesis, FinancialParser, save_financial_record, get_stored_financials_df, get_advanced_fundamental_ratios, sync_auto_yahoo
    from classical_analysis import render_classical_analysis
    from ai_engine import generate_ai_report, calculate_portfolio_risk_score, run_stress_test, generate_rebalancing_suggestions
except ImportError:
    # دوال وهمية لمنع توقف النظام
    def render_technical_chart(*a): st.warning("الرسوم البيانية غير متوفرة")
    def run_backtest(*a): return None
    def render_financial_dashboard_ui(*a): st.warning("التحليل المالي غير متوفر")
    def get_fundamental_ratios(*a): return {}
    def get_thesis(*a): return {}
    def save_thesis(*a): pass
    def render_classical_analysis(*a): pass
    def generate_ai_report(*a): return {}
    def calculate_portfolio_risk_score(*a): return 50
    def run_stress_test(*a): return {"scenarios": [], "insight": ""}
    def generate_rebalancing_suggestions(*a): return []
    class FinancialParser: pass
    def save_financial_record(*args): pass
    def sync_auto_yahoo(s): return False, "Module Missing"
    def get_stored_financials_df(s, p): return pd.DataFrame()
    def get_advanced_fundamental_ratios(s): return {}

# 1. Navigation
def render_navbar():
    buttons = [
        ('🏠 الرئيسية','home'), ('⚡ مضاربة','spec'), ('💎 استثمار','invest'), 
        ('💓 نبض','pulse'), ('📜 صكوك','sukuk'), ('🔍 تحليل','analysis'), 
        ('🧪 المختبر','backtest'), ('💰 السيولة','cash'), ('🔄 تحديث','update')
    ]
    
    st.markdown("""<style>div.stButton > button {width: 100%; border-radius: 8px;}</style>""", unsafe_allow_html=True)
    
    cols = st.columns(len(buttons) + 1)
    for i, (label, key) in enumerate(buttons):
        with cols[i]:
            type_btn = "primary" if st.session_state.page == key else "secondary"
            if st.button(label, key=f"nav_{key}", type=type_btn): 
                st.session_state.page = key
                st.rerun()
                
    with cols[-1]:
        with st.popover("👤 القائمة"):
            st.write(f"مرحباً {st.session_state.get('username','User')}")
            if st.button("➕ إضافة صفقة"): st.session_state.page='add'; st.rerun()
            if st.button("⚙️ إعدادات"): st.session_state.page='settings'; st.rerun()
            st.markdown("---")
            if st.button("🚪 خروج"): 
                try: from security import logout; logout()
                except: st.session_state.clear(); st.rerun()

# 2. Dashboard
def view_dashboard(fin):
    try: tp, tc = get_tasi_data()
    except: tp, tc = 0, 0
    ar = "🔼" if tc >= 0 else "🔽"
    
    df = fin['all_trades']
    total_assets = fin['market_val_open'] + fin['cash']
    cash_pct = (fin['cash'] / total_assets * 100) if total_assets else 0
    
    risk_score = calculate_portfolio_risk_score(df, cash_pct)
    risk_color = "success" if risk_score < 40 else "danger" if risk_score > 70 else "neutral"
    risk_label = "منخفضة" if risk_score < 40 else "عالية" if risk_score > 70 else "متوسطة"

    c_tasi, c_risk = st.columns([3, 1])
    with c_tasi:
        st.markdown(f"""
        <div class="tasi-card">
            <div><div style="opacity:0.9;">المؤشر العام (TASI)</div><div style="font-size:2.5rem; font-weight:900;">{safe_fmt(tp)}</div></div>
            <div style="background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:10px; font-weight:bold; direction:ltr;">{ar} {tc:.2f}%</div>
        </div>""", unsafe_allow_html=True)
    with c_risk:
        render_kpi(f"المخاطرة ({risk_label})", f"{risk_score}/100", risk_color, "🛡️")
    
    c1, c2, c3, c4 = st.columns(4)
    total_pl = fin['unrealized_pl'] + fin['realized_pl']
    with c1: render_kpi(f"الكاش ({cash_pct:.1f}%)", safe_fmt(fin['cash']), "blue", "💵")
    with c2: render_kpi("صافي الإيداعات", safe_fmt(fin['total_deposited']-fin['total_withdrawn']), "neutral", "🏗️")
    with c3: render_kpi("إجمالي الأصول", safe_fmt(total_assets), "neutral", "🏦")
    with c4: render_kpi("الربح الكلي", safe_fmt(total_pl), 'success' if total_pl>=0 else 'danger', "📈")
    
    st.markdown("---")
    
    o1, o2, o3, o4 = st.columns(4)
    open_pct = (fin['unrealized_pl'] / fin['cost_open'] * 100) if fin['cost_open'] else 0
    with o1: render_kpi("التكلفة", safe_fmt(fin['cost_open']), "neutral")
    with o2: render_kpi("القيمة السوقية", safe_fmt(fin['market_val_open']), "blue")
    with o3: render_kpi("الربح الورقي", safe_fmt(fin['unrealized_pl']), "success" if fin['unrealized_pl']>=0 else "danger")
    with o4: render_kpi("النمو", f"{open_pct:.2f}%", "success" if open_pct>=0 else "danger")

    if not df.empty:
        # الرسوم البيانية
        open_trades = df[df['status'] == 'Open']
        try:
            invest_val = open_trades[open_trades['strategy'].astype(str).str.contains('استثمار', na=False)]['market_value'].sum()
            spec_val = open_trades[open_trades['strategy'].astype(str).str.contains('مضاربة', na=False)]['market_value'].sum()
        except: invest_val = spec_val = 0
        sukuk_val = open_trades[open_trades['asset_type'] == 'Sukuk']['market_value'].sum()
        
        alloc_df = pd.DataFrame({'Asset': ['استثمار', 'مضاربة', 'صكوك', 'كاش'], 'Value': [invest_val, spec_val, sukuk_val, fin['cash']]})
        alloc_df = alloc_df[alloc_df['Value'] > 0]
        
        c_ch1, c_ch2 = st.columns(2)
        with c_ch1:
            st.subheader("توزيع الأصول")
            st.plotly_chart(px.pie(alloc_df, values='Value', names='Asset', hole=0.4), use_container_width=True)
        with c_ch2:
            st.subheader("نمو المحفظة")
            crv = generate_equity_curve(df)
            if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested'), use_container_width=True)

# 3. Portfolio View (مع إعادة الفرز)
def view_portfolio(fin, key):
    ts = "مضاربة" if key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    st.markdown("""<style>.finance-table td, .finance-table th {white-space: nowrap !important;font-size: 0.85rem !important;vertical-align: middle !important;}</style>""", unsafe_allow_html=True)
    
    df = fin['all_trades']
    if df.empty:
        sub = pd.DataFrame(columns=['status', 'total_cost', 'market_value', 'gain', 'symbol', 'date', 'id'])
    else:
        sub = df[df['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    op = sub[sub['status'] == 'Open'].copy()
    cl = sub[sub['status'] == 'Close'].copy()
    
    t1, t2 = st.tabs(["الصفقات القائمة", "الأرشيف"])
    
    with t1:
        # الإجماليات
        k1, k2, k3 = st.columns(3)
        with k1: render_kpi("التكلفة", safe_fmt(op['total_cost'].sum() if not op.empty else 0), "neutral")
        with k2: render_kpi("القيمة السوقية", safe_fmt(op['market_value'].sum() if not op.empty else 0), "blue")
        with k3: render_kpi("الربح/الخسارة", safe_fmt(op['gain'].sum() if not op.empty else 0), "success" if (op['gain'].sum() if not op.empty else 0)>=0 else "danger")
        st.markdown("---")

        if not op.empty:
            # ✅ إعادة ميزة الفرز (Sort)
            sort_opts = ["الربح (الأعلى)", "القيمة (الأعلى)", "التاريخ (الأحدث)", "الرمز"]
            c_sort, _ = st.columns([1, 3])
            sort_by = c_sort.selectbox(f"فرز {ts} حسب:", sort_opts, key=f"s_op_{key}")
            
            if "الربح" in sort_by: op = op.sort_values('gain', ascending=False)
            elif "القيمة" in sort_by: op = op.sort_values('market_value', ascending=False)
            elif "الرمز" in sort_by: op = op.sort_values('symbol')
            else: op = op.sort_values('date', ascending=False)

            live_data = fetch_batch_data(op['symbol'].unique().tolist())
            op['current_price'] = op['symbol'].apply(lambda x: live_data.get(x, {}).get('price', 0))
            
            render_custom_table(op, [
                ('symbol','الرمز','text'), ('company_name','الشركة','text'), 
                ('quantity','الكمية','text'), ('entry_price','التكلفة','money'), 
                ('current_price','السعر','money'), ('gain','الربح','colorful'), ('gain_pct','%','percent')
            ])
            
            # عمليات البيع والتعديل (داخل Expander كما طلبت)
            c_a1, c_a2 = st.columns(2)
            with c_a1:
                with st.expander("🔴 بيع / إغلاق صفقة"):
                    s_id = st.selectbox("اختر الصفقة", op['id'].tolist(), format_func=lambda x: f"{op[op['id']==x]['company_name'].iloc[0]}", key=f"s_{key}")
                    if s_id:
                        with st.form(f"frm_s_{s_id}"):
                            pr = st.number_input("سعر البيع")
                            dt = st.date_input("تاريخ")
                            if st.form_submit_button("تأكيد البيع"):
                                valid, msg = validate_trade_inputs(1, pr)
                                if valid:
                                    execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s", (pr, str(dt), s_id))
                                    st.success("تم"); st.cache_data.clear(); st.rerun()
                                else: st.error(msg)
            with c_a2:
                with st.expander("✏️ تعديل صفقة"):
                    e_id = st.selectbox("اختر الصفقة", op['id'].tolist(), key=f"e_{key}")
                    if e_id:
                        rw = op[op['id']==e_id].iloc[0]
                        with st.form(f"frm_e_{e_id}"):
                            nq = st.number_input("الكمية", value=float(rw['quantity']))
                            np = st.number_input("السعر", value=float(rw['entry_price']))
                            if st.form_submit_button("حفظ التعديل"):
                                valid, msg = validate_trade_inputs(nq, np)
                                if valid:
                                    execute_query("UPDATE Trades SET quantity=%s, entry_price=%s WHERE id=%s", (nq, np, e_id))
                                    st.success("تم"); st.cache_data.clear(); st.rerun()
                                else: st.error(msg)
        else: st.info("لا توجد صفقات قائمة")
        
        # زر الإضافة
        st.markdown("---")
        if st.button("➕ إضافة سهم جديد", key=f"add_{key}"): st.session_state.page='add'; st.rerun()

    with t2:
        if not cl.empty:
            # ✅ إعادة الفرز للأرشيف
            sort_cl = st.selectbox("فرز الأرشيف:", ["التاريخ (الأحدث)", "الربح (الأعلى)"], key=f"s_cl_{key}")
            if "الربح" in sort_cl: cl = cl.sort_values('gain', ascending=False)
            else: cl = cl.sort_values('exit_date', ascending=False)
            
            render_custom_table(cl, [('company_name','الشركة','text'), ('gain','الربح','colorful'), ('exit_date','تاريخ البيع','date')])
        else: st.info("الأرشيف فارغ")

# 4. Sukuk Portfolio (مع إعادة الفرز والترتيب)
def view_sukuk_portfolio(fin):
    st.header("📜 محفظة الصكوك")
    df = fin['all_trades']
    sukuk = df[df['asset_type'] == 'Sukuk'].copy() if not df.empty else pd.DataFrame()
    
    op = sukuk[sukuk['status'] == 'Open'].copy()
    cl = sukuk[sukuk['status'] == 'Close'].copy()
    
    t1, t2 = st.tabs(["الصكوك القائمة", "الأرشيف"])
    
    with t1:
        if not op.empty:
            k1, k2, k3 = st.columns(3)
            with k1: render_kpi("إجمالي الاستثمار", safe_fmt(op['total_cost'].sum()), "neutral")
            with k2: render_kpi("القيمة الحالية", safe_fmt(op['market_value'].sum()), "blue")
            with k3: render_kpi("الربح", safe_fmt(op['gain'].sum()), "success")
            st.markdown("---")
            
            # ✅ إعادة الفرز
            sb = st.selectbox("فرز حسب:", ["التاريخ", "القيمة", "الاسم"], key="sort_sk")
            if "القيمة" in sb: op = op.sort_values('total_cost', ascending=False)
            elif "الاسم" in sb: op = op.sort_values('company_name')
            else: op = op.sort_values('date', ascending=False)
            
            render_custom_table(op, [('company_name','الصك','text'), ('quantity','العدد','text'), ('total_cost','القيمة','money'), ('date','تاريخ الشراء','date')])
            
            # البيع والتعديل (مخفي داخل Expander)
            c1, c2 = st.columns(2)
            with c1:
                with st.expander("💰 استرداد صك"):
                    sid = st.selectbox("الصك", op['id'].tolist(), format_func=lambda x: op[op['id']==x]['company_name'].iloc[0])
                    if sid:
                        with st.form(f"sk_s_{sid}"):
                            val = st.number_input("المبلغ المسترد")
                            dt = st.date_input("تاريخ")
                            if st.form_submit_button("تأكيد"):
                                qty = op[op['id']==sid].iloc[0]['quantity']
                                pr = val / qty if qty else 0
                                execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s", (pr, str(dt), sid))
                                st.success("تم"); st.cache_data.clear(); st.rerun()
            with c2:
                with st.expander("✏️ تعديل"):
                    eid = st.selectbox("الصك", op['id'].tolist(), key="sk_e")
                    if eid:
                        rw = op[op['id']==eid].iloc[0]
                        with st.form(f"sk_e_{eid}"):
                            nm = st.text_input("الاسم", value=rw['company_name'])
                            qt = st.number_input("العدد", value=float(rw['quantity']))
                            pr = st.number_input("السعر", value=float(rw['entry_price']))
                            if st.form_submit_button("حفظ"):
                                execute_query("UPDATE Trades SET company_name=%s, quantity=%s, entry_price=%s WHERE id=%s", (nm, qt, pr, eid))
                                st.success("تم"); st.cache_data.clear(); st.rerun()
        else: st.info("لا توجد صكوك قائمة")
        
        st.markdown("---")
        if st.button("➕ إضافة صك جديد"): st.session_state.page='add'; st.rerun()

    with t2:
        if not cl.empty:
            render_custom_table(cl, [('company_name','الصك','text'), ('gain','العائد','colorful'), ('exit_date','تاريخ الاسترداد','date')])
        else: st.info("الأرشيف فارغ")

# 5. Cash Log (مع إعادة الإجماليات والنماذج المخفية)
def view_cash_log():
    st.header("💰 سجل السيولة")
    fin = calculate_portfolio_metrics()
    
    # ✅ إعادة الإجماليات المفقودة في الأعلى
    dep = fin.get('deposits', pd.DataFrame())
    wit = fin.get('withdrawals', pd.DataFrame())
    ret = fin.get('returns', pd.DataFrame())
    
    c1, c2, c3 = st.columns(3)
    with c1: render_kpi("إجمالي الإيداع", safe_fmt(dep['amount'].sum() if not dep.empty else 0), "success")
    with c2: render_kpi("إجمالي السحب", safe_fmt(wit['amount'].sum() if not wit.empty else 0), "danger")
    with c3: render_kpi("إجمالي العوائد", safe_fmt(ret['amount'].sum() if not ret.empty else 0), "blue")
    
    st.markdown("---")
    t1, t2, t3 = st.tabs(["📥 الإيداعات", "📤 السحوبات", "🎁 العوائد"])
    
    # ✅ إعادة النماذج داخل Expander (مغلقة افتراضياً)
    with t1:
        with st.expander("➕ تسجيل إيداع جديد"):
            with st.form("d"):
                a = st.number_input("المبلغ")
                d = st.date_input("التاريخ", date.today())
                n = st.text_input("ملاحظة")
                if st.form_submit_button("حفظ"):
                    if a>0: execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n)); st.success("تم"); st.cache_data.clear(); st.rerun()
        if not dep.empty: render_custom_table(dep.sort_values('date', ascending=False), [('date','تاريخ','date'),('amount','مبلغ','money'),('note','ملاحظة','text')])
        
    with t2:
        with st.expander("➖ تسجيل سحب جديد"):
            with st.form("w"):
                a = st.number_input("المبلغ")
                d = st.date_input("التاريخ", date.today())
                n = st.text_input("ملاحظة")
                if st.form_submit_button("حفظ"):
                    if a>0: execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n)); st.success("تم"); st.cache_data.clear(); st.rerun()
        if not wit.empty: render_custom_table(wit.sort_values('date', ascending=False), [('date','تاريخ','date'),('amount','مبلغ','money'),('note','ملاحظة','text')])

    with t3:
        with st.expander("💵 تسجيل عائد/توزيع"):
            with st.form("r"):
                s = st.text_input("السهم")
                a = st.number_input("المبلغ")
                d = st.date_input("التاريخ", date.today())
                if st.form_submit_button("حفظ"):
                    if a>0: execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (%s,%s,%s)", (str(d), s, a)); st.success("تم"); st.cache_data.clear(); st.rerun()
        if not ret.empty: render_custom_table(ret.sort_values('date', ascending=False), [('date','تاريخ','date'),('symbol','سهم','text'),('amount','مبلغ','money')])

# 6. Analysis
def view_analysis(fin):
    st.header("🔬 التحليل الشامل")
    trades = fin['all_trades']
    
    if not trades.empty:
        open_pos = trades[trades['status']=='Open']
        st.subheader("📊 اختبار التحمل")
        res = run_stress_test(fin['market_val_open'], open_pos)
        if res['scenarios']:
            sdf = pd.DataFrame(res['scenarios'])
            st.plotly_chart(px.bar(sdf, x='scenario', y='impact_pct', color='scenario', color_discrete_map={r['scenario']:r['color'] for _,r in sdf.iterrows()}), use_container_width=True)
            st.info(res['insight'])
    
    syms = list(trades['symbol'].unique())
    s = st.selectbox("اختر السهم", syms) if syms else None
    
    if s:
        n, _ = get_company_details(s)
        st.markdown(f"### {n} ({s})")
        tabs = st.tabs(["🤖 المستشار", "💰 مالي", "📈 فني", "📝 أطروحة"])
        
        with tabs[0]:
            rep = generate_ai_report(s)
            col = rep.get('color', '#666')
            st.markdown(f"<div style='padding:15px;border:2px solid {col};border-radius:10px;text-align:center;'><h3>{rep.get('recommendation','-')}</h3><p>{rep.get('strategy','-')}</p></div>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1: 
                st.write("فني:"); 
                for x in rep.get('tech_reasons',[]): st.write(f"- {x}")
            with c2: 
                st.write("مالي:"); 
                for x in rep.get('fund_reasons',[]): st.write(f"- {x}")
                
        with tabs[1]: render_financial_dashboard_ui(s)
        with tabs[2]: render_technical_chart(s)
        with tabs[3]:
            th = get_thesis(s)
            txt = th['thesis_text'] if th else ""
            with st.form("th"):
                nt = st.text_area("نص", value=txt)
                if st.form_submit_button("حفظ"): save_thesis(s, nt, 0, "Hold"); st.success("تم")

# 7. Others
def view_backtester_ui(fin):
    st.header("🧪 المختبر")
    if run_backtest:
        s = st.text_input("رمز السهم", "1120")
        if st.button("بدء"):
            res = run_backtest(get_chart_history(s, "2y"), "Trend", 100000)
            if res:
                st.metric("العائد", f"{res['return_pct']:.1f}%")
                st.line_chart(res['df']['Portfolio_Value'])
    else: st.warning("المختبر غير متوفر")

def render_pulse_dashboard():
    st.header("نبض السوق")
    trades = fetch_table("Trades")
    syms = list(trades['symbol'].unique()) if not trades.empty else []
    if syms:
        d = fetch_batch_data(syms)
        cols = st.columns(4)
        for i, (s, v) in enumerate(d.items()):
            chg = ((v['price']-v['prev_close'])/v['prev_close'])*100
            with cols[i%4]: render_ticker_card(s, "سهم", v['price'], chg)

def view_add_trade():
    st.header("إضافة")
    with st.form("a"):
        s = st.text_input("رمز")
        q = st.number_input("كمية")
        p = st.number_input("سعر")
        ty = st.selectbox("نوع", ["استثمار", "مضاربة", "صكوك"])
        if st.form_submit_button("حفظ"):
            valid, msg = validate_trade_inputs(q, p)
            if valid:
                nm, sec = get_company_details(s)
                at = "Sukuk" if ty == "صكوك" else "Stock"
                execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, quantity, entry_price, strategy, status) VALUES (%s,%s,%s,%s,%s,%s,%s,'Open')", (s,nm,sec,at,q,p,ty))
                st.success("تم"); st.cache_data.clear()
            else: st.error(msg)

def view_tools(): st.info("أدوات")
def view_settings(): 
    st.header("الإعدادات")
    if st.button("نسخة احتياطية"):
        d, n = create_smart_backup()
        if d: st.download_button("تحميل", d, n)

# 8. Router
def router():
    if 'page' not in st.session_state: st.session_state.page = 'home'
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    
    if pg == 'home': view_dashboard(fin)
    elif pg == 'spec': view_portfolio(fin, 'spec') 
    elif pg == 'invest': view_portfolio(fin, 'invest')
    elif pg == 'sukuk': view_sukuk_portfolio(fin)
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'cash': view_cash_log()
    elif pg == 'backtest': view_backtester_ui(fin)
    elif pg == 'pulse': render_pulse_dashboard()
    elif pg == 'add': view_add_trade()
    elif pg == 'tools': view_tools()
    elif pg == 'settings': view_settings()
    elif pg == 'update': 
        with st.spinner(".."): update_prices(); st.rerun()

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

# ========================================================
# 🛡️ استيراد الوحدات مع الحماية (Fail-Safe Imports)
# ========================================================

# 1. الرسوم البيانية
try:
    from charts import render_technical_chart
except ImportError:
    def render_technical_chart(symbol): st.warning("⚠️ ملف charts.py مفقود أو به خطأ.")

# 2. المختبر (Backtester)
try:
    from backtester import run_backtest
except ImportError:
    run_backtest = None # سنفحص هذا المتغير لاحقاً

# 3. التحليل المالي
try:
    from financial_analysis import render_financial_dashboard_ui, get_thesis, save_thesis
except ImportError:
    def render_financial_dashboard_ui(s): st.warning("⚠️ ملف financial_analysis.py مفقود.")
    def get_thesis(s): return {}
    def save_thesis(s, t, tg, r): pass

# 4. التحليل الكلاسيكي
try:
    from classical_analysis import render_classical_analysis
except ImportError:
    def render_classical_analysis(s): st.warning("⚠️ ملف classical_analysis.py مفقود.")

# 5. محرك الذكاء الاصطناعي (AI Engine)
try:
    from ai_engine import generate_ai_report, calculate_portfolio_risk_score, run_stress_test, generate_rebalancing_suggestions
except ImportError:
    def generate_ai_report(s): return {} # يرجع قاموس فارغ ليتم التعامل معه
    def calculate_portfolio_risk_score(df, c): return 50
    def run_stress_test(v, df): return {"scenarios": [], "insight": ""}
    def generate_rebalancing_suggestions(df, c): return []

# ========================================================
# 1. شريط التنقل (Navigation)
# ========================================================
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
            # تمييز الزر النشط
            is_active = st.session_state.page == key
            if st.button(label, key=f"nav_{key}", type="primary" if is_active else "secondary"):
                st.session_state.page = key
                st.rerun()
                
    with cols[-1]:
        with st.popover("👤 القائمة"):
            st.write(f"مرحباً, {st.session_state.get('username', 'Guest')}")
            if st.button("➕ إضافة صفقة", key="nav_add"): st.session_state.page='add'; st.rerun()
            if st.button("⚙️ إعدادات", key="nav_set"): st.session_state.page='settings'; st.rerun()
            st.divider()
            if st.button("🚪 خروج", key="nav_logout"):
                try: from security import logout; logout()
                except: st.session_state.clear(); st.rerun()

# ========================================================
# 2. لوحة القيادة (Dashboard)
# ========================================================
def view_dashboard(fin):
    try: tp, tc = get_tasi_data()
    except: tp, tc = 0, 0
    ar = "🔼" if tc >= 0 else "🔽"
    clr = "#4caf50" if tc >= 0 else "#f44336"

    # التحليل الذكي للمحفظة
    df = fin['all_trades']
    total_assets = fin['market_val_open'] + fin['cash']
    cash_pct = (fin['cash'] / total_assets * 100) if total_assets else 0
    
    # 1. بطاقة تاسي والمخاطرة
    c_tasi, c_risk = st.columns([3, 1])
    with c_tasi:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); padding: 20px; border-radius: 15px; color: white; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div>
                <div style="font-size: 0.9rem; opacity: 0.8;">المؤشر العام (TASI)</div>
                <div style="font-size: 2.2rem; font-weight: bold;">{safe_fmt(tp)}</div>
            </div>
            <div style="background: rgba(255,255,255,0.2); padding: 5px 15px; border-radius: 20px; font-weight: bold; font-size: 1.2rem;">
                {ar} {tc:.2f}%
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with c_risk:
        risk_score = calculate_portfolio_risk_score(df, cash_pct)
        r_col = "success" if risk_score < 40 else "warning" if risk_score < 70 else "danger"
        render_kpi("مستوى المخاطرة", f"{risk_score}/100", r_col, "🛡️")

    # 2. تنبيهات الذكاء الاصطناعي
    ai_suggestions = generate_rebalancing_suggestions(df, cash_pct)
    if ai_suggestions:
        with st.expander(f"📢 تنبيهات المستشار الذكي ({len(ai_suggestions)})", expanded=True):
            for level, msg in ai_suggestions:
                if level == 'priority': st.error(msg, icon="🚨")
                elif level == 'warning': st.warning(msg, icon="⚠️")
                elif level == 'success': st.success(msg, icon="✅")
                else: st.info(msg, icon="ℹ️")

    st.divider()

    # 3. الملخص المالي
    c1, c2, c3, c4 = st.columns(4)
    total_pl = fin['unrealized_pl'] + fin['realized_pl']
    with c1: render_kpi(f"الكاش المتوفر ({cash_pct:.1f}%)", safe_fmt(fin['cash']), "blue", "💵")
    with c2: render_kpi("صافي الإيداعات", safe_fmt(fin['total_deposited'] - fin['total_withdrawn']), "neutral", "🏦")
    with c3: render_kpi("قيمة الأصول الحالية", safe_fmt(fin['market_val_open']), "neutral", "📊")
    with c4: render_kpi("الربح الكلي (المحقق+الورقي)", safe_fmt(total_pl), 'success' if total_pl>=0 else 'danger', "💰")

    # 4. الرسوم البيانية
    if not df.empty:
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.subheader("توزيع الأصول")
            try:
                open_trades = df[df['status'] == 'Open']
                invest_val = open_trades[open_trades['strategy'].astype(str).str.contains('استثمار', na=False)]['market_value'].sum()
                spec_val = open_trades[open_trades['strategy'].astype(str).str.contains('مضاربة', na=False)]['market_value'].sum()
                sukuk_val = open_trades[open_trades['asset_type'] == 'Sukuk']['market_value'].sum()
                
                alloc_data = {'Asset': ['استثمار', 'مضاربة', 'صكوك', 'كاش'], 
                              'Value': [invest_val, spec_val, sukuk_val, fin['cash']]}
                fig = px.pie(alloc_data, values='Value', names='Asset', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.update_layout(height=300, margin=dict(t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
            except: st.info("جاري تجميع البيانات...")

        with col_chart2:
            st.subheader("نمو المحفظة")
            curve = generate_equity_curve(df)
            if not curve.empty:
                fig2 = px.line(curve, x='date', y='cumulative_invested', title='')
                fig2.update_traces(line_color='#2ecc71', line_width=3)
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("لا توجد بيانات تاريخية كافية للرسم.")
    else:
        st.info("ابدأ بإضافة صفقات لتظهر التحليلات هنا.")

# ========================================================
# 3. عرض المحفظة (Portfolio View)
# ========================================================
def view_portfolio(fin, key):
    ts = "مضاربة" if key == 'spec' else "استثمار"
    st.header(f"💼 محفظة ال{ts}")
    
    df = fin['all_trades']
    if df.empty:
        st.info("لا توجد صفقات.")
        return

    # فلترة حسب الاستراتيجية
    sub = df[df['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    op = sub[sub['status'] == 'Open'].copy()
    cl = sub[sub['status'] == 'Close'].copy()

    tab1, tab2 = st.tabs(["📌 الصفقات القائمة", "🗄️ الأرشيف المغلق"])

    with tab1:
        if not op.empty:
            # مؤشرات سريعة
            tot_cost = op['total_cost'].sum()
            tot_val = op['market_value'].sum()
            tot_gain = op['gain'].sum()
            k1, k2, k3 = st.columns(3)
            with k1: render_kpi("التكلفة", safe_fmt(tot_cost), "neutral")
            with k2: render_kpi("القيمة السوقية", safe_fmt(tot_val), "blue")
            with k3: render_kpi("الربح/الخسارة", safe_fmt(tot_gain), "success" if tot_gain>=0 else "danger")
            
            st.divider()
            
            # جلب البيانات الحية
            live_data = fetch_batch_data(op['symbol'].unique().tolist())
            
            # تحديث البيانات للعرض
            op['prev_close'] = op['symbol'].apply(lambda x: live_data.get(x, {}).get('prev_close', 0))
            op['day_change'] = op.apply(lambda r: ((r['current_price'] - r['prev_close']) / r['prev_close'] * 100) if r['prev_close'] > 0 else 0, axis=1)
            op['status_ar'] = "مفتوحة"

            # الجدول
            cols = [
                ('company_name', 'الشركة', 'text'), 
                ('symbol', 'الرمز', 'text'),
                ('quantity', 'الكمية', 'money'), 
                ('entry_price', 'متوسط التكلفة', 'money'),
                ('current_price', 'السعر الحالي', 'money'),
                ('day_change', 'التغير اليومي', 'percent'),
                ('gain', 'الربح/الخسارة', 'colorful'),
                ('gain_pct', 'النسبة %', 'percent')
            ]
            render_custom_table(op, cols)

            # أدوات التحكم (بيع / تعديل)
            c_act1, c_act2 = st.columns(2)
            with c_act1:
                with st.expander("🔴 إغلاق صفقة (بيع)"):
                    opts = {f"{r['company_name']} ({r['quantity']})": r['id'] for _, r in op.iterrows()}
                    sel = st.selectbox("اختر الصفقة", list(opts.keys()), key=f"sel_sell_{key}")
                    if sel:
                        tid = opts[sel]
                        with st.form(f"sell_{tid}"):
                            p = st.number_input("سعر البيع", min_value=0.0)
                            d = st.date_input("تاريخ البيع", date.today())
                            if st.form_submit_button("تنفيذ البيع"):
                                execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s", (p, str(d), tid))
                                st.success("تم البيع!"); st.cache_data.clear(); st.rerun()
            
            with c_act2:
                with st.expander("✏️ تعديل صفقة"):
                    opts_e = {f"{r['company_name']} - {r['date']}": r['id'] for _, r in op.iterrows()}
                    sel_e = st.selectbox("اختر للتعديل", list(opts_e.keys()), key=f"sel_edit_{key}")
                    if sel_e:
                        tid = opts_e[sel_e]
                        curr = op[op['id'] == tid].iloc[0]
                        with st.form(f"edit_{tid}"):
                            nq = st.number_input("الكمية", value=float(curr['quantity']))
                            np = st.number_input("سعر الشراء", value=float(curr['entry_price']))
                            nd = st.date_input("التاريخ", pd.to_datetime(curr['date']))
                            if st.form_submit_button("حفظ التعديل"):
                                execute_query("UPDATE Trades SET quantity=%s, entry_price=%s, date=%s WHERE id=%s", (nq, np, str(nd), tid))
                                st.success("تم التعديل!"); st.cache_data.clear(); st.rerun()

        else:
            st.info("لا توجد صفقات مفتوحة في هذه المحفظة.")

    with tab2:
        if not cl.empty:
            render_custom_table(cl, [('company_name','الشركة','text'), ('gain','الربح المحقق','colorful'), ('exit_date','تاريخ الخروج','date')])
        else:
            st.info("الأرشيف فارغ.")

# ========================================================
# 4. محفظة الصكوك
# ========================================================
def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك والعوائد الثابتة")
    df = fin['all_trades']
    sukuk = df[df['asset_type'] == 'Sukuk'].copy() if not df.empty else pd.DataFrame()
    
    if sukuk.empty:
        st.warning("لم تقم بإضافة أي صكوك بعد.")
        if st.button("➕ إضافة صك جديد"): st.session_state.page='add'; st.rerun()
        return

    op = sukuk[sukuk['status'] == 'Open']
    
    if not op.empty:
        # عرض الصكوك
        total_inv = op['total_cost'].sum()
        st.metric("إجمالي الاستثمار في الصكوك", safe_fmt(total_inv))
        
        cols = [('company_name', 'اسم الصك', 'text'), ('quantity', 'العدد', 'text'), 
                ('entry_price', 'قيمة الصك', 'money'), ('total_cost', 'الإجمالي', 'money'), ('date', 'تاريخ الشراء', 'date')]
        render_custom_table(op, cols)
        
        # خيار التصفية
        with st.expander("استرداد / بيع صك"):
            opts = {f"{r['company_name']}": r['id'] for _, r in op.iterrows()}
            s = st.selectbox("اختر الصك", list(opts.keys()))
            if s:
                tid = opts[s]
                with st.form(f"sukuk_{tid}"):
                    val = st.number_input("المبلغ المسترد كاملاً")
                    dt = st.date_input("تاريخ الاسترداد")
                    if st.form_submit_button("تأكيد"):
                        # حساب سعر الخروج للوحدة
                        qty = float(op[op['id']==tid].iloc[0]['quantity'])
                        ep = val / qty if qty else 0
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s", (ep, str(dt), tid))
                        st.success("تم"); st.cache_data.clear(); st.rerun()
    else:
        st.info("جميع الصكوك مغلقة.")

# ========================================================
# 5. سجل السيولة (Cash Log)
# ========================================================
def view_cash_log():
    st.header("💰 سجل العمليات المالية")
    fin = calculate_portfolio_metrics()
    
    t1, t2, t3 = st.tabs(["📥 الإيداعات", "📤 السحوبات", "🎁 التوزيعات"])
    
    with t1:
        with st.form("new_dep"):
            a = st.number_input("المبلغ", min_value=0.0)
            d = st.date_input("التاريخ", date.today())
            n = st.text_input("ملاحظة")
            if st.form_submit_button("تسجيل إيداع"):
                execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                st.success("تم"); st.cache_data.clear(); st.rerun()
        if not fin['deposits'].empty: render_custom_table(fin['deposits'], [('date','التاريخ','date'),('amount','المبلغ','money'),('note','ملاحظة','text')])

    with t2:
        with st.form("new_wit"):
            a = st.number_input("المبلغ", min_value=0.0)
            d = st.date_input("التاريخ", date.today())
            n = st.text_input("ملاحظة")
            if st.form_submit_button("تسجيل سحب"):
                execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                st.success("تم"); st.cache_data.clear(); st.rerun()
        if not fin['withdrawals'].empty: render_custom_table(fin['withdrawals'], [('date','التاريخ','date'),('amount','المبلغ','money'),('note','ملاحظة','text')])

    with t3:
        with st.form("new_ret"):
            s = st.text_input("رمز السهم")
            a = st.number_input("مبلغ التوزيع", min_value=0.0)
            d = st.date_input("التاريخ", date.today())
            if st.form_submit_button("تسجيل توزيعات"):
                execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (%s,%s,%s)", (str(d), s, a))
                st.success("تم"); st.cache_data.clear(); st.rerun()
        if not fin['returns'].empty: render_custom_table(fin['returns'], [('date','التاريخ','date'),('symbol','السهم','text'),('amount','المبلغ','money')])

# ========================================================
# 6. التحليل الشامل (Analysis) - تم الإصلاح الجذري هنا 🛠️
# ========================================================
def view_analysis(fin):
    st.header("🔬 التحليل الشامل والمستشار الذكي")
    
    trades = fin['all_trades']
    
    # 1. تحليل المحفظة الكلي
    if not trades.empty:
        open_pos = trades[trades['status']=='Open']
        st.subheader("🛡️ اختبار التحمل (Stress Test)")
        
        stress = run_stress_test(fin['market_val_open'], open_pos)
        if stress.get('scenarios'):
            c_ch, c_tx = st.columns([3, 1])
            with c_ch:
                sdf = pd.DataFrame(stress['scenarios'])
                fig = px.bar(sdf, x='scenario', y='impact_pct', color='scenario', 
                             title="تأثير سيناريوهات السوق على المحفظة",
                             color_discrete_map={row['scenario']: row['color'] for _, row in sdf.iterrows()})
                st.plotly_chart(fig, use_container_width=True)
            with c_tx:
                st.info(stress.get('insight', ''))
        st.divider()

    # 2. التحليل الفردي للسهم
    # تجميع قائمة الأسهم (من المحفظة + المراقبة)
    wl = fetch_table("Watchlist")
    my_stocks = trades['symbol'].unique().tolist() if not trades.empty else []
    wl_stocks = wl['symbol'].unique().tolist() if not wl.empty else []
    all_stocks = list(set(my_stocks + wl_stocks))
    
    c_sel1, c_sel2 = st.columns([2, 1])
    search_sym = c_sel2.text_input("بحث عن رمز جديد")
    
    options = [search_sym] + all_stocks if search_sym else all_stocks
    selected_sym = c_sel1.selectbox("اختر الشركة للتحليل:", options) if options else None
    
    if selected_sym:
        nm, sc = get_company_details(selected_sym)
        st.markdown(f"## {nm} ({selected_sym}) - {sc}")
        
        # التبويبات الفرعية
        at1, at2, at3, at4, at5 = st.tabs(["🤖 المستشار", "💰 القوائم المالية", "📈 الشارت الفني", "🏛️ كلاسيكي", "📝 ملاحظاتي"])
        
        # أ. المستشار الذكي (مع الحماية من KeyError)
        with at1:
            with st.spinner("جاري تحليل البيانات..."):
                report = generate_ai_report(selected_sym)
            
            # استخراج البيانات بأمان باستخدام .get()
            rec_text = report.get('recommendation', 'غير متوفر')
            rec_color = report.get('color', '#6c757d') # رمادي افتراضي في حال عدم وجود لون
            rec_strat = report.get('strategy', 'لا توجد بيانات كافية للتحليل')
            
            # عرض النتيجة
            st.markdown(f"""
            <div style="text-align:center; padding: 20px; background-color: #f8f9fa; border-radius: 15px; border: 2px solid {rec_color}; margin-bottom: 20px;">
                <h2 style="color: {rec_color}; margin:0;">{rec_text}</h2>
                <p style="color: #333; margin-top:10px; font-size:1.1rem;">{rec_strat}</p>
            </div>
            """, unsafe_allow_html=True)
            
            col_t, col_f = st.columns(2)
            with col_t:
                st.markdown("##### 📐 الرؤية الفنية")
                for r in report.get('tech_reasons', []): st.write(f"• {r}")
            with col_f:
                st.markdown("##### 📊 الرؤية المالية")
                for r in report.get('fund_reasons', []): st.write(f"• {r}")

        # ب. المالي
        with at2: render_financial_dashboard_ui(selected_sym)
        
        # ج. الفني
        with at3: render_technical_chart(selected_sym)
        
        # د. الكلاسيكي
        with at4: render_classical_analysis(selected_sym)
        
        # هـ. الأطروحة
        with at5:
            thesis = get_thesis(selected_sym)
            old_txt = thesis['thesis_text'] if thesis else ""
            with st.form("th_form"):
                new_txt = st.text_area("اكتب تحليلك الخاص أو ملاحظاتك هنا:", value=old_txt, height=200)
                if st.form_submit_button("حفظ الملاحظات"):
                    save_thesis(selected_sym, new_txt, 0, "Hold")
                    st.success("تم الحفظ")

# ========================================================
# 7. المختبر (Backtester)
# ========================================================
def view_backtester_ui(fin):
    st.header("🧪 مختبر الاستراتيجيات")
    if not run_backtest:
        st.error("⚠️ وحدة الاختبار غير متوفرة. تأكد من وجود الملف backtester.py")
        return

    # قائمة الأسهم
    all_syms = fin['all_trades']['symbol'].unique().tolist()
    if "1120.SR" not in all_syms: all_syms.append("1120.SR")
    
    c1, c2, c3 = st.columns(3)
    s = c1.selectbox("السهم للاختبار", all_syms)
    strat = c2.selectbox("الاستراتيجية", ["Trend Follower", "Sniper", "RSI Reversal"])
    amount = c3.number_input("رأس المال الافتراضي", 100000, step=5000)
    
    if st.button("🚀 تشغيل المحاكاة"):
        with st.spinner("جاري العودة بالزمن واختبار البيانات..."):
            hist = get_chart_history(s, period="2y") # سنتين
            res = run_backtest(hist, strat, amount)
            
            if res:
                st.success("اكتمل الاختبار!")
                m1, m2, m3 = st.columns(3)
                ret_col = "success" if res['return_pct'] > 0 else "danger"
                m1.metric("العائد النهائي", f"{res['return_pct']:.2f}%")
                m2.metric("القيمة النهائية", f"{res['final_value']:,.2f}")
                m3.metric("عدد الصفقات", len(res['trades_log']))
                
                st.line_chart(res['df']['Portfolio_Value'])
                with st.expander("سجل الصفقات الافتراضية"):
                    st.dataframe(res['trades_log'])
            else:
                st.error("فشل الاختبار. قد لا تتوفر بيانات تاريخية كافية.")

# ========================================================
# 8. نبض السوق وإضافة صفقة والإعدادات
# ========================================================
def render_pulse_dashboard():
    st.header("💓 نبض السوق (قائمة المراقبة)")
    # جلب الأسهم من Watchlist + المحفظة
    wl = fetch_table("Watchlist")
    trades = fetch_table("Trades")
    syms = list(set(wl['symbol'].tolist() + trades['symbol'].tolist()))
    
    if not syms:
        st.info("القائمة فارغة.")
        return
        
    data = fetch_batch_data(syms)
    
    # عرض بشكل شبكة
    cols = st.columns(4)
    for i, (sym, info) in enumerate(data.items()):
        chg = ((info['price'] - info['prev_close'])/info['prev_close']*100) if info['prev_close'] else 0
        with cols[i % 4]:
            render_ticker_card(sym, "سهم", info['price'], chg)

def view_add_trade():
    st.header("➕ تسجيل عملية جديدة")
    with st.form("add_t"):
        c1, c2 = st.columns(2)
        s = c1.text_input("رمز السهم (مثال: 1120)")
        typ = c2.selectbox("تصنيف الصفقة", ["استثمار", "مضاربة", "صكوك"])
        
        c3, c4, c5 = st.columns(3)
        qty = c3.number_input("الكمية", min_value=1.0)
        price = c4.number_input("سعر الشراء", min_value=0.0)
        dt = c5.date_input("التاريخ", date.today())
        
        if st.form_submit_button("✅ حفظ العملية"):
            if not s or qty <= 0 or price <= 0:
                st.error("الرجاء إدخال بيانات صحيحة")
            else:
                # جلب اسم الشركة آلياً
                nm, sec = get_company_details(s)
                asset_t = "Sukuk" if typ == "صكوك" else "Stock"
                
                execute_query(
                    "INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Open')",
                    (s, nm, sec, asset_t, str(dt), qty, price, typ)
                )
                st.success(f"تمت إضافة {nm} بنجاح!")
                st.session_state.page = 'home'
                st.cache_data.clear()
                st.rerun()

def view_settings():
    st.header("⚙️ الإعدادات والنظام")
    
    st.subheader("📦 النسخ الاحتياطي")
    if st.button("تحميل نسخة من بياناتي (Excel)"):
        data, name = create_smart_backup()
        if data:
            st.download_button("📥 تنزيل الملف", data, name, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.success("جاهز للتنزيل")

# ========================================================
# 9. الموجه الرئيسي (Router)
# ========================================================
def router():
    if 'page' not in st.session_state: st.session_state.page = 'home'
    
    render_navbar()
    
    pg = st.session_state.page
    fin = calculate_portfolio_metrics() # حسابات مركزية مرة واحدة
    
    if pg == 'home': view_dashboard(fin)
    elif pg == 'spec': view_portfolio(fin, 'spec')
    elif pg == 'invest': view_portfolio(fin, 'invest')
    elif pg == 'sukuk': view_sukuk_portfolio(fin)
    elif pg == 'cash': view_cash_log()
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'backtest': view_backtester_ui(fin)
    elif pg == 'pulse': render_pulse_dashboard()
    elif pg == 'add': view_add_trade()
    elif pg == 'settings': view_settings()
    elif pg == 'update':
        with st.spinner("جاري تحديث الأسعار من السوق..."):
            update_prices()
        st.success("تم التحديث!")
        st.session_state.page = 'home'
        st.rerun()

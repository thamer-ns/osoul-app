import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from config import DEFAULT_COLORS
from components import render_kpi, render_custom_table, render_ticker_card, safe_fmt
from analytics import calculate_portfolio_metrics, update_prices, generate_equity_curve
from database import execute_query, fetch_table
from market_data import get_static_info, get_tasi_data, get_chart_history, fetch_batch_data
from charts import render_technical_chart
from backtester import run_backtest
from financial_analysis import render_financial_dashboard_ui, get_fundamental_ratios, get_thesis, save_thesis
from classical_analysis import render_classical_analysis
from data_source import get_company_details

def render_navbar():
    buttons = [
        ('🏠 الرئيسية','home'), ('⚡ مضاربة','spec'), ('💎 استثمار','invest'), 
        ('💓 نبض','pulse'), ('📜 صكوك','sukuk'), ('🔍 تحليل','analysis'), 
        ('🧪 المختبر','backtest'), ('💰 السيولة','cash'), ('🔄 تحديث','update')
    ]
    cols = st.columns(len(buttons) + 1)
    for i, (label, key) in enumerate(buttons):
        with cols[i]:
            type_btn = "primary" if st.session_state.page == key else "secondary"
            if st.button(label, key=f"nav_{key}", use_container_width=True, type=type_btn): 
                st.session_state.page = key; st.rerun()
    with cols[-1]:
        with st.popover("👤 القائمة", use_container_width=True):
            if st.button("➕ إضافة صفقة", use_container_width=True): st.session_state.page='add'; st.rerun()
            if st.button("⚙️ الإعدادات", use_container_width=True): st.session_state.page='settings'; st.rerun()
            st.markdown("---")
            if st.button("🚪 خروج", use_container_width=True): 
                try: from security import logout; logout()
                except: st.session_state.clear(); st.rerun()
    st.markdown("---")

def view_dashboard(fin):
    try: tp, tc = get_tasi_data()
    except: tp, tc = 0, 0
    ar = "🔼" if tc >= 0 else "🔽"
    st.markdown(f"""<div class="tasi-card"><div><div style="opacity:0.9;">TASI</div><div style="font-size:2rem; font-weight:900;">{safe_fmt(tp)}</div></div><div style="background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:10px; font-weight:bold; direction:ltr;">{ar} {tc:.2f}%</div></div>""", unsafe_allow_html=True)
    
    c1, c2, c3, c4 = st.columns(4)
    total_pl = fin['unrealized_pl'] + fin['realized_pl']
    total_assets = fin['market_val_open'] + fin['cash']
    cash_pct = (fin['cash'] / total_assets * 100) if total_assets else 0
    with c1: render_kpi(f"الكاش ({cash_pct:.1f}%)", safe_fmt(fin['cash']), "blue", "💵")
    with c2: render_kpi("صافي الإيداعات", safe_fmt(fin['total_deposited']-fin['total_withdrawn']), "neutral", "🏗️")
    with c3: render_kpi("الأصول", safe_fmt(total_assets), "neutral", "🏦")
    with c4: render_kpi("الربح الكلي", safe_fmt(total_pl), 'success' if total_pl>=0 else 'danger', "📈")
    
    st.markdown("---")
    df = fin['all_trades']
    st.markdown("##### 📊 صفقات مفتوحة")
    o1,o2,o3,o4 = st.columns(4)
    with o1: render_kpi("التكلفة", safe_fmt(fin['cost_open']), "neutral", "💰")
    with o2: render_kpi("القيمة السوقية", safe_fmt(fin['market_val_open']), "blue", "📊")
    with o3: render_kpi("الربح الورقي", safe_fmt(fin['unrealized_pl']), "success" if fin['unrealized_pl']>=0 else "danger", "📈")
    op_pct = (fin['unrealized_pl']/fin['cost_open']*100) if fin['cost_open'] else 0
    with o4: render_kpi("النمو", f"{op_pct:.2f}%", "success" if op_pct>=0 else "danger", "٪")

    st.markdown("<div style='margin-bottom: 25px;'></div>##### 📜 صفقات مغلقة", unsafe_allow_html=True)
    if not df.empty:
        closed = df[df['status'] == 'Close']
        cc = closed['total_cost'].sum(); cpl = fin['realized_pl']; cpct = (cpl/cc*100) if cc else 0
    else: cc=cpl=cpct=0
    x1,x2,x3 = st.columns(3)
    with x1: render_kpi("رأس المال المسترد", safe_fmt(cc), "neutral", "↩️")
    with x2: render_kpi("الربح المحقق", safe_fmt(cpl), "success" if cpl>=0 else "danger", "✅")
    with x3: render_kpi("العائد", f"{cpct:.2f}%", "success" if cpct>=0 else "danger", "٪")
    
    st.markdown("---")
    if not df.empty:
        op = df[df['status'] == 'Open']
        inv = op[op['strategy'].str.contains('استثمار', na=False)]['market_value'].sum()
        spc = op[op['strategy'].str.contains('مضاربة', na=False)]['market_value'].sum()
        suk = op[op['asset_type'] == 'Sukuk']['market_value'].sum()
        adf = pd.DataFrame({'A':['استثمار','مضاربة','صكوك','كاش'], 'V':[inv,spc,suk,fin['cash']]})
        adf = adf[adf['V']>0]
        c1, c2 = st.columns(2)
        with c1: st.subheader("توزيع الأصول"); fig=px.pie(adf, values='V', names='A', hole=0.4); st.plotly_chart(fig, use_container_width=True)
        with c2: st.subheader("النمو"); crv=generate_equity_curve(df); st.plotly_chart(px.line(crv, x='date', y='cumulative_invested'), use_container_width=True)

def view_portfolio(fin, key):
    ts = "مضاربة" if key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    st.markdown("<style>.finance-table td{white-space:nowrap;font-size:0.85rem;}</style>", unsafe_allow_html=True)
    df = fin['all_trades']
    sub = df[df['strategy'].str.contains(ts, na=False)].copy() if not df.empty else pd.DataFrame()
    op = sub[sub['status'] == 'Open'].copy(); cl = sub[sub['status'] == 'Close'].copy()
    
    t1, t2 = st.tabs(["الصفقات القائمة", "الأرشيف"])
    with t1:
        if not op.empty:
            live = fetch_batch_data(op['symbol'].unique().tolist())
            op['prev_close'] = op['symbol'].apply(lambda x: live.get(x,{}).get('prev_close',0))
            op['day_change'] = op.apply(lambda r: ((r['current_price']-r['prev_close'])/r['prev_close']*100) if r['prev_close']>0 else 0, axis=1)
            op['weight'] = (op['market_value']/op['market_value'].sum()*100).fillna(0)
            
            cols = [('company_name','الشركة','text'),('symbol','الرمز','text'),('date','تاريخ','date'),
                    ('quantity','الكمية','money'),('entry_price','شراء','money'),('current_price','حالي','money'),
                    ('market_value','سوقية','money'),('gain','ربح','colorful'),('gain_pct','%','percent'),
                    ('day_change','يومي %','percent'),('weight','وزن','percent')]
            render_custom_table(op, cols)
            
            c1, c2 = st.columns(2)
            with c1:
                with st.expander("💰 بيع"):
                    opts = {f"{r['company_name']} ({r['quantity']})": r['id'] for _,r in op.iterrows()}
                    sel = st.selectbox("اختر", list(opts.keys()), key=f"s_{key}")
                    if sel:
                        tid = opts[sel]; curr = op[op['id']==tid].iloc[0]
                        with st.form(f"frm_{tid}"):
                            p = st.number_input("سعر البيع", value=float(curr['current_price']))
                            d = st.date_input("تاريخ", date.today())
                            if st.form_submit_button("تأكيد"):
                                execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s", (p,str(d),tid))
                                st.success("تم"); st.cache_data.clear(); st.rerun()
            with c2:
                with st.expander("✏️ تعديل"):
                    opts = {f"{r['company_name']} - {r['date']}": r['id'] for _,r in op.iterrows()}
                    sel = st.selectbox("اختر", list(opts.keys()), key=f"e_{key}")
                    if sel:
                        tid = opts[sel]; curr = op[op['id']==tid].iloc[0]
                        with st.form(f"edit_{tid}"):
                            nq = st.number_input("الكمية", value=float(curr['quantity']))
                            np = st.number_input("سعر الشراء", value=float(curr['entry_price']))
                            nd = st.date_input("التاريخ", pd.to_datetime(curr['date']))
                            if st.form_submit_button("حفظ"):
                                execute_query("UPDATE Trades SET quantity=%s, entry_price=%s, date=%s WHERE id=%s", (nq,np,str(nd),tid))
                                st.success("تم"); st.cache_data.clear(); st.rerun()
        else: st.info("فارغة")
    with t2:
        if not cl.empty:
            render_custom_table(cl, [('company_name','الشركة','text'),('gain','الربح','colorful'),('gain_pct','%','percent'),('exit_date','تاريخ البيع','date')])
        else: st.info("فارغة")

def view_sukuk_portfolio(fin):
    st.header("📜 صكوك")
    df = fin['all_trades']; sukuk = df[df['asset_type'] == 'Sukuk'].copy() if not df.empty else pd.DataFrame()
    
    c_add, _ = st.columns([1,4])
    with c_add: 
        if st.button("➕ إضافة صك", type="primary"): st.session_state.page='add'; st.rerun()

    if not sukuk.empty:
        sukuk['company_name'] = sukuk['company_name'].fillna(sukuk['symbol'])
        render_custom_table(sukuk, [('company_name','الاسم','text'),('quantity','العدد','money'),('entry_price','سعر','money'),('total_cost','اجمالي','money'),('gain','ربح','colorful')])
        
        c1, c2 = st.columns(2)
        with c1:
            with st.expander("💰 استرداد"):
                opts = {f"{r['company_name']}": r['id'] for _,r in sukuk.iterrows()}
                sel = st.selectbox("اختر", list(opts.keys()))
                if sel:
                    tid = opts[sel]; curr = sukuk[sukuk['id']==tid].iloc[0]
                    with st.form(f"s_{tid}"):
                        tot = st.number_input("المبلغ المستلم كاملاً")
                        d = st.date_input("تاريخ")
                        if st.form_submit_button("تأكيد"):
                            ep = tot/float(curr['quantity']) if float(curr['quantity'])>0 else 0
                            execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s", (ep,str(d),tid))
                            st.success("تم"); st.cache_data.clear(); st.rerun()
        with c2:
            with st.expander("✏️ تعديل"):
                opts = {f"{r['company_name']}": r['id'] for _,r in sukuk.iterrows()}
                sel = st.selectbox("اختر", list(opts.keys()), key="es")
                if sel:
                    tid = opts[sel]; curr = sukuk[sukuk['id']==tid].iloc[0]
                    with st.form(f"e_{tid}"):
                        nm = st.text_input("الاسم", value=curr['company_name'])
                        q = st.number_input("العدد", value=float(curr['quantity']))
                        p = st.number_input("سعر", value=float(curr['entry_price']))
                        if st.form_submit_button("حفظ"):
                            execute_query("UPDATE Trades SET symbol=%s, company_name=%s, quantity=%s, entry_price=%s WHERE id=%s", (nm,nm,q,p,tid))
                            st.success("تم"); st.cache_data.clear(); st.rerun()

def view_cash_log():
    st.header("💰 السيولة"); fin = calculate_portfolio_metrics()
    d, w, r = fin['deposits'], fin['withdrawals'], fin['returns']
    c1,c2,c3 = st.columns(3)
    with c1: render_kpi("إيداع", safe_fmt(d['amount'].sum()), "success", "📥")
    with c2: render_kpi("سحب", safe_fmt(w['amount'].sum()), "danger", "📤")
    with c3: render_kpi("عوائد", safe_fmt(r['amount'].sum()), "blue", "🎁")
    
    t1,t2,t3 = st.tabs(["إيداع","سحب","عوائد"])
    cols = [('date','تاريخ','date'),('amount','مبلغ','money'),('note','ملاحظة','text')]
    with t1:
        with st.form("d"): 
            a=st.number_input("مبلغ"); dt=st.date_input("تاريخ"); n=st.text_input("ملاحظة")
            if st.form_submit_button("حفظ"): execute_query("INSERT INTO Deposits (date,amount,note) VALUES (%s,%s,%s)",(str(dt),a,n)); st.rerun()
        render_custom_table(d.sort_values('date',False), cols)
    with t2:
        with st.form("w"): 
            a=st.number_input("مبلغ"); dt=st.date_input("تاريخ"); n=st.text_input("ملاحظة")
            if st.form_submit_button("حفظ"): execute_query("INSERT INTO Withdrawals (date,amount,note) VALUES (%s,%s,%s)",(str(dt),a,n)); st.rerun()
        render_custom_table(w.sort_values('date',False), cols)
    with t3:
        with st.form("r"): 
            s=st.text_input("رمز"); a=st.number_input("مبلغ"); dt=st.date_input("تاريخ"); n=st.text_input("ملاحظة")
            if st.form_submit_button("حفظ"): execute_query("INSERT INTO ReturnsGrants (date,symbol,amount,note) VALUES (%s,%s,%s,%s)",(str(dt),s,a,n)); st.rerun()
        render_custom_table(r.sort_values('date',False), cols)

def view_analysis(fin):
    st.header("🔬 تحليل"); wl = fetch_table("Watchlist"); trades = fin['all_trades']
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist()))
    c1,c2=st.columns([1,2]); ns=c1.text_input("بحث"); s=c2.selectbox("سهم", [ns]+syms if ns else syms) if syms or ns else None
    if s:
        n, sec = get_static_info(s); st.markdown(f"### {n} ({s})")
        t1,t2,t3,t4,t5 = st.tabs(["مؤشرات","فني","قوائم","كلاسيكي","أطروحة"])
        with t1: d=get_fundamental_ratios(s); st.metric("التقييم",f"{d['Score']}/10",d['Rating']); st.write(d)
        with t2: render_technical_chart(s)
        with t3: render_financial_dashboard_ui(s)
        with t4: render_classical_analysis(s)
        with t5: 
            th=get_thesis(s); txt=th['thesis_text'] if th is not None else ""; tgt=th['target_price'] if th is not None else 0.0
            with st.form("th"):
                nt=st.text_area("نص",value=txt); ng=st.number_input("هدف",value=float(tgt))
                if st.form_submit_button("حفظ"): save_thesis(s,nt,ng,""); st.success("تم")

def view_backtester_ui(fin):
    st.header("🧪 مختبر"); sym = st.selectbox("سهم", ["1120.SR"]+fin['all_trades']['symbol'].unique().tolist())
    if st.button("بدء"):
        res = run_backtest(get_chart_history(sym,"2y"), "Trend Follower", 100000)
        if res: st.metric("عائد", f"{res['return_pct']:.2f}%"); st.line_chart(res['df']['Portfolio_Value'])

def render_pulse_dashboard():
    st.header("💓 نبض"); wl = fetch_table("Watchlist")
    nw = st.text_input("اضافة للمراقبة"); 
    if st.button("اضافة") and nw: execute_query("INSERT INTO Watchlist (symbol) VALUES (%s) ON CONFLICT DO NOTHING",(nw,)); st.rerun()
    syms = list(set(fetch_table("Trades")['symbol'].unique().tolist() + wl['symbol'].unique().tolist()))
    if syms:
        d = fetch_batch_data(syms); cols = st.columns(4)
        for i,(s,inf) in enumerate(d.items()):
            ch = ((inf['price']-inf['prev_close'])/inf['prev_close']*100) if inf['prev_close']>0 else 0
            with cols[i%4]: render_ticker_card(s, get_static_info(s)[0], inf['price'], ch)

def view_add_trade():
    st.header("➕ إضافة صفقة"); 
    with st.form("add"):
        c1,c2=st.columns(2); s=c1.text_input("رمز (مثال 1120)"); t=c2.selectbox("نوع",["استثمار","مضاربة","صكوك"])
        c3,c4,c5=st.columns(3); q=c3.number_input("كمية"); p=c4.number_input("سعر"); d=c5.date_input("تاريخ")
        if st.form_submit_button("حفظ"):
            at = "Sukuk" if t=="صكوك" else "Stock"; nm, sec = get_company_details(s)
            execute_query("INSERT INTO Trades (symbol,company_name,sector,asset_type,date,quantity,entry_price,strategy,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Open')", (s,nm,sec,at,str(d),q,p,t))
            st.success("تم"); st.cache_data.clear()

def view_settings():
    st.header("⚙️ إعدادات"); 
    if st.button("تحديث بيانات الشركات القديمة"):
        df=fetch_table("Trades"); c=0
        for _,r in df.iterrows():
            if not r['company_name'] or r['company_name']=='None':
                n,s=get_company_details(r['symbol']); execute_query("UPDATE Trades SET company_name=%s, sector=%s WHERE id=%s",(n,s,r['id'])); c+=1
        st.success(f"تم {c}")

def router():
    render_navbar(); pg=st.session_state.page; fin=calculate_portfolio_metrics()
    if pg=='home': view_dashboard(fin)
    elif pg=='pulse': render_pulse_dashboard()
    elif pg in ['spec','invest']: view_portfolio(fin, pg)
    elif pg=='sukuk': view_sukuk_portfolio(fin)
    elif pg=='cash': view_cash_log()
    elif pg=='analysis': view_analysis(fin)
    elif pg=='backtest': view_backtester_ui(fin)
    elif pg=='settings': view_settings()
    elif pg=='add': view_add_trade()
    elif pg=='update': update_prices(); st.session_state.page='home'; st.rerun()

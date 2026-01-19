# تأكد أن دالة router في views.py تشبه هذا الشكل:

def router():
    render_navbar() # سيقوم برسم الهيدر الجديد
    
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    
    if pg == 'home': view_dashboard(fin)
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'sukuk': view_sukuk_portfolio(fin)
    elif pg == 'cash': view_liquidity()
    elif pg == 'analysis': view_analysis(fin)
    
    # هذه الصفحات تأتي الآن من قائمة المستخدم
    elif pg == 'tools': view_tools()
    elif pg == 'add': view_add_trade()
    elif pg == 'settings': view_settings()
    
    elif pg == 'update':
        with st.spinner("جاري تحديث الأسعار من السوق..."): update_prices()
        st.session_state.page = 'home'; st.rerun()

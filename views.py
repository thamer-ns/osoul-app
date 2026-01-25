import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time

# استيراد دالة الاتصال بقاعدة البيانات (يفترض أنها معدلة للاتصال السحابي)
# تأكد أن get_db في ملف db.py تعيد اتصالاً صالحاً للقاعدة السحابية
from db import get_db, run_query, run_command  # Assuming you have helper functions for cloud DB

# --- Constants & Themes ---
PRESET_THEMES = {
    "افتراضي (فاتح)": {"base": "light", "primary": "#1f77b4", "bg": "#ffffff", "sec_bg": "#f0f2f6", "text": "#31333F"},
    "داكن (Dark)": {"base": "dark", "primary": "#ff4b4b", "bg": "#0e1117", "sec_bg": "#262730", "text": "#fafafa"},
    "أزرق ليلي": {"base": "dark", "primary": "#00adb5", "bg": "#222831", "sec_bg": "#393e46", "text": "#eeeeee"},
    "صحراوي": {"base": "light", "primary": "#d35400", "bg": "#fdf2e9", "sec_bg": "#fae5d3", "text": "#5d4037"},
}

# --- Helper Functions ---
def enrich_data_frame(df):
    """
    دالة مساعدة لإثراء البيانات بالحسابات الأساسية.
    تستخدم في عدة أماكن في العرض.
    """
    if df.empty:
        return df
    
    # تأكد من تحويل الأعمدة الرقمية
    numeric_cols = ['price', 'quantity', 'cost', 'total_cost', 'market_value']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # حسابات إضافية (الربح، النسبة، إلخ)
    if 'market_value' in df.columns and 'total_cost' in df.columns:
        df['gain'] = df['market_value'] - df['total_cost']
        df['gain_pct'] = (df['gain'] / df['total_cost']) * 100
        df['gain_pct'] = df['gain_pct'].fillna(0)
    
    return df

# --- Views Functions ---

def view_dashboard():
    """
    واجهة لوحة المعلومات (الداشبورد).
    يتم اعتمادها كما هي من ملفك الأصلي.
    """
    st.header("📊 لوحة المعلومات")
    
    # (هنا يمكنك وضع كود الداشبورد الحالي الخاص بك كما هو)
    # نظراً لأنك طلبت تعديل view_settings فقط، سأفترض أن هذا الجزء موجود لديك.
    # إذا كنت بحاجة لإعادة كتابته، يرجى تزويدي بالكود الخاص به.
    st.info("تم تحميل لوحة المعلومات.")
    # ... بقية كود الداشبورد ...


def view_portfolio():
    """
    واجهة المحفظة وتفاصيل الأسهم.
    يتم اعتمادها كما هي.
    """
    st.header("💼 المحفظة الاستثمارية")
    # ... كود المحفظة الخاص بك ...
    st.info("تم تحميل بيانات المحفظة.")


def view_transactions():
    """
    سجل العمليات.
    يتم اعتمادها كما هي.
    """
    st.header("📝 سجل العمليات")
    # ... كود العمليات الخاص بك ...
    st.info("تم تحميل سجل العمليات.")


def view_settings():
    """
    واجهة الإعدادات - تم استبدالها بالكود الجديد المخصص للقاعدة السحابية.
    تتضمن: الثيمات، أهداف القطاعات، قائمة المتابعة، وإدارة البيانات.
    """
    st.header("⚙️ الإعدادات")

    # 1. إدارة الثيمات (Themes)
    st.subheader("🎨 المظهر")
    
    # تهيئة الألوان في session_state إذا لم تكن موجودة
    if "custom_colors" not in st.session_state:
        st.session_state.custom_colors = PRESET_THEMES["افتراضي (فاتح)"].copy()

    selected_theme_name = st.selectbox("اختر نمط الألوان:", list(PRESET_THEMES.keys()))
    
    if st.button("تطبيق الثيم"):
        st.session_state.custom_colors = PRESET_THEMES[selected_theme_name].copy()
        # هنا يمكنك إضافة كود لحفظ الثيم المختار في قاعدة البيانات إذا أردت
        st.toast(f"تم تطبيق ثيم: {selected_theme_name}", icon="🎨")
        time.sleep(0.5)
        st.rerun()

    st.divider()

    # 2. إدارة أهداف القطاعات (Sector Targets)
    st.subheader("🎯 أهداف توزيع القطاعات")
    st.caption("حدد النسبة المستهدفة لكل قطاع (يجب أن يكون المجموع 100%).")

    # جلب البيانات الحالية من قاعدة البيانات السحابية
    # نستخدم try-except لتجنب توقف البرنامج في حال مشاكل الاتصال
    try:
        # استعلام متوافق مع معظم قواعد البيانات (Postgres/MySQL/SQLite)
        query_sectors = "SELECT sector, target_percentage FROM SectorTargets ORDER BY sector"
        with get_db() as conn:
             df_sectors = pd.read_sql(query_sectors, conn)
    except Exception as e:
        st.error(f"خطأ في جلب بيانات القطاعات: {e}")
        df_sectors = pd.DataFrame(columns=['sector', 'target_percentage'])

    if not df_sectors.empty:
        # عرض جدول قابل للتعديل
        edited_df = st.data_editor(
            df_sectors,
            column_config={
                "sector": st.column_config.TextColumn(
                    "القطاع",
                    disabled=True,  # منع تعديل اسم القطاع للحفاظ على البيانات
                    help="اسم القطاع (لا يمكن تعديله هنا)"
                ),
                "target_percentage": st.column_config.NumberColumn(
                    "النسبة المستهدفة %",
                    min_value=0,
                    max_value=100,
                    step=1,
                    format="%.1f %%"
                )
            },
            hide_index=True,
            use_container_width=True,
            key="sector_editor"
        )

        # التحقق من المجموع
        total_target = edited_df['target_percentage'].sum()
        col_sum, col_btn = st.columns([2, 1])
        
        with col_sum:
            if abs(total_target - 100.0) > 0.1:
                st.warning(f"⚠️ مجموع النسب: {total_target:.1f}% (يجب أن يكون 100%)")
            else:
                st.success(f"✅ مجموع النسب: {total_target:.1f}%")

        with col_btn:
            if st.button("حفظ التغييرات", type="primary", disabled=(abs(total_target - 100.0) > 0.1)):
                try:
                    with get_db() as conn:
                        # التحديث في القواعد السحابية يفضل استخدام execute مع parameters
                        for index, row in edited_df.iterrows():
                            # جملة تحديث قياسية (Standard SQL Update)
                            update_sql = "UPDATE SectorTargets SET target_percentage = ? WHERE sector = ?"
                            # ملاحظة: بعض المكتبات تستخدم %s بدلاً من ? (مثل psycopg2 لـ Postgres)
                            # إذا كنت تستخدم Postgres صافي، قد تحتاج لتغيير ? إلى %s في دالة db.py
                            conn.execute(update_sql, (row['target_percentage'], row['sector']))
                            
                        # حفظ (Commit) إذا لم يكن ضمن Context Manager تلقائي
                        if hasattr(conn, 'commit'):
                            conn.commit()
                            
                    st.toast("تم تحديث أهداف المحفظة بنجاح!", icon="💾")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"حدث خطأ أثناء الحفظ: {e}")
    else:
        st.info("لا توجد قطاعات مسجلة حالياً. قم بإضافة صفقات ليتم التعرف على القطاعات.")

    st.divider()

    # 3. قائمة المتابعة (Watchlist)
    with st.expander("⭐ إدارة قائمة المتابعة"):
        col_add, col_btn_add = st.columns([3, 1])
        new_symbol = col_add.text_input("إضافة رمز سهم:", placeholder="مثال: 1120").strip()
        
        if col_btn_add.button("إضافة", key="add_watchlist"):
            if new_symbol:
                try:
                    with get_db() as conn:
                        # استخدام جملة متوافقة مع Cloud DB لتجنب التكرار
                        # في Postgres: INSERT ... ON CONFLICT DO NOTHING
                        # في SQLite: INSERT OR IGNORE
                        # هنا نستخدم Try-Except كحل عام وآمن
                        try:
                            conn.execute("INSERT INTO Watchlist (symbol) VALUES (?)", (new_symbol,))
                            if hasattr(conn, 'commit'): conn.commit()
                            st.success(f"تمت إضافة {new_symbol}")
                        except Exception as insert_err:
                            # غالباً الخطأ سيكون بسبب تكرار المفتاح الأساسي (Duplicate Key)
                            st.warning(f"السهم {new_symbol} موجود مسبقاً أو حدث خطأ: {insert_err}")
                            
                    st.rerun()
                except Exception as e:
                    st.error(f"خطأ في قاعدة البيانات: {e}")

        # عرض القائمة الحالية للحذف
        try:
            with get_db() as conn:
                watchlist_df = pd.read_sql("SELECT symbol FROM Watchlist", conn)
            
            if not watchlist_df.empty:
                st.write("الأسهم المتابعة حالياً:")
                for i, row in watchlist_df.iterrows():
                    c1, c2 = st.columns([4, 1])
                    c1.text(row['symbol'])
                    if c2.button("حذف", key=f"del_{row['symbol']}"):
                        with get_db() as conn:
                            conn.execute("DELETE FROM Watchlist WHERE symbol = ?", (row['symbol'],))
                            if hasattr(conn, 'commit'): conn.commit()
                        st.rerun()
            else:
                st.caption("القائمة فارغة.")
        except Exception as e:
            st.error("تعذر تحميل قائمة المتابعة.")

    st.divider()

    # 4. منطقة الخطر (إدارة البيانات)
    with st.expander("⚠️ منطقة الخطر (تعديل البيانات)"):
        st.warning("هذه الخيارات تؤثر مباشرة على قاعدة البيانات السحابية.")
        
        # خيار حذف صفقة محددة
        st.subheader("حذف صفقة")
        try:
            with get_db() as conn:
                # جلب آخر 50 صفقة مثلاً لتسريع العرض السحابي
                trades_df = pd.read_sql("SELECT id, date, symbol, type, quantity, price FROM Trades ORDER BY date DESC LIMIT 50", conn)
            
            if not trades_df.empty:
                trade_to_delete = st.selectbox(
                    "اختر الصفقة للحذف:", 
                    trades_df.index, 
                    format_func=lambda x: f"{trades_df.loc[x, 'date']} - {trades_df.loc[x, 'symbol']} ({trades_df.loc[x, 'type']})"
                )
                
                if st.button("حذف الصفقة المحددة", type="primary"):
                    trade_id = int(trades_df.loc[trade_to_delete, 'id'])
                    with get_db() as conn:
                        conn.execute("DELETE FROM Trades WHERE id = ?", (trade_id,))
                        if hasattr(conn, 'commit'): conn.commit()
                    st.success("تم حذف الصفقة.")
                    time.sleep(1)
                    st.rerun()
            else:
                st.info("لا توجد صفقات لعرضها.")
        except Exception as e:
            st.error(f"خطأ في جلب الصفقات: {e}")

# --- Main Router ---
def main():
    """
    الموجه الرئيسي للتطبيق.
    """
    # تهيئة الـ Session State
    if "custom_colors" not in st.session_state:
        st.session_state.custom_colors = PRESET_THEMES["افتراضي (فاتح)"].copy()

    # القائمة الجانبية
    with st.sidebar:
        st.title("📱 أسهمي (My Stocks)")
        page = st.radio(
            "تصفح الأقسام", 
            ["لوحة المعلومات", "المفظة", "سجل العمليات", "الإعدادات"],
            index=0
        )
        st.markdown("---")
        st.caption("نسخة سحابية v1.0")

    # توجيه الصفحات
    if page == "لوحة المعلومات":
        view_dashboard()
    elif page == "المفظة":
        view_portfolio()
    elif page == "سجل العمليات":
        view_transactions()
    elif page == "الإعدادات":
        view_settings()

if __name__ == "__main__":
    main()

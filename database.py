# database.py
import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
import bcrypt
from contextlib import contextmanager
import re
import config  # تم ربط الملف بـ config
from osoli_logging import get_logger, log_exception


# =========================================================
# 1) إعداد الاتصال (Connection Setup)
# =========================================================

@st.cache_resource
def get_connection_pool():
    """
    Connection pool (cached) for Streamlit using PostgreSQL.
    """
    db_url = getattr(config, 'DB_CONNECTION_URL', None) or getattr(config, 'get_db_url', lambda: None)()
    if not db_url:
        st.error("⚠️ لم يتم العثور على رابط قاعدة البيانات. ضع DATABASE_URL في Secrets أو Environment Variables")
        return None

    try:
        # إنشاء مسبح اتصالات بحد أدنى 1 وحد أقصى 20
        # ملاحظة: sslmode يمرر إلى psycopg2.connect عبر kwargs (صحيح)
        return psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=20,
            dsn=db_url,
            sslmode="require",
        )
    except Exception as e:
        log_exception(e, "DB pool init error")
        st.error(f"DB Error: {e}")
        return None


def _conn_is_healthy(conn) -> bool:
    """
    بعض البيئات تقفل الاتصال القديم داخل Pool.
    """
    try:
        return conn is not None and getattr(conn, "closed", 1) == 0
    except Exception:
        return False


@contextmanager
def get_db():
    """
    Context Manager لإدارة الاتصال وإرجاعه للـ Pool بأمان.
    """
    pool_obj = get_connection_pool()
    if not pool_obj:
        yield None
        return

    conn = None
    try:
        conn = pool_obj.getconn()

        # ✅ إصلاح: لو الاتصال قديم/مقفول — اغلقه وخذ غيره
        if not _conn_is_healthy(conn):
            try:
                pool_obj.putconn(conn, close=True)
            except Exception as e:
                log_exception(e, "Ignored DB cleanup error", level="DEBUG")
            conn = pool_obj.getconn()

        yield conn

    except Exception as e:
        # rollback آمن
        try:
            if conn and _conn_is_healthy(conn):
                conn.rollback()
        except Exception as e:
                log_exception(e, "Ignored DB cleanup error", level="DEBUG")
        log_exception(e, "DB Connection/Block Error")
        raise

    finally:
        # ارجاع الاتصال للمسبح
        try:
            if pool_obj and conn:
                pool_obj.putconn(conn)
        except Exception as e:
                log_exception(e, "Ignored DB cleanup error", level="DEBUG")


# =========================================================
# 2) أدوات التعامل مع الأسماء (Table Name Normalizer)
# =========================================================
KNOWN_TABLES = [
    # Core
    "Users",
    "Trades",
    "Deposits",
    "Withdrawals",
    "ReturnsGrants",
    "Watchlist",
    "InvestmentThesis",
    "FinancialStatements",
    # AI / Lab
    "ai_signals",
    "ai_weights",
    "ai_user_rules",
    "lab_runs",
    "lab_trades",
    "lab_equity",
    "ai_decisions",
]


def normalize_sql_tables(query: str) -> str:
    """
    يحول أسماء الجداول المعروفة إلى lowercase إذا كانت غير مقتبسة "Quoted".
    """
    if not query:
        return query
    fixed = query
    for t in KNOWN_TABLES:
        fixed = re.sub(rf'(?<!")\b{re.escape(t)}\b(?!")', str(t).lower(), fixed)
    return fixed


def _fix_placeholders(query: str) -> str:
    """
    تحويل ? إلى %s للتوافق مع مكتبة psycopg2
    """
    if not query:
        return query
    return query.replace("?", "%s")


def _quote_ident(name: str) -> str:
    """
    quoting identifiers safely: "name"
    """
    return '"' + str(name).replace('"', '""') + '"'


def _is_safe_identifier(name: str) -> bool:
    """
    يسمح فقط بأسماء جداول/أعمدة آمنة (حروف/أرقام/underscore) لتجنب أي حقن.
    """
    if name is None:
        return False
    s = str(name).strip()
    # يسمح بحالة وجود نقاط؟ عادة لا نحتاج schema.table داخل public
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s))


# =========================================================
# 3) التنفيذ والجلب (Execute / Fetch)
# =========================================================
def execute_query(query, params=()):
    """
    Execute SQL with safe normalization and placeholder fix.
    Returns True/False.
    """
    if not query:
        return False

    with get_db() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                fixed_query = normalize_sql_tables(str(query))
                fixed_query = _fix_placeholders(fixed_query)
                cur.execute(fixed_query, params or ())
                conn.commit()
            return True
        except Exception as e:
            try:
                conn.rollback()
            except Exception as e:
                log_exception(e, "Ignored DB cleanup error", level="DEBUG")
            print(f"Query Error: {e}")
            return False


def fetch_table(table_or_query, params=None):
    """
    ✅ جلب بيانات كـ DataFrame.
    يدعم حالتين:
    1) اسم جدول: fetch_table("trades")
    2) استعلام SQL مع باراميترات: fetch_table("SELECT ... WHERE x=%s", (..,))

    ملاحظات:
    - أسماء الجداول يتم التحقق منها لمنع SQL injection عبر identifiers.
    - عند تمرير Query، يتم استخدام pandas.read_sql مع params.
    """
    if table_or_query is None:
        return pd.DataFrame()

    q = str(table_or_query).strip()
    if not q:
        return pd.DataFrame()

    # detect query mode
    q_lower = q.lstrip().lower()
    is_query = (
        " " in q_lower or "\n" in q_lower
        or q_lower.startswith("select")
        or q_lower.startswith("with")
        or q_lower.startswith("show")
        or q_lower.startswith("pragma")
    )

    with get_db() as conn:
        if not conn:
            return pd.DataFrame()

        if is_query:
            try:
                return pd.read_sql(q, conn, params=params or ())
            except Exception as e:
                log_exception(e, "fetch_table(query) failed", level="ERROR")
                return pd.DataFrame()

        # table-name mode (legacy behavior)
        name_raw = q.replace('"', "")
        if not name_raw:
            return pd.DataFrame()

        # 0) تحقق من سلامة اسم الجدول (لتجنب SQL injection عبر identifier)
        if not _is_safe_identifier(name_raw):
            maybe = normalize_sql_tables(name_raw).strip().replace('"', "")
            if not _is_safe_identifier(maybe):
                return pd.DataFrame()
            name_raw = maybe

        # 1) Quoted exactly as passed
        try:
            return pd.read_sql(f"SELECT * FROM {_quote_ident(name_raw)}", conn)
        except Exception as e:
            log_exception(e, "Ignored DB read error (quoted)", level="DEBUG")

        # 2) Lowercase (common in Postgres)
        try:
            return pd.read_sql(f"SELECT * FROM {name_raw.lower()}", conn)
        except Exception as e:
            log_exception(e, "Ignored DB read error (lowercase)", level="DEBUG")

        # 3) Normalize from list
        try:
            t = normalize_sql_tables(name_raw).strip().replace('"', "")
            if not _is_safe_identifier(t):
                return pd.DataFrame()
            return pd.read_sql(f"SELECT * FROM {t}", conn)
        except Exception:
            return pd.DataFrame()
# =========================================================
# 4) التهيئة والمايجريشن (Init & Schema Migration)
# =========================================================
def migrate_financial_schema():
    """
    إضافة الأعمدة الجديدة لجدول القوائم المالية إذا لم تكن موجودة.
    """
    columns_to_add = [
        ("total_assets", "DOUBLE PRECISION"),
        ("total_liabilities", "DOUBLE PRECISION"),
        ("total_equity", "DOUBLE PRECISION"),
        ("operating_cash_flow", "DOUBLE PRECISION"),
        ("current_assets", "DOUBLE PRECISION"),
        ("current_liabilities", "DOUBLE PRECISION"),
        ("long_term_debt", "DOUBLE PRECISION"),
        ("source", "VARCHAR(20)"),
        ("period_type", "VARCHAR(20)"),
    ]

    for col_name, col_type in columns_to_add:
        execute_query(
            f"ALTER TABLE financialstatements ADD COLUMN IF NOT EXISTS {col_name} {col_type}",
            (),
        )


def init_db():
    """
    إنشاء جميع الجداول الأساسية. يتم استخدام lowercase لتفادي مشاكل Postgres.
    """
    tables = [
        "CREATE TABLE IF NOT EXISTS users (username VARCHAR(50) PRIMARY KEY, password TEXT, email TEXT)",
        """CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY, symbol VARCHAR(20), company_name TEXT, sector TEXT,
            asset_type VARCHAR(20), date DATE, quantity DOUBLE PRECISION, entry_price DOUBLE PRECISION,
            exit_price DOUBLE PRECISION DEFAULT 0, current_price DOUBLE PRECISION DEFAULT 0,
            strategy VARCHAR(20), status VARCHAR(10) DEFAULT 'Open', exit_date DATE, notes TEXT
        )""",
        "CREATE TABLE IF NOT EXISTS deposits (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS withdrawals (id SERIAL PRIMARY KEY, date DATE, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS returnsgrants (id SERIAL PRIMARY KEY, date DATE, symbol VARCHAR(20), company_name TEXT, amount DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS watchlist (symbol VARCHAR(20) PRIMARY KEY, target_price DOUBLE PRECISION, note TEXT)",
        "CREATE TABLE IF NOT EXISTS investmentthesis (symbol VARCHAR(20) PRIMARY KEY, thesis_text TEXT, target_price DOUBLE PRECISION, recommendation VARCHAR(20), last_updated DATE)",
        """CREATE TABLE IF NOT EXISTS financialstatements (
            symbol VARCHAR(20), date DATE,
            revenue DOUBLE PRECISION, net_income DOUBLE PRECISION,
            period_type VARCHAR(20) DEFAULT 'Annual',
            source VARCHAR(20) DEFAULT 'Auto',
            PRIMARY KEY(symbol, date, period_type)
        )""",
    ]

    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                for t in tables:
                    cur.execute(t)
            conn.commit()

    migrate_financial_schema()


# =========================================================
# 5) المصادقة والأمان (Auth)
# =========================================================
def db_create_user(u, p):
    try:
        h = bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        return execute_query("INSERT INTO Users (username, password) VALUES (%s, %s)", (u, h))
    except Exception as e:
        print(f"Create User Error: {e}")
        return False


def db_verify_user(u, p):
    """
    التحقق من المستخدم.
    """
    with get_db() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM users WHERE username = %s", (u,))
                res = cur.fetchone()
                if res and res[0]:
                    return bcrypt.checkpw(p.encode("utf-8"), res[0].encode("utf-8"))
        except Exception as e:
            print(f"Verify User Error: {e}")
            return False
    return False


# =========================================================
# 6) فحص الصحة والتشخيص (Healthcheck)
# =========================================================
def db_healthcheck():
    """
    تشخيص سريع: يعرض معلومات الاتصال + عداد سجلات الجداول + كشف ازدواج الجداول.
    لا يغير أي بيانات.
    """
    info = {"connected": False, "db": {}, "counts": {}, "dup_tables": []}

    with get_db() as conn:
        if not conn:
            return info

        info["connected"] = True
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_user, inet_server_addr()::text, inet_server_port();")
                res = cur.fetchone()
                if res:
                    dbname, user, host, port = res
                    info["db"] = {"database": dbname, "user": user, "host": host, "port": port}

                tables = [
                    "users",
                    "trades",
                    "deposits",
                    "withdrawals",
                    "returnsgrants",
                    "watchlist",
                    "investmentthesis",
                    "financialstatements",
                ]
                for t in tables:
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {t};")
                        info["counts"][t] = cur.fetchone()[0]
                    except Exception:
                        info["counts"][t] = None

                # فحص الجداول المكررة (Capital vs Small)
                cur.execute(
                    """
                    SELECT tablename FROM pg_tables
                    WHERE schemaname='public'
                    AND tablename IN ('trades','Trades','deposits','Deposits','financialstatements','FinancialStatements',
                                     'users','Users','watchlist','Watchlist','investmentthesis','InvestmentThesis',
                                     'withdrawals','Withdrawals','returnsgrants','ReturnsGrants');
                    """
                )
                found = [r[0] for r in cur.fetchall()]
                pairs = [
                    ("Users", "users"),
                    ("Trades", "trades"),
                    ("Deposits", "deposits"),
                    ("Withdrawals", "withdrawals"),
                    ("ReturnsGrants", "returnsgrants"),
                    ("Watchlist", "watchlist"),
                    ("InvestmentThesis", "investmentthesis"),
                    ("FinancialStatements", "financialstatements"),
                ]
                for a, b in pairs:
                    if a in found and b in found:
                        info["dup_tables"].append((a, b))

        except Exception as e:
            info["db"]["error"] = str(e)

    return info


# =========================================================
# 7) أدوات الإصلاح المتقدمة (Advanced Migration Helpers)
# =========================================================
def _table_exists(conn, table_name: str) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1 FROM pg_tables
                    WHERE schemaname='public' AND tablename=%s
                );
                """,
                (table_name,),
            )
            return bool(cur.fetchone()[0])
    except Exception:
        return False


def _get_columns(conn, table_name: str):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s
                ORDER BY ordinal_position;
                """,
                (table_name,),
            )
            return [r[0] for r in cur.fetchall()]
    except Exception:
        return []


def _get_primary_key_cols(conn, table_name: str) -> list:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass
                AND i.indisprimary;
                """,
                (table_name,),
            )
            return [r[0] for r in cur.fetchall()]
    except Exception:
        return []


def _set_sequence_to_max_id(conn, table_lower: str, id_col: str = "id"):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_get_serial_sequence(%s, %s);", (table_lower, id_col))
            res = cur.fetchone()
            if not res or not res[0]:
                return True
            seq = res[0]

            cur.execute(f"SELECT COALESCE(MAX({id_col}), 0) FROM {table_lower};")
            mx = int(cur.fetchone()[0] or 0)

            cur.execute("SELECT setval(%s, %s, true);", (seq, mx))
        conn.commit()
        return True
    except Exception as e:
        try:
            conn.rollback()
        except Exception as e:
                log_exception(e, "Ignored DB cleanup error", level="DEBUG")
        print(f"Sequence Fix Error ({table_lower}): {e}")
        return False


def migrate_fix_case_duplicate_tables(drop_old: bool = False) -> dict:
    """
    إصلاح ازدواج الجداول بسبب حالة الأحرف (Case Sensitivity).
    """
    report = {"ok": False, "actions": [], "errors": []}

    pairs = [
        ("Users", "users"),
        ("Trades", "trades"),
        ("Deposits", "deposits"),
        ("Withdrawals", "withdrawals"),
        ("ReturnsGrants", "returnsgrants"),
        ("Watchlist", "watchlist"),
        ("InvestmentThesis", "investmentthesis"),
        ("FinancialStatements", "financialstatements"),
    ]

    serial_id_tables = {"trades", "deposits", "withdrawals", "returnsgrants"}

    with get_db() as conn:
        if not conn:
            report["errors"].append("No DB connection")
            return report

        try:
            with conn.cursor() as cur:
                for src_cap, dst_low in pairs:
                    src_exists = _table_exists(conn, src_cap)
                    dst_exists = _table_exists(conn, dst_low)
                    if not (src_exists and dst_exists):
                        continue

                    src_cols = _get_columns(conn, src_cap)
                    dst_cols = _get_columns(conn, dst_low)

                    common = [c for c in dst_cols if c in src_cols]
                    if not common:
                        report["errors"].append(f"No common columns between {src_cap} and {dst_low}")
                        continue

                    pk_cols = _get_primary_key_cols(conn, dst_low)

                    cols_csv = ", ".join([_quote_ident(c) for c in common])
                    src_table_sql = _quote_ident(src_cap)

                    if pk_cols and all(pk in common for pk in pk_cols):
                        pk_csv = ", ".join([_quote_ident(c) for c in pk_cols])

                        if dst_low in ("watchlist", "investmentthesis", "financialstatements"):
                            set_cols = [c for c in common if c not in pk_cols]
                            if set_cols:
                                set_sql = ", ".join([f"{_quote_ident(c)} = EXCLUDED.{_quote_ident(c)}" for c in set_cols])
                                sql = f"""
                                    INSERT INTO {dst_low} ({cols_csv})
                                    SELECT {cols_csv} FROM {src_table_sql}
                                    ON CONFLICT ({pk_csv}) DO UPDATE SET {set_sql};
                                """
                            else:
                                sql = f"""
                                    INSERT INTO {dst_low} ({cols_csv})
                                    SELECT {cols_csv} FROM {src_table_sql}
                                    ON CONFLICT ({pk_csv}) DO NOTHING;
                                """
                        else:
                            sql = f"""
                                INSERT INTO {dst_low} ({cols_csv})
                                SELECT {cols_csv} FROM {src_table_sql}
                                ON CONFLICT ({pk_csv}) DO NOTHING;
                            """
                    else:
                        sql = f"""
                            INSERT INTO {dst_low} ({cols_csv})
                            SELECT {cols_csv} FROM {src_table_sql};
                        """

                    try:
                        cur.execute(sql)
                        report["actions"].append(f"Merged {src_table_sql} -> {dst_low} (cols={len(common)})")
                        conn.commit()
                    except Exception as e:
                        try:
                            conn.rollback()
                        except Exception as e:
                            log_exception(e, "Ignored DB cleanup error", level="DEBUG")
                        report["errors"].append(f"Merge failed for {src_cap}->{dst_low}: {e}")
                        continue

                    if dst_low in serial_id_tables:
                        _set_sequence_to_max_id(conn, dst_low, "id")

                    if drop_old:
                        try:
                            cur.execute(f"DROP TABLE IF EXISTS {src_table_sql} CASCADE;")
                            conn.commit()
                            report["actions"].append(f"Dropped old table {src_table_sql}")
                        except Exception as e:
                            try:
                                conn.rollback()
                            except Exception as e:
                                log_exception(e, "Ignored DB cleanup error", level="DEBUG")
                            report["errors"].append(f"Drop failed for {src_table_sql}: {e}")

            report["ok"] = (len(report["errors"]) == 0)
            return report

        except Exception as e:
            try:
                conn.rollback()
            except Exception as e:
                log_exception(e, "Ignored DB cleanup error", level="DEBUG")
            report["errors"].append(str(e))
            report["ok"] = False
            return report

"""
BillFlow's tables, written once and rendered for each database type.

Everything is INTEGER, DOUBLE-like numbers or VARCHAR, and foreign keys are
declared at table level: MySQL ignores the inline REFERENCES form, and cannot
index or give defaults to TEXT columns.
"""
from billflow import clock

_TYPES = {
    "sqlite":     {"pk": "INTEGER PRIMARY KEY AUTOINCREMENT", "real": "REAL"},
    "postgresql": {"pk": "SERIAL PRIMARY KEY", "real": "DOUBLE PRECISION"},
    "mysql":      {"pk": "INTEGER PRIMARY KEY AUTO_INCREMENT", "real": "DOUBLE"},
}

# Parent tables come before the tables that point at them.
_TABLES = {
    "products": """
        id       {pk},
        name     VARCHAR(255) NOT NULL,
        price    {real} NOT NULL DEFAULT 0,
        quantity INTEGER NOT NULL DEFAULT 0,
        category VARCHAR(100) NOT NULL DEFAULT 'General',
        hsn_code VARCHAR(20) NOT NULL DEFAULT '',
        gst_rate {real} NOT NULL DEFAULT 18
    """,
    "customers": """
        id          {pk},
        name        VARCHAR(255) NOT NULL,
        phone       VARCHAR(30),
        email       VARCHAR(255),
        age         INTEGER,
        gender      VARCHAR(20),
        tag         VARCHAR(20) DEFAULT 'Regular',
        total_spent {real} NOT NULL DEFAULT 0,
        visit_count INTEGER NOT NULL DEFAULT 0
    """,
    "bills": """
        id           {pk},
        date         VARCHAR(30) NOT NULL,
        customer     VARCHAR(255) NOT NULL,
        customer_id  INTEGER,
        subtotal     {real} NOT NULL DEFAULT 0,
        discount     {real} NOT NULL DEFAULT 0,
        tax          {real} NOT NULL DEFAULT 0,
        total        {real} NOT NULL DEFAULT 0,
        note         VARCHAR(500) DEFAULT '',
        coupon_code  VARCHAR(50) DEFAULT '',
        payment_mode VARCHAR(20) DEFAULT 'Cash',
        staff_id     INTEGER DEFAULT 0,
        FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
    """,
    "bill_items": """
        id         {pk},
        bill_id    INTEGER NOT NULL,
        product_id INTEGER,
        name       VARCHAR(255) NOT NULL,
        price      {real} NOT NULL,
        qty        INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
    """,
    "coupons": """
        id          {pk},
        code        VARCHAR(50) NOT NULL UNIQUE,
        type        VARCHAR(20) NOT NULL DEFAULT 'percent',
        value       {real} NOT NULL DEFAULT 0,
        min_bill    {real} NOT NULL DEFAULT 0,
        expiry      VARCHAR(20) NOT NULL DEFAULT '',
        active      INTEGER NOT NULL DEFAULT 1,
        usage_count INTEGER NOT NULL DEFAULT 0,
        description VARCHAR(500) DEFAULT ''
    """,
    "staff": """
        id             {pk},
        name           VARCHAR(255) NOT NULL,
        phone          VARCHAR(30) DEFAULT '',
        role           VARCHAR(50) DEFAULT 'Staff',
        shift_start    VARCHAR(10) DEFAULT '09:00',
        shift_end      VARCHAR(10) DEFAULT '18:00',
        commission_pct {real} DEFAULT 0,
        salary         {real} DEFAULT 0,
        active         INTEGER DEFAULT 1
    """,
    "sales_targets": """
        id         {pk},
        period     VARCHAR(20) NOT NULL,
        target_amt {real} NOT NULL DEFAULT 0,
        staff_id   INTEGER DEFAULT 0
    """,
    "holidays": """
        id   {pk},
        date VARCHAR(20) NOT NULL UNIQUE,
        name VARCHAR(255) NOT NULL DEFAULT '',
        type VARCHAR(30) NOT NULL DEFAULT 'holiday'
    """,
    "expenses": """
        id       {pk},
        date     VARCHAR(20) NOT NULL,
        category VARCHAR(100) NOT NULL DEFAULT 'General',
        amount   {real} NOT NULL DEFAULT 0,
        note     VARCHAR(500) DEFAULT '',
        staff_id INTEGER DEFAULT 0
    """,
    "purchase_orders": """
        id           {pk},
        date         VARCHAR(20) NOT NULL,
        product_id   INTEGER,
        product_name VARCHAR(255) NOT NULL,
        qty_ordered  INTEGER NOT NULL DEFAULT 0,
        unit_cost    {real} NOT NULL DEFAULT 0,
        supplier     VARCHAR(255) DEFAULT '',
        status       VARCHAR(20) DEFAULT 'Pending',
        note         VARCHAR(500) DEFAULT '',
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
    """,
    "cash_register": """
        id           {pk},
        date         VARCHAR(20) NOT NULL UNIQUE,
        opening_cash {real} NOT NULL DEFAULT 0,
        notes        VARCHAR(500) DEFAULT ''
    """,
    "staff_advances": """
        id       {pk},
        staff_id INTEGER NOT NULL,
        date     VARCHAR(20) NOT NULL,
        amount   {real} NOT NULL DEFAULT 0,
        note     VARCHAR(500) DEFAULT '',
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE
    """,
    "roster": """
        id         {pk},
        staff_id   INTEGER NOT NULL,
        week_start VARCHAR(20) NOT NULL,
        monday     VARCHAR(30) DEFAULT '',
        tuesday    VARCHAR(30) DEFAULT '',
        wednesday  VARCHAR(30) DEFAULT '',
        thursday   VARCHAR(30) DEFAULT '',
        friday     VARCHAR(30) DEFAULT '',
        saturday   VARCHAR(30) DEFAULT '',
        sunday     VARCHAR(30) DEFAULT '',
        FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE
    """,
    "suppliers": """
        id      {pk},
        name    VARCHAR(255) NOT NULL,
        phone   VARCHAR(30) DEFAULT '',
        email   VARCHAR(255) DEFAULT '',
        gstin   VARCHAR(20) DEFAULT '',
        address VARCHAR(500) DEFAULT '',
        note    VARCHAR(500) DEFAULT ''
    """,
    # Every data-changing action, so Rule 56(8)'s edit log requirement is satisfied.
    "audit_log": """
        id         {pk},
        date       VARCHAR(30) NOT NULL,
        staff_id   INTEGER,
        staff_name VARCHAR(255) NOT NULL DEFAULT '',
        action     VARCHAR(50) NOT NULL,
        entity     VARCHAR(50) NOT NULL,
        entity_id  INTEGER,
        detail     VARCHAR(1000) DEFAULT ''
    """,
    # Signing keys generated on first use. It has an id column because PostgreSQL INSERTs ask for one back.
    "app_secrets": """
        id    {pk},
        name  VARCHAR(50) NOT NULL UNIQUE,
        value VARCHAR(128) NOT NULL
    """,
    # Every change to a product's quantity, so on hand always equals the sum of qty here.
    "stock_movements": """
        id         {pk},
        date       VARCHAR(30) NOT NULL,
        product_id INTEGER NOT NULL,
        type       VARCHAR(20) NOT NULL,
        qty        INTEGER NOT NULL,
        balance    INTEGER NOT NULL,
        unit_cost  {real},
        ref_id     INTEGER,
        reason     VARCHAR(100) DEFAULT '',
        note       VARCHAR(500) DEFAULT '',
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
    """,
}

TABLE_NAMES = list(_TABLES)

# A product is low on stock when it has fewer units than its reorder level; new products start here.
DEFAULT_REORDER_LEVEL = 10

# Columns added after the tables were first released. create_schema adds any an older database lacks,
# so a new database and an upgraded one end up the same.
_ADDED_COLUMNS = [
    ("products", "sku", "VARCHAR(64) NOT NULL DEFAULT ''"),
    ("products", "barcode", "VARCHAR(64) NOT NULL DEFAULT ''"),
    ("products", "cost", "{real} NOT NULL DEFAULT 0"),
    ("products", "reorder_level", f"INTEGER NOT NULL DEFAULT {DEFAULT_REORDER_LEVEL}"),
    ("products", "supplier_id", "INTEGER"),
    ("products", "archived", "INTEGER NOT NULL DEFAULT 0"),
    ("bill_items", "cost", "{real} NOT NULL DEFAULT 0"),
    ("bill_items", "return_status", "VARCHAR(20) NOT NULL DEFAULT ''"),
    ("purchase_orders", "qty_received", "INTEGER NOT NULL DEFAULT 0"),
    ("purchase_orders", "supplier_id", "INTEGER"),
    ("staff", "pin", "VARCHAR(12) NOT NULL DEFAULT ''"),
    ("staff", "permissions", "VARCHAR(500) NOT NULL DEFAULT ''"),
    ("bills", "refund_of", "INTEGER"),
    ("bills", "credit_note", "VARCHAR(30) NOT NULL DEFAULT ''"),
]

# Run once, right after the column is added to an existing database, to fill it in from what is there.
_FILL_ADDED_COLUMN = {
    ("purchase_orders", "qty_received"): "UPDATE purchase_orders SET qty_received = qty_ordered WHERE status = 'Received'",
    # Best guess at a cost for products that already have stock: the last price paid on a received order.
    ("products", "cost"): (
        "UPDATE products SET cost = (SELECT po.unit_cost FROM purchase_orders po WHERE po.product_id = products.id "
        "AND po.status = 'Received' AND po.unit_cost > 0 ORDER BY po.id DESC LIMIT 1) "
        "WHERE EXISTS (SELECT 1 FROM purchase_orders po WHERE po.product_id = products.id "
        "AND po.status = 'Received' AND po.unit_cost > 0)"),
}

_INDEXES = [
    ("idx_bill_items_bid", "bill_items", "bill_id"),
    ("idx_bill_items_pid", "bill_items", "product_id"),
    ("idx_bills_date", "bills", "date"),
    ("idx_bills_cust", "bills", "customer_id"),
    ("idx_products_name", "products", "name"),
    ("idx_customers_name", "customers", "name"),
    ("idx_customers_phone", "customers", "phone"),
    ("idx_expenses_date", "expenses", "date"),
    ("idx_moves_pid", "stock_movements", "product_id"),
    ("idx_moves_date", "stock_movements", "date"),
    ("idx_products_barcode", "products", "barcode"),
    ("idx_products_sku", "products", "sku"),
    ("idx_products_archived", "products", "archived"),
    ("idx_audit_date", "audit_log", "date"),
    ("idx_audit_entity", "audit_log", "entity, entity_id"),
    ("idx_bills_refund_of", "bills", "refund_of"),
]


def _columns(conn, table) -> set:
    if conn.dialect == "sqlite":
        return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    where = "table_schema = current_schema()" if conn.dialect == "postgresql" else "table_schema = DATABASE()"
    rows = conn.execute(f"SELECT column_name AS name FROM information_schema.columns WHERE {where} AND table_name = ?",
                        (table,)).fetchall()
    return {r["name"] for r in rows}


def _add_missing_columns(conn, types):
    present = {}
    for table, column, definition in _ADDED_COLUMNS:
        if table not in present:
            present[table] = _columns(conn, table)
        if column not in present[table]:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition.format(**types)}")
            present[table].add(column)
            if (table, column) in _FILL_ADDED_COLUMN:
                conn.execute(_FILL_ADDED_COLUMN[(table, column)])


def record_opening_balances(conn):
    """Products that have stock but no ledger rows yet (from before the ledger existed, or added
    straight into the table) get an opening balance, so the ledger adds up to what is on hand."""
    conn.execute(
        "INSERT INTO stock_movements (date, product_id, type, qty, balance, reason) "
        "SELECT ?, p.id, 'Opening', p.quantity, p.quantity, 'Opening balance' FROM products p "
        "WHERE p.quantity <> 0 AND NOT EXISTS (SELECT 1 FROM stock_movements m WHERE m.product_id = p.id)",
        (clock.now().strftime("%Y-%m-%d %H:%M:%S"),))


def create_schema(conn):
    """Create any missing tables, columns and indexes. Safe to run on every start."""
    types = _TYPES[conn.dialect]
    for name, columns in _TABLES.items():
        conn.execute(f"CREATE TABLE IF NOT EXISTS {name} ({columns.format(**types)})")
    _add_missing_columns(conn, types)
    record_opening_balances(conn)
    for index, table, column in _INDEXES:
        if conn.dialect == "mysql":
            # MySQL has no CREATE INDEX IF NOT EXISTS
            found = conn.execute(
                "SELECT COUNT(*) AS n FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND table_name = ? AND index_name = ?",
                (table, index)).fetchone()["n"]
            if found:
                continue
            conn.execute(f"CREATE INDEX {index} ON {table} ({column})")
        else:
            conn.execute(f"CREATE INDEX IF NOT EXISTS {index} ON {table} ({column})")

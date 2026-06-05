import aiosqlite
import json
import secrets
from config import DATABASE_URL


# ─── ACCOUNTANT ───────────────────────────────────────────────

async def get_accountant(telegram_id: int):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM accountants WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_accountant(telegram_id: int, full_name: str, phone: str):
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            "INSERT OR IGNORE INTO accountants (telegram_id, full_name, phone) VALUES (?, ?, ?)",
            (telegram_id, full_name, phone),
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM accountants WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            db.row_factory = aiosqlite.Row
            row = await cursor.fetchone()
            return dict(row) if row else None


# ─── CLIENT ───────────────────────────────────────────────────

async def get_client(telegram_id: int):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_client(telegram_id: int, full_name: str = None):
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            "INSERT OR IGNORE INTO clients (telegram_id, full_name) VALUES (?, ?)",
            (telegram_id, full_name),
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


# ─── INVITE LINKS ─────────────────────────────────────────────

async def create_invite_token(accountant_id: int) -> str:
    token = "MAC_" + secrets.token_hex(4).upper()
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            "INSERT INTO invite_links (accountant_id, token) VALUES (?, ?)",
            (accountant_id, token),
        )
        await db.commit()
    return token


async def get_invite_link(token: str):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM invite_links WHERE token = ? AND is_active = 1", (token,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def deactivate_invite_token(token: str, accountant_id: int):
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            "UPDATE invite_links SET is_active = 0 WHERE token = ? AND accountant_id = ?",
            (token, accountant_id),
        )
        await db.commit()


async def get_accountant_tokens(accountant_id: int):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM invite_links WHERE accountant_id = ? ORDER BY created_at DESC",
            (accountant_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# ─── CLIENT–ACCOUNTANT LINK ───────────────────────────────────

async def link_client_accountant(client_id: int, accountant_id: int):
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            "INSERT OR IGNORE INTO client_accountant (client_id, accountant_id) VALUES (?, ?)",
            (client_id, accountant_id),
        )
        await db.commit()


async def get_client_accountants(client_id: int):
    """Returns list of accountants linked to this client."""
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT a.* FROM accountants a
               JOIN client_accountant ca ON ca.accountant_id = a.id
               WHERE ca.client_id = ?""",
            (client_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_accountant_clients(accountant_id: int):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT c.* FROM clients c
               JOIN client_accountant ca ON ca.client_id = c.id
               WHERE ca.accountant_id = ?""",
            (accountant_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# ─── DOCUMENT BATCHES ─────────────────────────────────────────

async def create_batch(client_id: int, accountant_id: int) -> int:
    async with aiosqlite.connect(DATABASE_URL) as db:
        cursor = await db.execute(
            "INSERT INTO document_batches (client_id, accountant_id, status) VALUES (?, ?, 'pending')",
            (client_id, accountant_id),
        )
        await db.commit()
        return cursor.lastrowid


async def update_batch_status(batch_id: int, status: str):
    async with aiosqlite.connect(DATABASE_URL) as db:
        if status == "done":
            await db.execute(
                "UPDATE document_batches SET status = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, batch_id),
            )
        else:
            await db.execute(
                "UPDATE document_batches SET status = ? WHERE id = ?",
                (status, batch_id),
            )
        await db.commit()


async def get_batch(batch_id: int):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM document_batches WHERE id = ?", (batch_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


# ─── DOCUMENTS ────────────────────────────────────────────────

async def add_document(batch_id: int, file_path: str, telegram_file_id: str,
                       doc_type: str = None, payment_type: str = None, include_items: int = 0) -> int:
    async with aiosqlite.connect(DATABASE_URL) as db:
        cursor = await db.execute(
            """INSERT INTO documents (batch_id, file_path, telegram_file_id, doc_type, payment_type, include_items)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (batch_id, file_path, telegram_file_id, doc_type, payment_type, include_items),
        )
        await db.commit()
        return cursor.lastrowid


async def update_document_ocr(doc_id: int, ocr_result: dict):
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            "UPDATE documents SET ocr_result = ? WHERE id = ?",
            (json.dumps(ocr_result, ensure_ascii=False), doc_id),
        )
        await db.commit()


async def get_batch_documents(batch_id: int):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM documents WHERE batch_id = ? ORDER BY id ASC", (batch_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_client_history(client_id: int, limit: int = 10):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT db.*, COUNT(d.id) as doc_count
               FROM document_batches db
               LEFT JOIN documents d ON d.batch_id = db.id
               WHERE db.client_id = ?
               GROUP BY db.id
               ORDER BY db.created_at DESC
               LIMIT ?""",
            (client_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# ─── PANEL TOKENS ─────────────────────────────────────────────

async def create_panel_token(accountant_id: int, hours: int = 24) -> str:
    """Create a time-limited panel access token."""
    token = secrets.token_urlsafe(32)
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            """INSERT INTO panel_tokens (accountant_id, token, expires_at)
               VALUES (?, ?, datetime('now', ?))""",
            (accountant_id, token, f"+{hours} hours"),
        )
        await db.commit()
    return token


async def get_panel_token(token: str):
    """Returns accountant if token is valid and not expired."""
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT a.* FROM accountants a
               JOIN panel_tokens pt ON pt.accountant_id = a.id
               WHERE pt.token = ? AND pt.expires_at > datetime('now')""",
            (token,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


# ─── PANEL QUERIES ────────────────────────────────────────────

async def get_panel_clients(accountant_id: int):
    """All clients with document count and last activity."""
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT c.id, c.full_name, c.created_at,
                      COUNT(DISTINCT db.id) as batch_count,
                      COUNT(d.id) as doc_count,
                      MAX(db.created_at) as last_activity
               FROM clients c
               JOIN client_accountant ca ON ca.client_id = c.id
               LEFT JOIN document_batches db ON db.client_id = c.id AND db.accountant_id = ?
               LEFT JOIN documents d ON d.batch_id = db.id
               WHERE ca.accountant_id = ?
               GROUP BY c.id
               ORDER BY last_activity DESC""",
            (accountant_id, accountant_id),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_panel_documents(accountant_id: int, client_id: int, month: str = None):
    """
    All documents for a client. month = 'YYYY-MM' to filter, None = all.
    """
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        if month:
            async with db.execute(
                """SELECT d.id, d.file_path, d.telegram_file_id, d.ocr_result, d.created_at,
                          d.doc_type, d.payment_type, d.include_items, d.review_status,
                          db.id as batch_id, db.status
                   FROM documents d
                   JOIN document_batches db ON db.id = d.batch_id
                   WHERE db.accountant_id = ? AND db.client_id = ?
                     AND strftime('%Y-%m', d.created_at) = ?
                   ORDER BY d.created_at ASC""",
                (accountant_id, client_id, month),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """SELECT d.id, d.file_path, d.telegram_file_id, d.ocr_result, d.created_at,
                          d.doc_type, d.payment_type, d.include_items, d.review_status,
                          db.id as batch_id, db.status
                   FROM documents d
                   JOIN document_batches db ON db.id = d.batch_id
                   WHERE db.accountant_id = ? AND db.client_id = ?
                   ORDER BY d.created_at ASC""",
                (accountant_id, client_id),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_accountant_by_id(accountant_id: int):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM accountants WHERE id = ?", (accountant_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


# ─── COMPANY (CARİ) ───────────────────────────────────────────

async def upsert_company(client_id: int, accountant_id: int, name: str, tax_no: str = None):
    """Insert or ignore company for this client."""
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            """INSERT OR IGNORE INTO companies (client_id, accountant_id, name, tax_no)
               VALUES (?, ?, ?, ?)""",
            (client_id, accountant_id, name, tax_no),
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM companies WHERE client_id=? AND accountant_id=? AND name=?",
            (client_id, accountant_id, name),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_companies(accountant_id: int, client_id: int = None):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        if client_id:
            async with db.execute(
                "SELECT * FROM companies WHERE accountant_id=? AND client_id=? ORDER BY name",
                (accountant_id, client_id),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM companies WHERE accountant_id=? ORDER BY name",
                (accountant_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]

import aiosqlite
from config import DATABASE_URL

async def init_db():
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS accountants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id BIGINT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                phone TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id BIGINT UNIQUE NOT NULL,
                full_name TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS invite_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                accountant_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (accountant_id) REFERENCES accountants(id)
            );

            CREATE TABLE IF NOT EXISTS client_accountant (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                accountant_id INTEGER NOT NULL,
                linked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(client_id, accountant_id),
                FOREIGN KEY (client_id) REFERENCES clients(id),
                FOREIGN KEY (accountant_id) REFERENCES accountants(id)
            );

            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                accountant_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                tax_no TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(id),
                FOREIGN KEY (accountant_id) REFERENCES accountants(id)
            );

            CREATE TABLE IF NOT EXISTS document_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                accountant_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                FOREIGN KEY (client_id) REFERENCES clients(id),
                FOREIGN KEY (accountant_id) REFERENCES accountants(id)
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                file_path TEXT,
                telegram_file_id TEXT,
                ocr_result TEXT,
                doc_type TEXT,
                payment_type TEXT,
                company_id INTEGER,
                include_items INTEGER DEFAULT 0,
                review_status TEXT DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES document_batches(id),
                FOREIGN KEY (company_id) REFERENCES companies(id)
            );

            CREATE TABLE IF NOT EXISTS panel_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                accountant_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                FOREIGN KEY (accountant_id) REFERENCES accountants(id)
            );
        """)
        await db.commit()

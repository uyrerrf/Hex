import sqlite3
import os

db_path = None
for f in os.listdir('.'):
    if f.endswith('.db'):
        db_path = f
        break

if not db_path:
    db_path = 'database.db'

print(f'DB: {db_path}')
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Get current schema
cur.execute("SELECT sql FROM sqlite_master WHERE name='device_overlay_mappings'")
row = cur.fetchone()
if row:
    print(f'Current schema: {row[0]}')
    
    # Drop and recreate with nullable fields
    cur.execute('ALTER TABLE device_overlay_mappings RENAME TO device_overlay_mappings_old')
    cur.execute('''CREATE TABLE device_overlay_mappings (
        id INTEGER PRIMARY KEY,
        device_id VARCHAR(100) NOT NULL,
        package_name VARCHAR(255) NOT NULL,
        project_id VARCHAR(50),
        screen_id VARCHAR(50),
        screen_name VARCHAR(100),
        template_json TEXT,
        is_enabled BOOLEAN DEFAULT 1,
        created_at DATETIME
    )''')
    cur.execute('INSERT INTO device_overlay_mappings SELECT * FROM device_overlay_mappings_old')
    cur.execute('DROP TABLE device_overlay_mappings_old')
    conn.commit()
    
    # Verify
    cur.execute("SELECT sql FROM sqlite_master WHERE name='device_overlay_mappings'")
    row = cur.fetchone()
    print(f'New schema: {row[0]}')
    print('Migration done!')
else:
    print('Table not found, will be created on next startup')

conn.close()

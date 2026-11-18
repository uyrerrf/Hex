import sqlite3
import os

db_path = "gangstar_local.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("UPDATE operators SET totp_enabled = 0, hwid = NULL WHERE username = 'admin'")
    conn.commit()
    print("Sucesso! Linhas afetadas:", c.rowcount)
    conn.close()
else:
    print("DB nao encontrado em", db_path)

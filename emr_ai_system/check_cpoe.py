import sqlite3

DB_PATH = "rsjpdhk_emr.db"

print("\n" + "="*70)
print("1️⃣ CHECK DATABASE")
print("="*70)

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cpoe_orders'")
    if cursor.fetchone():
        print("✅ Table 'cpoe_orders' EXISTS")
        cursor.execute("SELECT COUNT(*) FROM cpoe_orders")
        count = cursor.fetchone()[0]
        print(f"   📊 Total records: {count}")
        if count > 0:
            print("\n   Sample data:")
            cursor.execute("SELECT order_id, episode_id, order_name, status FROM cpoe_orders LIMIT 3")
            for row in cursor.fetchall():
                print(f"   - {row[0]} | {row[1]} | {row[2]} | {row[3]}")
    else:
        print("❌ Table 'cpoe_orders' NOT FOUND")
    conn.close()
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "="*70)
print("2️⃣ CHECK bridge_cpoe_sync")
print("="*70)

try:
    from modules.bridge_cpoe_sync import CPOESyncManager
    print("✅ Module imported")
    sync = CPOESyncManager(db_path=DB_PATH)
    print("✅ CPOESyncManager created")
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "="*70)
print("3️⃣ CHECK dashboard.py")
print("="*70)

try:
    with open("dashboard.py", "r") as f:
        if "Order dari Dokter (CPOE)" in f.read():
            print("✅ CPOE section found")
        else:
            print("❌ CPOE section NOT found - use dashboard-integrated.py")
except FileNotFoundError:
    print("❌ dashboard.py not found - use dashboard-integrated.py")
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "="*70)
print("4️⃣ CHECK order_type vs filter dashboard.py")
print("="*70)
print("dashboard.py HANYA menampilkan order_type: obat / lab / ventilator / bundle")

VALID_CODES = {"obat", "lab", "ventilator", "bundle"}
try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT order_type, COUNT(*) FROM cpoe_orders GROUP BY order_type")
    rows = cursor.fetchall()
    if not rows:
        print("   (Belum ada order tersimpan)")
    else:
        bermasalah = 0
        for order_type, jumlah in rows:
            if order_type in VALID_CODES:
                print(f"   ✅ '{order_type}': {jumlah} order — akan MUNCUL di dashboard")
            else:
                bermasalah += jumlah
                print(f"   ❌ '{order_type}': {jumlah} order — TIDAK akan muncul "
                      f"(bukan salah satu dari {VALID_CODES})")
        if bermasalah:
            print(f"\n   ⚠️ {bermasalah} order TERSIMPAN tapi TIDAK SINKRON ke dashboard "
                  "karena order_type belum dinormalisasi (lihat fix modules/doctor/database.py).")
        else:
            print("\n   🎉 Semua order_type sudah valid, harus muncul normal di dashboard.")
    conn.close()
except Exception as e:
    print(f"❌ Error: {e}")
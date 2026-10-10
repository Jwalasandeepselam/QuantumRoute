import sqlite3
import json

DB_PATH = "quantum_route.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            role TEXT
        )
    ''')
    
    # Nodes table (Emergency pins)
    c.execute('''
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lat REAL,
            lon REAL,
            label TEXT,
            priority TEXT DEFAULT 'Normal'
        )
    ''')
    # Migrate databases created before incident priorities existed.
    columns = {row[1] for row in c.execute("PRAGMA table_info(nodes)")}
    if "priority" not in columns:
        c.execute("ALTER TABLE nodes ADD COLUMN priority TEXT DEFAULT 'Normal'")
    
    # Drivers state table
    c.execute('''
        CREATE TABLE IF NOT EXISTS driver_state (
            username TEXT PRIMARY KEY,
            lat REAL,
            lon REAL,
            assigned_route TEXT, 
            route_geometries TEXT,
            route_durations TEXT,
            current_stop_index INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insert default users if not exists
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('admin', 'admin123', 'Admin')")
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('driver1', 'driver123', 'Driver')")
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('driver2', 'driver123', 'Driver')")
    
    conn.commit()
    conn.close()

def get_nodes():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, lat, lon, label, priority FROM nodes")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "lat": r[1], "lon": r[2], "label": r[3], "priority": r[4] if len(r)>4 and r[4] else "Normal"} for r in rows]

def add_node(lat, lon, label):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO nodes (lat, lon, label, priority) VALUES (?, ?, ?, 'Normal')", (lat, lon, label))
    conn.commit()
    conn.close()

def update_node(node_id, label, priority):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE nodes SET label=?, priority=? WHERE id=?", (label, priority, node_id))
    conn.commit()
    conn.close()

def delete_node(node_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
    conn.commit()
    conn.close()

def clear_nodes():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM nodes")
    conn.commit()
    conn.close()

def update_driver_route(username, route, geometries, durations):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO driver_state (username, assigned_route, route_geometries, route_durations, current_stop_index)
        VALUES (?, ?, ?, ?, 0)
        ON CONFLICT(username) DO UPDATE SET 
            assigned_route=excluded.assigned_route,
            route_geometries=excluded.route_geometries,
            route_durations=excluded.route_durations,
            current_stop_index=0
    ''', (username, json.dumps(route), json.dumps(geometries), json.dumps(durations)))
    conn.commit()
    conn.close()

def update_driver_location(username, lat, lon, stop_index):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO driver_state (username, lat, lon, current_stop_index)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET 
            lat=excluded.lat,
            lon=excluded.lon,
            current_stop_index=excluded.current_stop_index,
            last_updated=CURRENT_TIMESTAMP
    ''', (username, lat, lon, stop_index))
    conn.commit()
    conn.close()

def get_driver_state(username):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT lat, lon, assigned_route, route_geometries, route_durations, current_stop_index FROM driver_state WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "lat": row[0],
            "lon": row[1],
            "assigned_route": json.loads(row[2]) if row[2] else [],
            "route_geometries": json.loads(row[3]) if row[3] else [],
            "route_durations": json.loads(row[4]) if row[4] else [],
            "current_stop_index": row[5]
        }
    return None

def get_all_drivers():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT u.username, d.lat, d.lon, d.current_stop_index 
        FROM users u 
        LEFT JOIN driver_state d ON u.username = d.username 
        WHERE u.role = 'Driver'
    ''')
    rows = c.fetchall()
    conn.close()
    return [{"username": r[0], "lat": r[1], "lon": r[2], "current_stop_index": r[3]} for r in rows]

def add_driver(username, password):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'Driver')", (username, password))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()

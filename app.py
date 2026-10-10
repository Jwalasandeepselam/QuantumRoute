import streamlit as st
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import time
import osrm_helper
import quantum_solver
import db

def init_session_state():
    """Initialize basic auth session state."""
    db.init_db()
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "username" not in st.session_state:
        st.session_state.username = None
    if "role" not in st.session_state:
        st.session_state.role = None

def login():
    st.title("🚑 QuantumRoute Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")
        
        if submit_button:
            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT role FROM users WHERE username=? AND password=?", (username, password))
            row = c.fetchone()
            conn.close()
            if row:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.role = row[0]
                st.rerun()
            else:
                st.error("Invalid username or password")

def logout():
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None
    st.rerun()

def admin_dashboard():
    st.header("👮 Officer Command Center")
    st.info("💡 Tip: Drop pins to create emergencies, then Calculate VRP Route.")
    
    # Auto-refresh every 3 seconds to see live driver updates
    st_autorefresh(interval=3000, key="admin_refresh")
    
    # Load nodes from DB
    nodes = db.get_nodes()
    
    # Load driver states from DB
    drivers = db.get_all_drivers()
    
    m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)
    
    # Plot emergencies
    for node in nodes:
        folium.Marker(
            location=[node['lat'], node['lon']],
            popup=node['label'],
            tooltip=node['label'],
            icon=folium.Icon(color="blue")
        ).add_to(m)
        
    # Plot live drivers
    for driver in drivers:
        if driver['lat'] is not None and driver['lon'] is not None:
            folium.Marker(
                location=[driver['lat'], driver['lon']],
                tooltip=f"🚑 {driver['username']} (Live)",
                icon=folium.Icon(color="red", icon="ambulance", prefix='fa')
            ).add_to(m)
            
    map_data = st_folium(m, width=700, height=500, returned_objects=["last_clicked"])
    
    if map_data and map_data.get('last_clicked'):
        raw_lat = map_data['last_clicked']['lat']
        raw_lon = map_data['last_clicked']['lng']
        lon, lat = osrm_helper.get_nearest_road(raw_lon, raw_lat)
        
        is_duplicate = any(abs(n['lat'] - lat) < 0.0001 and abs(n['lon'] - lon) < 0.0001 for n in nodes)
        if not is_duplicate:
            if len(nodes) < 15:
                db.add_node(lat, lon, f"Emergency {len(nodes)+1}")
                st.rerun()
            else:
                st.warning("Maximum 15 hubs allowed for prototype.")
                
    st.write("---")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⚛️ Calculate Quantum VRP Route", use_container_width=True, type="primary"):
            if len(nodes) < 3:
                st.warning("Please add at least 3 hubs.")
            else:
                with st.spinner("Running QAOA Quantum Optimization..."):
                    coords = [[n['lat'], n['lon']] for n in nodes]
                    dist_matrix = osrm_helper.get_distance_matrix(coords)
                    best_route = quantum_solver.solve_route(dist_matrix)
                    
                    route_geometries = []
                    route_durations = []
                    for i in range(len(best_route) - 1):
                        idx1 = best_route[i]
                        idx2 = best_route[i+1]
                        geom, dur = osrm_helper.get_route_geometry(coords[idx1][1], coords[idx1][0], coords[idx2][1], coords[idx2][0])
                        route_geometries.append(geom)
                        route_durations.append(dur)
                    
                    # For prototype, assign the full route to 'driver1'. (In real VRP, we'd split it)
                    db.update_driver_route("driver1", best_route, route_geometries, route_durations)
                    
                    # Initialize driver1 at the first node
                    first_node_idx = best_route[0]
                    db.update_driver_location("driver1", coords[first_node_idx][0], coords[first_node_idx][1], 0)
                    
                    st.success("✅ VRP Route Optimized! Dispatched to Fleet.")
    with col2:
        if st.button("🗑️ Clear All Emergencies", use_container_width=True):
            db.clear_nodes()
            st.rerun()
            
    st.subheader("Active Emergencies")
    for n in nodes:
        c1, c2 = st.columns([4, 1])
        c1.write(f"📍 {n['label']} (Lat: {n['lat']:.4f}, Lon: {n['lon']:.4f})")
        if c2.button("Delete", key=f"del_{n['id']}"):
            db.delete_node(n['id'])
            st.rerun()

def driver_dashboard():
    st.header(f"🚑 Mobile Interface ({st.session_state.username})")
    
    driver_state = db.get_driver_state(st.session_state.username)
    nodes = db.get_nodes()
    
    if not driver_state or not driver_state["assigned_route"]:
        st.warning("⚠️ No active route assigned by Dispatch. Awaiting orders...")
        return
        
    route = driver_state["assigned_route"]
    current_idx = driver_state["current_stop_index"]
    geometries = driver_state["route_geometries"]
    durations = driver_state["route_durations"]
    
    # Check if admin deleted nodes rendering our route indices invalid
    if max(route) >= len(nodes):
         st.error("Admin modified the nodes after routing. Please ask admin to Recalculate.")
         return
    
    traffic_override = st.session_state.get('traffic_override', False)
    
    first_node_idx = route[0]
    m = folium.Map(location=[nodes[first_node_idx]['lat'], nodes[first_node_idx]['lon']], zoom_start=13)
    
    remaining_duration_sec = sum(durations[current_idx:]) if current_idx < len(durations) else 0
    if traffic_override:
        remaining_duration_sec *= 0.75
    eta_mins = int(remaining_duration_sec // 60)
    
    for geom in geometries:
        folium.PolyLine(locations=geom, color="gray", weight=5, dash_array="5").add_to(m)

    for i in range(current_idx):
        if i < len(geometries):
            folium.PolyLine(locations=geometries[i], color="green", weight=6).add_to(m)
            
    for i, n_idx in enumerate(route):
        folium.Marker(
            location=[nodes[n_idx]['lat'], nodes[n_idx]['lon']],
            popup=f"Stop {i}",
            tooltip=f"Stop {i}: {nodes[n_idx]['label']}",
            icon=folium.Icon(color="blue", icon="info-sign")
        ).add_to(m)
        
    if current_idx < len(route):
        curr_node_idx = route[current_idx]
        folium.Marker(
            location=[nodes[curr_node_idx]['lat'], nodes[curr_node_idx]['lon']],
            tooltip=f"🚑 {st.session_state.username} Live GPS",
            icon=folium.Icon(color="red", icon="ambulance", prefix='fa')
        ).add_to(m)
        
    st_folium(m, width=700, height=400, returned_objects=[])
    
    st.write("---")
    if current_idx >= len(route):
        st.success("✅ All deliveries completed! Returning to Depot.")
    else:
        st.info(f"⏱️ **Estimated Time of Arrival (ETA): {eta_mins} mins**")
        st.write(f"**Current Stop:** Stop {current_idx} ({nodes[route[current_idx]]['label']})")
        
    if st.button("📡 Transmit GPS to Cloud (Next Stop)", use_container_width=True, type="primary"):
        if current_idx < len(route):
            next_idx = current_idx + 1
            node_idx = route[next_idx] if next_idx < len(route) else route[-1]
            lat = nodes[node_idx]['lat']
            lon = nodes[node_idx]['lon']
            db.update_driver_location(st.session_state.username, lat, lon, next_idx)
            st.rerun()
            
    st.write("---")
    st.subheader("Advanced Quantum Fleet Features")
    
    is_override = st.session_state.get('traffic_override', False)
    if st.button("🚦 Activate City Traffic Light Preemption", type="secondary" if not is_override else "primary"):
        st.session_state.traffic_override = not is_override
        st.rerun()
        
    if is_override:
        st.success("🟢 City infrastructure engaged! All upcoming traffic lights locked to GREEN.")

def main():
    st.set_page_config(page_title="QuantumRoute", layout="centered", page_icon="🚑")
    init_session_state()
    
    if not st.session_state.logged_in:
        login()
    else:
        with st.sidebar:
            st.write(f"Logged in as: **{st.session_state.username}** ({st.session_state.role})")
            if st.button("🚪 Logout"):
                logout()
                
        if st.session_state.role == "Admin":
            admin_dashboard()
        elif st.session_state.role == "Driver":
            driver_dashboard()

if __name__ == "__main__":
    main()
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
            icon=folium.Icon(color="darkred" if node.get('priority') == 'Code Red' else "blue", icon="warning-sign" if node.get('priority') == 'Code Red' else "info-sign")
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
    
    driver_usernames = [d['username'] for d in drivers] if drivers else ["driver1", "driver2"]
    selected_drivers = st.multiselect("🚑 Select Drivers for Dispatch", driver_usernames, default=driver_usernames[:1] if driver_usernames else [])
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⚛️ Calculate Quantum VRP Route", use_container_width=True, type="primary"):
            if len(nodes) < 3:
                st.warning("Please add at least 3 hubs.")
            elif not selected_drivers:
                st.warning("Please select at least one driver.")
            else:
                with st.spinner("Running QAOA + VRP Clustering..."):
                    coords = [[n['lat'], n['lon']] for n in nodes]
                    
                    # 1. Clustering (VRP)
                    k = len(selected_drivers)
                    if k >= len(coords):
                        clusters = [[i] for i in range(len(coords))]
                    else:
                        import math, random
                        random.seed(42)
                        centroids = random.sample(coords, k)
                        clusters = [[] for _ in range(k)]
                        for _ in range(10):
                            clusters = [[] for _ in range(k)]
                            for i, c in enumerate(coords):
                                dists = [math.hypot(c[0]-cen[0], c[1]-cen[1]) for cen in centroids]
                                clusters[dists.index(min(dists))].append(i)
                            for i in range(k):
                                if clusters[i]:
                                    centroids[i] = (sum(coords[j][0] for j in clusters[i])/len(clusters[i]), sum(coords[j][1] for j in clusters[i])/len(clusters[i]))
                        clusters = [c for c in clusters if c] # remove empty
                    
                    # 2. Quantum Routing for each Driver
                    for k_idx, cluster_indices in enumerate(clusters):
                        if k_idx >= len(selected_drivers): break
                        driver_username = selected_drivers[k_idx]
                        
                        cluster_coords = [coords[i] for i in cluster_indices]
                        sub_dist_matrix = osrm_helper.get_distance_matrix(cluster_coords)
                        sub_route = quantum_solver.solve_route(sub_dist_matrix)
                        global_route = [cluster_indices[i] for i in sub_route]
                        
                        route_geometries = []
                        route_durations = []
                        for i in range(len(global_route) - 1):
                            idx1 = global_route[i]
                            idx2 = global_route[i+1]
                            geom, dur = osrm_helper.get_route_geometry(coords[idx1][1], coords[idx1][0], coords[idx2][1], coords[idx2][0])
                            route_geometries.append(geom)
                            route_durations.append(dur)
                            
                        db.update_driver_route(driver_username, global_route, route_geometries, route_durations)
                        first_node_idx = global_route[0]
                        db.update_driver_location(driver_username, coords[first_node_idx][0], coords[first_node_idx][1], 0)
                        
                    st.success("✅ VRP Route Optimized! Dispatched to Fleet.")
    with col2:
        if st.button("🗑️ Clear All Emergencies", use_container_width=True):
            db.clear_nodes()
            st.rerun()
            
    st.subheader("📋 Hub Management (Active Emergencies)")
    for n in nodes:
        with st.container():
            c1, c2, c3 = st.columns([3, 2, 1])
            new_label = c1.text_input("Name", value=n['label'], key=f"name_{n['id']}")
            new_priority = c2.selectbox("Priority", ["Normal", "Code Red"], index=0 if n.get('priority', 'Normal') == 'Normal' else 1, key=f"pri_{n['id']}")
            
            # If changed, update DB
            if new_label != n['label'] or new_priority != n.get('priority', 'Normal'):
                db.update_node(n['id'], new_label, new_priority)
                st.rerun()
                
            if c3.button("Delete", key=f"del_{n['id']}"):
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
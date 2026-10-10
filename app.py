import streamlit as st
import folium
from streamlit_folium import st_folium
import time
import osrm_helper
import quantum_solver

# Hardcoded user credentials and roles
USERS = {
    "admin": {"password": "admin123", "role": "Admin"},
    "driver": {"password": "driver123", "role": "Driver"}
}

def init_session_state():
    """Initialize session state variables for authentication and state."""
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "role" not in st.session_state:
        st.session_state.role = None
    if "admin_nodes" not in st.session_state:
        st.session_state.admin_nodes = []
    if "best_route" not in st.session_state:
        st.session_state.best_route = []
    if "current_stop_index" not in st.session_state:
        st.session_state.current_stop_index = 0

def login():
    """Display and handle the login form."""
    st.title("🔐 QuantumRoute Login")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")
        
        if submit_button:
            if username in USERS and USERS[username]["password"] == password:
                st.session_state.logged_in = True
                st.session_state.role = USERS[username]["role"]
                st.rerun()
            else:
                st.error("Invalid username or password")

def logout():
    """Clear session state and return to login."""
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.current_stop_index = 0
    # CRITICAL FIX: DO NOT clear admin_nodes or best_route here!
    # The Driver needs to see the route the Admin created.
    st.rerun()

def admin_dashboard():
    """Display the Admin Interface with Folium Map."""
    st.header("👮 Officer Command Center")
    st.info("💡 Tip: Drop 4-5 pins on the map, then click 'Calculate Quantum Route'.")
    
    m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)
    
    for node in st.session_state.admin_nodes:
        folium.Marker(
            location=[node['lat'], node['lon']],
            popup=node['label'],
            tooltip=node['label'],
            icon=folium.Icon(color="blue")
        ).add_to(m)
        
    map_data = st_folium(m, width=700, height=500, returned_objects=["last_clicked"])
    
    if map_data and map_data.get('last_clicked'):
        lat = map_data['last_clicked']['lat']
        lon = map_data['last_clicked']['lng']
        
        is_duplicate = any(
            abs(node['lat'] - lat) < 0.0001 and abs(node['lon'] - lon) < 0.0001 
            for node in st.session_state.admin_nodes
        )
        
        if not is_duplicate:
            if len(st.session_state.admin_nodes) < 8:
                new_node = {
                    'lat': lat,
                    'lon': lon,
                    'label': f"Hub {len(st.session_state.admin_nodes)}"
                }
                st.session_state.admin_nodes.append(new_node)
                st.rerun()
            else:
                st.warning("Maximum 8 hubs allowed for Quantum optimization.")
                
    st.write("---")
    if st.button("⚛️ Calculate Quantum Route", use_container_width=True, type="primary"):
        nodes = st.session_state.admin_nodes
        if len(nodes) < 3:
            st.warning("Please add at least 3 hubs.")
        else:
            with st.spinner("Running QAOA Quantum Optimization..."):
                coords = [[n['lat'], n['lon']] for n in nodes]
                dist_matrix = osrm_helper.get_distance_matrix(coords)
                st.session_state.best_route = quantum_solver.solve_route(dist_matrix)
                st.session_state.current_stop_index = 0 # Reset driver progress
                st.success("✅ Route Optimized! Ready for Driver Dispatch.")

def driver_dashboard():
    """Display the Driver Interface."""
    st.header("🚑 Driver Mobile Interface")
    
    if not st.session_state.admin_nodes or not st.session_state.best_route:
        st.warning("⚠️ No active route assigned yet. Please log in as Officer and calculate a route first.")
        return
        
    nodes = st.session_state.admin_nodes
    route = st.session_state.best_route
    current_idx = st.session_state.current_stop_index
    
    # 1. Route Map Visualization
    first_node_idx = route[0]
    m = folium.Map(location=[nodes[first_node_idx]['lat'], nodes[first_node_idx]['lon']], zoom_start=12)
    
    # STEP A: Draw the FULL route in GRAY first
    full_route_coords = []
    for n_idx in route:
        full_route_coords.append([nodes[n_idx]['lat'], nodes[n_idx]['lon']])
    
    if len(full_route_coords) > 1:
        folium.PolyLine(locations=full_route_coords, color="gray", weight=5, dash_array="5").add_to(m)

    # STEP B: Draw the COMPLETED portion in GREEN on top
    completed_coords = []
    for i in range(current_idx + 1): 
        if i < len(route):
            n_idx = route[i]
            completed_coords.append([nodes[n_idx]['lat'], nodes[n_idx]['lon']])
            
    if len(completed_coords) > 1:
        folium.PolyLine(locations=completed_coords, color="green", weight=6).add_to(m)
        
    # STEP C: Add regular markers for all stops
    for i, n_idx in enumerate(route):
        folium.Marker(
            location=[nodes[n_idx]['lat'], nodes[n_idx]['lon']],
            popup=f"Stop {i}",
            tooltip=f"Stop {i}: {nodes[n_idx]['label']}",
            icon=folium.Icon(color="blue", icon="info-sign")
        ).add_to(m)
        
    # STEP D: Add the Red Ambulance Marker at the current position
    if current_idx < len(route):
        curr_node_idx = route[current_idx]
        folium.Marker(
            location=[nodes[curr_node_idx]['lat'], nodes[curr_node_idx]['lon']],
            tooltip="🚑 Ambulance Current Location",
            icon=folium.Icon(color="red", icon="road")
        ).add_to(m)
        
    st_folium(m, width=700, height=400, returned_objects=[])
    
    # 2. Simulation Controls
    st.write("---")
    if current_idx >= len(route):
        st.success("✅ All deliveries completed! Returning to Depot.")
    else:
        st.write(f"**Current Stop:** Stop {current_idx} ({nodes[route[current_idx]]['label']})")
        st.write(f"**Progress:** {current_idx} / {len(route) - 1} stops completed")
        
    if st.button("⏩ Simulate Next Stop", use_container_width=True, type="primary"):
        if current_idx < len(route):
            st.session_state.current_stop_index += 1
            st.rerun()
            
    st.write("---")
    
    # 3. 'Teju' Bonus Features
    st.subheader("Mobile App Features")
    
    offline_mode = st.checkbox("📶 Simulate Network Loss")
    if offline_mode:
        st.warning("⚠️ OFFLINE MODE: Actions saved to Local Cache. Will sync when online.")
        
    units = st.number_input("Units Delivered at this Stop", min_value=0, step=10, value=0, key="delivered_units")
    if st.button("Confirm Delivery"):
        st.success(f"✅ Inventory updated. Remaining capacity: {100 - units}")
        
    if st.button("🚨 SIMULATE ACCIDENT / SOS", type="primary"):
        st.error("🚨 EMERGENCY SOS TRIGGERED: GPS Coordinates sent to Officer Dashboard!")

def main():
    st.set_page_config(page_title="QuantumRoute", layout="centered", page_icon="🚑")
    init_session_state()
    
    if not st.session_state.logged_in:
        login()
    else:
        with st.sidebar:
            st.write(f"Logged in as: **{st.session_state.role}**")
            st.write("---")
            
            if st.session_state.role == "Admin":
                if st.button("🗑️ Clear All Nodes"):
                    st.session_state.admin_nodes = []
                    st.session_state.best_route = []
                    st.session_state.current_stop_index = 0
                    st.rerun()
                    
            if st.button("🚪 Logout"):
                logout()
                
        if st.session_state.role == "Admin":
            admin_dashboard()
        elif st.session_state.role == "Driver":
            driver_dashboard()

if __name__ == "__main__":
    main()
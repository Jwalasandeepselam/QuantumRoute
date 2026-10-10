import streamlit as st
import folium
from streamlit_folium import st_folium
import time

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

def login():
    """Display and handle the login form."""
    st.title("Login")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")
        
        if submit_button:
            # Check if user exists and password matches
            if username in USERS and USERS[username]["password"] == password:
                st.session_state.logged_in = True
                st.session_state.role = USERS[username]["role"]
                st.rerun()  # Refresh to show the appropriate dashboard
            else:
                st.error("Invalid username or password")

def logout():
    """Clear session state and return to login."""
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.admin_nodes = []
    st.session_state.best_route = []
    st.rerun()

def admin_dashboard():
    """Display the Admin Interface with Folium Map."""
    st.header(" Officer Command Center")
    
    # Initialize map centrally. By explicitly asking ONLY for 'last_clicked',
    # st_folium will completely stop re-rendering the app when the user pans or zooms, fixing the blinking!
    m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)
    
    # Add existing markers to the map
    for node in st.session_state.admin_nodes:
        folium.Marker(
            location=[node['lat'], node['lon']],
            popup=node['label'],
            tooltip=node['label']
        ).add_to(m)
        
    # Render the map and ONLY capture last_clicked to prevent pan/zoom blinking
    map_data = st_folium(m, width=700, height=500, returned_objects=["last_clicked"])
    
    # Handle user clicks on the map
    if map_data and map_data.get('last_clicked'):
        lat = map_data['last_clicked']['lat']
        lon = map_data['last_clicked']['lng']
        
        # Check for exact duplicates
        is_duplicate = any(
            node['lat'] == lat and node['lon'] == lon 
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
                st.rerun()  # Redraw map with the new marker
            else:
                st.warning("Maximum 8 hubs allowed for Quantum optimization.")
                
    st.write("---")
    if st.button("⚛️ Calculate Quantum Route", use_container_width=True):
        nodes = st.session_state.admin_nodes
        if len(nodes) < 3:
            st.warning("Please add at least 3 hubs.")
        else:
            with st.spinner("Calculating..."):
                time.sleep(2)
                st.session_state.best_route = list(range(len(nodes)))
                st.success("✅ Route Optimized! (Mock Mode)")

def driver_dashboard():
    """Display the Driver Interface."""
    st.header("🚑 Driver Mobile Interface")
    
    if "current_stop_index" not in st.session_state:
        st.session_state.current_stop_index = 0
        
    if not st.session_state.admin_nodes or not st.session_state.best_route:
        st.info("No active route assigned by Officer yet.")
        return
        
    nodes = st.session_state.admin_nodes
    route = st.session_state.best_route
    current_idx = st.session_state.current_stop_index
    
    # 1. Route Map Visualization
    first_node_idx = route[0]
    m = folium.Map(location=[nodes[first_node_idx]['lat'], nodes[first_node_idx]['lon']], zoom_start=6)
    
    # Completed segments (Green)
    completed_coords = []
    for i in range(min(current_idx + 1, len(route))):
        n_idx = route[i]
        completed_coords.append([nodes[n_idx]['lat'], nodes[n_idx]['lon']])
    if len(completed_coords) > 1:
        folium.PolyLine(locations=completed_coords, color="green", weight=5).add_to(m)
        
    # Remaining segments (Gray)
    remaining_coords = []
    for i in range(min(current_idx, len(route) - 1), len(route)):
        n_idx = route[i]
        remaining_coords.append([nodes[n_idx]['lat'], nodes[n_idx]['lon']])
    if len(remaining_coords) > 1:
        folium.PolyLine(locations=remaining_coords, color="gray", weight=5, dash_array="5").add_to(m)
        
    # Add regular markers
    for i, n_idx in enumerate(route):
        folium.Marker(
            location=[nodes[n_idx]['lat'], nodes[n_idx]['lon']],
            popup=f"Stop {i}",
            tooltip=f"Stop {i}: {nodes[n_idx]['label']}"
        ).add_to(m)
        
    # Ambulance Marker
    if current_idx < len(route):
        curr_node_idx = route[current_idx]
        folium.Marker(
            location=[nodes[curr_node_idx]['lat'], nodes[curr_node_idx]['lon']],
            icon=folium.Icon(color="red", icon="info-sign"),
            tooltip="Ambulance Current Location"
        ).add_to(m)
        
    # returned_objects=[] prevents map interaction from rerunning the app
    st_folium(m, width=700, height=400, returned_objects=[])
    
    # 2. Simulation Controls
    if current_idx >= len(route):
        st.success("✅ All deliveries completed! Returning to Depot.")
    else:
        st.write(f"**Current Stop:** Stop {current_idx} ({nodes[route[current_idx]]['label']})")
        
    if st.button("⏩ Simulate Next Stop", use_container_width=True):
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
        st.error("EMERGENCY SOS TRIGGERED: GPS Coordinates sent to Officer Dashboard!")

def main():
    """Main application flow."""
    # Set up basic page config
    st.set_page_config(page_title="QuantumRoute", layout="centered")
    
    init_session_state()
    
    if not st.session_state.logged_in:
        # Show login screen if not authenticated
        login()
    else:
        # Sidebar available for logged in users
        with st.sidebar:
            st.write(f"Logged in as: **{st.session_state.role}**")
            
            # Sidebar controls for Admin
            if st.session_state.role == "Admin":
                if st.button("Clear All Nodes"):
                    st.session_state.admin_nodes = []
                    st.session_state.best_route = []
                    st.rerun()
                    
            if st.button("Logout"):
                logout()
                
        # Route to the correct dashboard based on role
        if st.session_state.role == "Admin":
            admin_dashboard()
        elif st.session_state.role == "Driver":
            driver_dashboard()

if __name__ == "__main__":
    main()

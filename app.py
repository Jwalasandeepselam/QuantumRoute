import math
import random

import folium
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_folium import st_folium

import db
import osrm_helper
import quantum_solver


def init_state():
    db.init_db()
    for key, value in {"logged_in": False, "username": None, "role": None, "traffic_override": False}.items():
        st.session_state.setdefault(key, value)


def design():
    st.markdown("""<style>
    :root{--p:#f6f3f1;--b:#2b59d1;--m:#cfdaf5;--i:#242424;--g:#4e4d4d;--s:#797776;--a:#cecac8}.stApp{background:var(--p);color:var(--i);font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.block-container{max-width:1432px;padding:0 40px 64px}#MainMenu,footer,header{visibility:hidden}.banner{background:#000;color:var(--p);margin:0 -40px 28px;padding:11px 40px;display:flex;justify-content:space-between;font-size:11px;letter-spacing:.06em;text-transform:uppercase}.nav{display:flex;justify-content:space-between;align-items:center;padding:14px 0 27px;border-bottom:1px solid var(--a)}.brand,.display,.section{font-family:Georgia,serif;font-weight:400;letter-spacing:-.05em}.brand{font-size:28px}.pill{border:1px solid var(--a);border-radius:99px;padding:8px 12px;color:var(--g);font-size:11px}.dot{background:#3aa65e;width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:8px}.eyebrow{color:var(--s);font-size:11px;letter-spacing:.07em;text-transform:uppercase}.display{font-size:clamp(44px,6vw,78px);line-height:1.02;margin:15px 0 20px}.section{font-size:34px;line-height:1.08;margin:8px 0 14px}.blue{color:var(--b)}.copy{color:var(--g);font-size:15px;line-height:1.55;max-width:650px}.hero{padding:66px 0 44px}.panel{border:1px solid var(--a);border-radius:40px;padding:32px;background:#ffffff35;margin:22px 0}.mist{background:var(--m);border-color:transparent}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:28px}.stat{border:1px solid var(--a);border-radius:22px;padding:16px;background:#ffffff45}.stat b{display:block;font:400 27px Georgia,serif;margin-bottom:7px}.stat span{font-size:10px;text-transform:uppercase;color:var(--s);letter-spacing:.05em}.stButton>button{border-radius:99px;border:1px solid var(--i);background:var(--i);color:#fff;font:12px ui-monospace,monospace;letter-spacing:.04em;text-transform:uppercase;min-height:46px}.stButton>button:hover{background:var(--b);border-color:var(--b)}div[data-testid='stTextInput'] input,div[data-testid='stMultiSelect'] div[data-baseweb='select']>div{border-radius:14px;border-color:var(--a);background:transparent}@media(max-width:700px){.block-container{padding:0 20px 40px}.banner{margin:0 -20px 20px;padding:10px 20px}.banner span:last-child{display:none}.stats{grid-template-columns:1fr}.panel{padding:24px;border-radius:28px}}
    </style>""", unsafe_allow_html=True)


def shell(label):
    st.markdown(f'<div class="banner"><span>QuantumRoute / live dispatch interface</span><span>System integrity: nominal</span></div><div class="nav"><span class="brand">QuantumRoute</span><span class="pill"><i class="dot"></i>{label}</span></div>', unsafe_allow_html=True)


def login():
    shell("SECURE ACCESS")
    left, right = st.columns([1.2, .8], gap="large")
    with left:
        st.markdown('<section class="hero"><div class="eyebrow">Emergency logistics, reconciled in real time</div><h1 class="display">Every minute is a <span class="blue">decision.</span></h1><p class="copy">Assign emergency response routes across a fleet, track execution, and retain operational control from one calm interface.</p><div class="stats"><div class="stat"><b>QAOA</b><span>Route solver</span></div><div class="stat"><b>VRP</b><span>Fleet allocation</span></div><div class="stat"><b>LIVE</b><span>Driver telemetry</span></div></div></section>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="panel mist"><div class="eyebrow">Authorized operators</div><h2 class="section">Enter the command layer.</h2>', unsafe_allow_html=True)
        with st.form("login"):
            username = st.text_input("Operator ID", placeholder="admin, driver1, or driver2")
            password = st.text_input("Access key", type="password")
            submit = st.form_submit_button("Enter workspace  →", use_container_width=True)
        st.markdown('<p class="copy" style="font-size:12px">Demo: admin/admin123 or driver1/driver123.</p></div>', unsafe_allow_html=True)
        if submit:
            with db.get_connection() as conn:
                row = conn.execute("SELECT role FROM users WHERE username=? AND password=?", (username, password)).fetchone()
            if row:
                st.session_state.logged_in, st.session_state.username, st.session_state.role = True, username, row[0]
                st.rerun()
            st.error("The operator ID or access key is not recognized.")


def clusters(coords, count):
    if count >= len(coords): return [[i] for i in range(len(coords))]
    random.seed(42); centers = random.sample(coords, count)
    for _ in range(10):
        groups = [[] for _ in centers]
        for index, coordinate in enumerate(coords):
            nearest = min(range(len(centers)), key=lambda i: math.hypot(coordinate[0]-centers[i][0], coordinate[1]-centers[i][1]))
            groups[nearest].append(index)
        for i, group in enumerate(groups):
            if group: centers[i] = (sum(coords[j][0] for j in group)/len(group), sum(coords[j][1] for j in group)/len(group))
    return [group for group in groups if group]


def admin():
    shell("OFFICER COMMAND"); st_autorefresh(interval=3000, key="fleet_refresh")
    nodes, drivers = db.get_nodes(), db.get_all_drivers()
    active = sum(1 for d in drivers if d["lat"] is not None)
    st.markdown(f'<div class="panel mist"><div class="eyebrow">Command center / fleet preparation</div><h1 class="section" style="font-size:42px">Build a route the field team can trust.</h1><p class="copy">Place emergencies, set their priority, and allocate the response fleet across validated road geometry.</p><div class="stats"><div class="stat"><b>{len(nodes)}/15</b><span>Active emergencies</span></div><div class="stat"><b>{len(drivers)}</b><span>Drivers available</span></div><div class="stat"><b>{active}</b><span>Live locations</span></div></div></div>', unsafe_allow_html=True)
    m = folium.Map([20.5937, 78.9629], zoom_start=5, tiles="OpenStreetMap")
    for node in nodes: 
        if node["label"] == "Depot":
            folium.Marker([node["lat"],node["lon"]], tooltip=node["label"], icon=folium.Icon(color="black", icon="home")).add_to(m)
        else:
            folium.Marker([node["lat"],node["lon"]], tooltip=node["label"], icon=folium.Icon(color="darkred" if node["priority"] == "Code Red" else "blue")).add_to(m)
    for driver in drivers:
        state = db.get_driver_state(driver["username"])
        if state and state["route_geometries"]:
            for geom in state["route_geometries"]: folium.PolyLine(geom, color="#8b8b8b", weight=4, dash_array="6").add_to(m)
            for geom in state["route_geometries"][:state["current_stop_index"]]: folium.PolyLine(geom, color="#2b59d1", weight=5).add_to(m)
        if driver["lat"] is not None: folium.Marker([driver["lat"],driver["lon"]], tooltip=f'{driver["username"]} / live', icon=folium.Icon(color="red",icon="ambulance",prefix="fa")).add_to(m)
    clicked = st_folium(m, width=None, height=500, returned_objects=["last_clicked"], key="command_map")
    if clicked and clicked.get("last_clicked"):
        point = clicked["last_clicked"]; lon, lat = osrm_helper.get_nearest_road(point["lng"], point["lat"])
        label = "Depot" if len(nodes) == 0 else f"Emergency {len(nodes)}"
        if len(nodes) < 15 and not any(abs(n["lat"]-lat)<.0001 and abs(n["lon"]-lon)<.0001 for n in nodes): db.add_node(lat, lon, label); st.rerun()
    selected = st.multiselect("Select drivers for dispatch", [d["username"] for d in drivers], default=[d["username"] for d in drivers[:1]])
    a,b = st.columns([3,1]); dispatch = a.button("Calculate fleet route  →", use_container_width=True); clear = b.button("Clear emergencies", use_container_width=True)
    if clear: db.clear_nodes(); st.rerun()
    if dispatch:
        if len(nodes) < 3 or not selected: st.warning("Add a Depot, at least two emergencies, and select a driver.")
        else:
            with st.spinner("Allocating the fleet across the road network…"):
                coords = [[n["lat"],n["lon"]] for n in nodes[1:]]
                for username, group in zip(selected, clusters(coords, len(selected))):
                    group_indices = [0] + [i + 1 for i in group]
                    sub_coords = [[nodes[idx]["lat"], nodes[idx]["lon"]] for idx in group_indices]
                    sub_route = quantum_solver.solve_route(osrm_helper.get_distance_matrix(sub_coords))
                    zero_idx = sub_route.index(0)
                    sub_route = sub_route[zero_idx:] + sub_route[:zero_idx]
                    route = [group_indices[i] for i in sub_route]
                    geoms, durations = [], []
                    for start, end in zip(route, route[1:]):
                        geom, duration = osrm_helper.get_route_geometry(nodes[start]["lon"],nodes[start]["lat"],nodes[end]["lon"],nodes[end]["lat"]); geoms.append(geom); durations.append(duration)
                    db.update_driver_route(username, route, geoms, durations); db.update_driver_location(username, nodes[route[0]]["lat"], nodes[route[0]]["lon"], 0)
            st.success("Fleet routes dispatched.")
    st.markdown('<div class="panel"><div class="eyebrow">Emergency management</div><h2 class="section">Name and prioritize every active incident.</h2></div>', unsafe_allow_html=True)
    for node in nodes:
        x,y,z = st.columns([3,2,1]); name=x.text_input("Incident name",node["label"],key=f'n{node["id"]}'); priority=y.selectbox("Priority",["Normal","Code Red"],index=1 if node["priority"]=="Code Red" else 0,key=f'p{node["id"]}')
        if name != node["label"] or priority != node["priority"]: db.update_node(node["id"],name,priority);st.rerun()
        if z.button("Remove",key=f'd{node["id"]}'):db.delete_node(node["id"]);st.rerun()


def driver():
    shell("DRIVER EXECUTION"); state, nodes = db.get_driver_state(st.session_state.username), db.get_nodes()
    if not state or not state["assigned_route"]:
        st.markdown('<div class="panel mist"><div class="eyebrow">Awaiting command center</div><h1 class="section">No active dispatch has been assigned.</h1><p class="copy">The command team will publish an optimized route before field navigation begins.</p></div>',unsafe_allow_html=True); return
    route,current,geoms,durations = state["assigned_route"],state["current_stop_index"],state["route_geometries"],state["route_durations"]
    if max(route) >= len(nodes): st.error("The emergency network changed. Ask command to recalculate."); return
    remaining=sum(durations[current:]) if current<len(durations) else 0
    if st.session_state.traffic_override: remaining *= .75
    if current >= len(route):
        st.markdown('<div class="panel mist"><div class="eyebrow">Active mission / response sequence</div><h1 class="section" style="font-size:42px">Mission Complete</h1><p class="copy">All deliveries are finished. Returning to depot.</p></div>', unsafe_allow_html=True)
    else:
        label=nodes[route[current]]["label"]
        st.markdown(f'<div class="panel mist"><div class="eyebrow">Active mission / response sequence</div><h1 class="section" style="font-size:42px">Next destination: {label}</h1><div class="stats"><div class="stat"><b>{round(remaining/60)} min</b><span>Arrival estimate</span></div><div class="stat"><b>{max(0,len(route)-current-1)}</b><span>Stops remaining</span></div><div class="stat"><b>{"Priority" if st.session_state.traffic_override else "Standard"}</b><span>Road priority</span></div></div></div>',unsafe_allow_html=True)
    m=folium.Map([nodes[route[0]]["lat"],nodes[route[0]]["lon"]],zoom_start=13,tiles="OpenStreetMap")
    for geom in geoms:folium.PolyLine(geom,color="#8b8b8b",weight=5,dash_array="6").add_to(m)
    for geom in geoms[:current]:folium.PolyLine(geom,color="#2b59d1",weight=6).add_to(m)
    for i,index in enumerate(route):
        if nodes[index]["label"] == "Depot":
            folium.Marker([nodes[index]["lat"],nodes[index]["lon"]],tooltip="Depot (Start)",icon=folium.Icon(color="black", icon="home")).add_to(m)
        else:
            folium.Marker([nodes[index]["lat"],nodes[index]["lon"]],tooltip=f'Stop {i}: {nodes[index]["label"]}',icon=folium.Icon(color="blue")).add_to(m)
    st_folium(m,width=None,height=430,returned_objects=[],key="driver_map")
    a,b=st.columns(2)
    if a.button("Confirm arrival  →",use_container_width=True):
        next_stop=min(current+1,len(route)); index=route[min(next_stop,len(route)-1)]; db.update_driver_location(st.session_state.username,nodes[index]["lat"],nodes[index]["lon"],next_stop);st.rerun()
    if b.button("Deactivate road priority" if st.session_state.traffic_override else "Activate road priority",use_container_width=True):st.session_state.traffic_override=not st.session_state.traffic_override;st.rerun()


def main():
    st.set_page_config(page_title="QuantumRoute — Dispatch",page_icon="◌",layout="wide"); init_state(); design()
    if not st.session_state.logged_in: login()
    elif st.session_state.role == "Admin": admin()
    else: driver()
    if st.session_state.logged_in and st.button("Sign out"): st.session_state.logged_in=False; st.session_state.username=None; st.session_state.role=None; st.rerun()


if __name__ == "__main__": main()

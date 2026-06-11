import argparse
import json
import socket
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog

try:
    import tkintermapview  # type: ignore[import-not-found]
except ImportError:
    tkintermapview = None


raspi_ip = None
raspi_port = None
sock = None
previousBtn = None
reader_thread = None

PROFILES_FILE = Path(__file__).resolve().parent / "route_profiles.json"
profiles_data = {"profiles": []}
active_profile_name = None
active_route_name = None


def load_profiles_from_disk():
    global profiles_data
    if not PROFILES_FILE.exists():
        profiles_data = {"profiles": []}
        return

    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError):
        profiles_data = {"profiles": []}
        return

    if not isinstance(data, dict) or "profiles" not in data or not isinstance(data["profiles"], list):
        profiles_data = {"profiles": []}
        return

    for profile in data["profiles"]:
        profile.setdefault("parkings", [])
        profile.setdefault("destinations", [])
        profile.setdefault("routes", [])
        profile.setdefault("hub", None)
        profile.setdefault("takeOffAlt", 8)
        profile.setdefault("speed", 7)
        for route in profile["routes"]:
            route.setdefault("intermediates", [])

    profiles_data = data


def save_profiles_to_disk():
    try:
        with open(PROFILES_FILE, "w", encoding="utf-8") as fp:
            json.dump(profiles_data, fp, indent=2)
    except OSError as ex:
        messagebox.showerror("Error", "No se pudo guardar route_profiles.json: " + str(ex))


def find_profile(profile_name):
    for profile in profiles_data["profiles"]:
        if profile.get("name") == profile_name:
            return profile
    return None


def find_named_point(points, name):
    for point in points:
        if point.get("name") == name:
            return point
    return None


def build_mission_from_profile(profile, route_name):
    route = None
    for item in profile.get("routes", []):
        if item.get("name") == route_name:
            route = item
            break

    if route is None:
        raise ValueError("Ruta no encontrada")

    parking = find_named_point(profile.get("parkings", []), route.get("parking"))
    destination = find_named_point(profile.get("destinations", []), route.get("destination"))
    hub = profile.get("hub")

    if parking is None:
        raise ValueError("Parking de la ruta no encontrado")
    if destination is None:
        raise ValueError("Destino de la ruta no encontrado")
    if not isinstance(hub, dict):
        raise ValueError("Falta definir el punto HUB comun")

    waypoints = [
        {"lat": float(parking["lat"]), "lon": float(parking["lon"]), "alt": float(parking.get("alt", 8))},
        {"lat": float(hub["lat"]), "lon": float(hub["lon"]), "alt": float(hub.get("alt", 8))},
    ]

    for point in route.get("intermediates", []):
        waypoints.append(
            {
                "lat": float(point["lat"]),
                "lon": float(point["lon"]),
                "alt": float(point.get("alt", hub.get("alt", 8))),
            }
        )

    waypoints.append(
        {"lat": float(destination["lat"]), "lon": float(destination["lon"]), "alt": float(destination.get("alt", 8))}
    )

    return {
        "speed": float(profile.get("speed", 7)),
        "takeOffAlt": float(profile.get("takeOffAlt", 8)),
        "waypoints": waypoints,
    }


def set_route_status(text, color="black"):
    if "routeStatusLbl" in globals() and routeStatusLbl is not None:
        routeStatusLbl["text"] = text
        routeStatusLbl["fg"] = color


def send_message(command, payload=None):
    global sock
    if sock is None:
        return

    message = {
        "type": "command",
        "command": command,
        "payload": payload,
    }

    try:
        sock.sendall((json.dumps(message) + "\n").encode("utf-8"))
    except OSError:
        sock = None
        show_service_disconnected()


def restart():
    time.sleep(5)
    arm_takeOffBtn["text"] = "Armar y Despegar"
    arm_takeOffBtn["fg"] = "black"
    arm_takeOffBtn["bg"] = "dark orange"

    landBtn["text"] = "Aterrizar"
    landBtn["fg"] = "black"
    landBtn["bg"] = "dark orange"

    RTLBtn["text"] = "RTL"
    RTLBtn["fg"] = "black"
    RTLBtn["bg"] = "dark orange"

    if previousBtn:
        previousBtn["fg"] = "black"
        previousBtn["bg"] = "dark orange"


def showTelemetryInfo(telemetry_info):
    altShowLbl["text"] = round(telemetry_info.get("alt", 0), 2)
    headingShowLbl["text"] = round(telemetry_info.get("heading", 0), 2)
    stateShowLbl["text"] = telemetry_info.get("state", "")


def show_service_disconnected():
    connectBtn["text"] = "Servicio desconectado"
    connectBtn["fg"] = "white"
    connectBtn["bg"] = "red"
    set_route_status("Servicio LAN desconectado", "red")


def on_message(message):
    msg_type = message.get("type")

    if msg_type == "telemetry":
        ventana.after(0, showTelemetryInfo, message.get("data", {}))

    if msg_type == "event":
        event = message.get("event")

        if event == "connected":
            connectBtn["text"] = "Dron conectado"
            connectBtn["fg"] = "white"
            connectBtn["bg"] = "green"

        if event == "flying":
            arm_takeOffBtn["text"] = "En el aire"
            arm_takeOffBtn["fg"] = "white"
            arm_takeOffBtn["bg"] = "green"

        if event == "missionUploading":
            set_route_status("Subiendo mision al dron...", "dark orange")

        if event == "missionUploaded":
            set_route_status("Mision subida correctamente", "green")

        if event == "missionStarted":
            set_route_status("Mision iniciada", "green")

        if event == "missionFinished":
            set_route_status("Mision finalizada", "green")

        if event == "landed":
            landBtn["text"] = "En tierra"
            landBtn["fg"] = "white"
            landBtn["bg"] = "green"
            threading.Thread(target=restart, daemon=True).start()

        if event == "atHome":
            RTLBtn["text"] = "En tierra"
            RTLBtn["fg"] = "white"
            RTLBtn["bg"] = "green"
            threading.Thread(target=restart, daemon=True).start()

    if msg_type == "error":
        error_text = str(message.get("message"))
        print("Error del servicio:", error_text)
        set_route_status("Error: " + error_text, "red")


def reader_loop():
    global sock
    local_sock = sock

    try:
        with local_sock.makefile("r", encoding="utf-8", newline="\n") as reader:
            while True:
                try:
                    line = reader.readline()
                except socket.timeout:
                    # Si no llega trafico durante un tiempo, seguimos esperando.
                    continue
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ventana.after(0, on_message, message)
    except OSError:
        pass
    finally:
        if sock is local_sock:
            sock = None
        ventana.after(0, show_service_disconnected)


def connect_service():
    global sock, reader_thread

    if sock is not None:
        return True

    connectBtn["text"] = "Conectando..."
    connectBtn["fg"] = "black"
    connectBtn["bg"] = "yellow"

    try:
        sock = socket.create_connection((raspi_ip, raspi_port), timeout=5)
        sock.settimeout(None)
    except OSError:
        show_service_disconnected()
        return False

    connectBtn["text"] = "Servicio LAN conectado"
    connectBtn["fg"] = "white"
    connectBtn["bg"] = "green"
    set_route_status("Servicio LAN conectado", "green")

    reader_thread = threading.Thread(target=reader_loop, daemon=True)
    reader_thread.start()
    return True


def connect_drone():
    if connect_service():
        send_message("connect")


def takeoff():
    send_message("arm_takeOff")
    arm_takeOffBtn["text"] = "Despegando..."
    arm_takeOffBtn["fg"] = "black"
    arm_takeOffBtn["bg"] = "yellow"


def land():
    send_message("Land")
    landBtn["text"] = "Aterrizando..."
    landBtn["fg"] = "black"
    landBtn["bg"] = "yellow"


def RTL():
    send_message("RTL")
    RTLBtn["text"] = "Retornando..."
    RTLBtn["fg"] = "black"
    RTLBtn["bg"] = "yellow"


def go(direction, btn):
    global previousBtn
    if previousBtn:
        previousBtn["fg"] = "black"
        previousBtn["bg"] = "dark orange"

    send_message("go", direction)
    btn["fg"] = "white"
    btn["bg"] = "green"
    previousBtn = btn


def startTelem():
    send_message("startTelemetry")


def stopTelem():
    send_message("stopTelemetry")


def changeHeading(_event):
    heading_value = int(gradesSldr.get())
    send_message("changeHeading", heading_value)


def changeNavSpeed(_event):
    speed_value = float(speedSldr.get())
    send_message("changeNavSpeed", speed_value)


def crear_ventana():
    global altShowLbl, headingShowLbl, speedSldr, gradesSldr, stateShowLbl
    global connectBtn, arm_takeOffBtn, landBtn, RTLBtn
    global routeStatusLbl
    global previousBtn

    previousBtn = None

    root = tk.Tk()
    root.title("Desktop LAN - Control Remoto via Raspi")
    root.geometry("500x700")

    for i in range(12):
        root.rowconfigure(i, weight=1)
    root.columnconfigure(0, weight=1)
    root.columnconfigure(1, weight=1)

    connectBtn = tk.Button(root, text="Conectar Dron", bg="dark orange", command=connect_drone)
    connectBtn.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    arm_takeOffBtn = tk.Button(root, text="Armar y Despegar", bg="dark orange", command=takeoff)
    arm_takeOffBtn.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    gradesSldr = tk.Scale(root, label="Grados:", resolution=5, from_=0, to=360, tickinterval=45, orient=tk.HORIZONTAL)
    gradesSldr.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)
    gradesSldr.bind("<ButtonRelease-1>", changeHeading)

    landBtn = tk.Button(root, text="Aterrizar", bg="dark orange", command=land)
    landBtn.grid(row=3, column=0, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    RTLBtn = tk.Button(root, text="RTL", bg="dark orange", command=RTL)
    RTLBtn.grid(row=3, column=1, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    navFrame = tk.LabelFrame(root, text="Navegacion")
    navFrame.grid(row=4, column=0, columnspan=2, padx=50, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    for i in range(3):
        navFrame.rowconfigure(i, weight=1)
        navFrame.columnconfigure(i, weight=1)

    NWBtn = tk.Button(navFrame, text="NW", bg="dark orange", command=lambda: go("NorthWest", NWBtn))
    NWBtn.grid(row=0, column=0, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    NoBtn = tk.Button(navFrame, text="No", bg="dark orange", command=lambda: go("North", NoBtn))
    NoBtn.grid(row=0, column=1, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    NEBtn = tk.Button(navFrame, text="NE", bg="dark orange", command=lambda: go("NorthEast", NEBtn))
    NEBtn.grid(row=0, column=2, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    WeBtn = tk.Button(navFrame, text="We", bg="dark orange", command=lambda: go("West", WeBtn))
    WeBtn.grid(row=1, column=0, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    StopBtn = tk.Button(navFrame, text="St", bg="dark orange", command=lambda: go("Stop", StopBtn))
    StopBtn.grid(row=1, column=1, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    EaBtn = tk.Button(navFrame, text="Ea", bg="dark orange", command=lambda: go("East", EaBtn))
    EaBtn.grid(row=1, column=2, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    SWBtn = tk.Button(navFrame, text="SW", bg="dark orange", command=lambda: go("Down", SWBtn))
    SWBtn.grid(row=2, column=0, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    SoBtn = tk.Button(navFrame, text="So", bg="dark orange", command=lambda: go("South", SoBtn))
    SoBtn.grid(row=2, column=1, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    SEBtn = tk.Button(navFrame, text="SE", bg="dark orange", command=lambda: go("Up", SEBtn))
    SEBtn.grid(row=2, column=2, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    speedSldr = tk.Scale(root, label="Velocidad (m/s):", resolution=1, from_=0, to=20, tickinterval=5, orient=tk.HORIZONTAL)
    speedSldr.grid(row=5, column=0, columnspan=2, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)
    speedSldr.bind("<ButtonRelease-1>", changeNavSpeed)

    StartTelemBtn = tk.Button(root, text="Empezar telemetria", bg="dark orange", command=startTelem)
    StartTelemBtn.grid(row=6, column=0, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    StopTelemBtn = tk.Button(root, text="Parar telemetria", bg="dark orange", command=stopTelem)
    StopTelemBtn.grid(row=6, column=1, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    plannerBtn = tk.Button(root, text="Planificador de rutas", bg="light steel blue", command=open_route_planner)
    plannerBtn.grid(row=7, column=0, columnspan=2, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    routeStatusLbl = tk.Label(root, text="Sin ruta activa", fg="black")
    routeStatusLbl.grid(row=8, column=0, columnspan=2, padx=5, pady=2, sticky=tk.W)

    telemetryFrame = tk.LabelFrame(root, text="Telemetria")
    telemetryFrame.grid(row=9, column=0, columnspan=2, padx=10, pady=10, sticky=tk.N + tk.S + tk.E + tk.W)

    telemetryFrame.rowconfigure(0, weight=1)
    telemetryFrame.rowconfigure(1, weight=1)
    telemetryFrame.columnconfigure(0, weight=1)
    telemetryFrame.columnconfigure(1, weight=1)
    telemetryFrame.columnconfigure(2, weight=1)

    altLbl = tk.Label(telemetryFrame, text="Altitud")
    altLbl.grid(row=0, column=0, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    headingLbl = tk.Label(telemetryFrame, text="Heading")
    headingLbl.grid(row=0, column=1, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    stateLbl = tk.Label(telemetryFrame, text="Estado")
    stateLbl.grid(row=0, column=2, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    altShowLbl = tk.Label(telemetryFrame, text="")
    altShowLbl.grid(row=1, column=0, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    headingShowLbl = tk.Label(telemetryFrame, text="")
    headingShowLbl.grid(row=1, column=1, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    stateShowLbl = tk.Label(telemetryFrame, text="")
    stateShowLbl.grid(row=1, column=2, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    return root


def parse_args():
    parser = argparse.ArgumentParser(description="Cliente Desktop por LAN")
    parser.add_argument("--raspi-ip", default="10.237.66.29", help="IP ZeroTier de la Raspi")
    parser.add_argument("--raspi-port", type=int, default=5000, help="Puerto TCP del servicio LAN en la Raspi")
    return parser.parse_args()


def open_route_planner():
    global active_profile_name, active_route_name

    if tkintermapview is None:
        messagebox.showerror(
            "Dependencia faltante",
            "Falta tkintermapview. Instala con: pip install tkintermapview",
        )
        return

    load_profiles_from_disk()

    planner = tk.Toplevel(ventana)
    planner.title("Planificador de rutas y perfiles")
    planner.geometry("1300x760")

    planner.columnconfigure(0, weight=3)
    planner.columnconfigure(1, weight=2)
    planner.rowconfigure(0, weight=1)

    map_frame = tk.LabelFrame(planner, text="Mapa")
    map_frame.grid(row=0, column=0, padx=8, pady=8, sticky=tk.N + tk.S + tk.E + tk.W)
    map_frame.rowconfigure(0, weight=1)
    map_frame.columnconfigure(0, weight=1)

    map_widget = tkintermapview.TkinterMapView(map_frame)
    map_widget.grid(row=0, column=0, sticky=tk.N + tk.S + tk.E + tk.W)
    map_widget.set_tile_server(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        max_zoom=19,
    )
    map_widget.set_position(40.4168, -3.7038)
    map_widget.set_zoom(6)

    control = tk.LabelFrame(planner, text="Perfiles y rutas")
    control.grid(row=0, column=1, padx=8, pady=8, sticky=tk.N + tk.S + tk.E + tk.W)

    for r in range(18):
        control.rowconfigure(r, weight=1)
    control.columnconfigure(0, weight=1)
    control.columnconfigure(1, weight=1)

    marker_refs = []
    path_refs = []

    selected_profile = tk.StringVar(value="")

    tk.Label(control, text="Perfiles").grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=4)
    profiles_list = tk.Listbox(control, height=5, exportselection=False)
    profiles_list.grid(row=1, column=0, columnspan=2, sticky=tk.N + tk.S + tk.E + tk.W, padx=4, pady=2)

    tk.Label(control, text="Parkings").grid(row=2, column=0, sticky=tk.W, padx=4)
    tk.Label(control, text="Destinos").grid(row=2, column=1, sticky=tk.W, padx=4)

    parking_list = tk.Listbox(control, height=5, exportselection=False)
    parking_list.grid(row=3, column=0, sticky=tk.N + tk.S + tk.E + tk.W, padx=4, pady=2)

    destination_list = tk.Listbox(control, height=5, exportselection=False)
    destination_list.grid(row=3, column=1, sticky=tk.N + tk.S + tk.E + tk.W, padx=4, pady=2)

    tk.Label(control, text="Rutas (parking -> hub -> destino)").grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=4)
    routes_list = tk.Listbox(control, height=6, exportselection=False)
    routes_list.grid(row=5, column=0, columnspan=2, sticky=tk.N + tk.S + tk.E + tk.W, padx=4, pady=2)

    tk.Label(control, text="Intermedios de la ruta seleccionada").grid(row=6, column=0, columnspan=2, sticky=tk.W, padx=4)
    intermediates_list = tk.Listbox(control, height=4, exportselection=False)
    intermediates_list.grid(row=7, column=0, columnspan=2, sticky=tk.N + tk.S + tk.E + tk.W, padx=4, pady=2)

    tk.Label(control, text="TakeOff Alt (m)").grid(row=8, column=0, sticky=tk.W, padx=4)
    tk.Label(control, text="Speed (m/s)").grid(row=8, column=1, sticky=tk.W, padx=4)

    takeoff_entry = tk.Entry(control)
    takeoff_entry.grid(row=9, column=0, sticky=tk.E + tk.W, padx=4, pady=2)

    speed_entry = tk.Entry(control)
    speed_entry.grid(row=9, column=1, sticky=tk.E + tk.W, padx=4, pady=2)

    hub_info_lbl = tk.Label(control, text="HUB: no definido", fg="dark orange")
    hub_info_lbl.grid(row=10, column=0, columnspan=2, sticky=tk.W, padx=4)

    status_lbl = tk.Label(control, text="Click derecho en el mapa para agregar puntos.", fg="black")
    status_lbl.grid(row=11, column=0, columnspan=2, sticky=tk.W, padx=4)

    def set_local_status(text, color="black"):
        status_lbl["text"] = text
        status_lbl["fg"] = color

    def get_selected_name(listbox):
        sel = listbox.curselection()
        if not sel:
            return None
        return listbox.get(sel[0])

    def refresh_profiles_list():
        profiles_list.delete(0, tk.END)
        for profile in profiles_data["profiles"]:
            profiles_list.insert(tk.END, profile.get("name", "sin_nombre"))

    def clear_map_objects():
        for marker in marker_refs:
            try:
                marker.delete()
            except Exception:
                pass
        marker_refs.clear()

        for path in path_refs:
            try:
                path.delete()
            except Exception:
                pass
        path_refs.clear()

    def draw_profile_on_map(profile):
        clear_map_objects()

        for point in profile.get("parkings", []):
            marker_refs.append(map_widget.set_marker(point["lat"], point["lon"], text="P: " + point["name"]))

        for point in profile.get("destinations", []):
            marker_refs.append(map_widget.set_marker(point["lat"], point["lon"], text="D: " + point["name"]))

        hub = profile.get("hub")
        if isinstance(hub, dict):
            marker_refs.append(map_widget.set_marker(hub["lat"], hub["lon"], text="HUB"))
            hub_info_lbl["text"] = "HUB: lat={:.6f} lon={:.6f} alt={:.1f}".format(hub["lat"], hub["lon"], hub.get("alt", 8.0))
            hub_info_lbl["fg"] = "green"
            map_widget.set_position(hub["lat"], hub["lon"])
        else:
            hub_info_lbl["text"] = "HUB: no definido"
            hub_info_lbl["fg"] = "dark orange"

        for route in profile.get("routes", []):
            parking = find_named_point(profile.get("parkings", []), route.get("parking"))
            destination = find_named_point(profile.get("destinations", []), route.get("destination"))
            if parking is None or destination is None or not isinstance(hub, dict):
                continue
            route_coords = [
                (parking["lat"], parking["lon"]),
                (hub["lat"], hub["lon"]),
            ]
            for p in route.get("intermediates", []):
                route_coords.append((p["lat"], p["lon"]))
            route_coords.append((destination["lat"], destination["lon"]))
            path_refs.append(map_widget.set_path(route_coords))

    def get_route_by_name(profile, route_name):
        if profile is None:
            return None
        for route in profile.get("routes", []):
            if route.get("name") == route_name:
                return route
        return None

    def refresh_intermediates_list(profile):
        intermediates_list.delete(0, tk.END)
        if profile is None:
            return

        route_name = get_selected_name(routes_list) or active_route_name
        route = get_route_by_name(profile, route_name)
        if route is None:
            return

        for index, point in enumerate(route.get("intermediates", []), start=1):
            label = "I{}: {:.6f}, {:.6f}, alt {:.1f}".format(index, point["lat"], point["lon"], point.get("alt", 8.0))
            intermediates_list.insert(tk.END, label)

    def refresh_profile_details(profile):
        parking_list.delete(0, tk.END)
        destination_list.delete(0, tk.END)
        routes_list.delete(0, tk.END)

        if profile is None:
            takeoff_entry.delete(0, tk.END)
            speed_entry.delete(0, tk.END)
            intermediates_list.delete(0, tk.END)
            hub_info_lbl["text"] = "HUB: no definido"
            hub_info_lbl["fg"] = "dark orange"
            clear_map_objects()
            return

        for point in profile.get("parkings", []):
            parking_list.insert(tk.END, point["name"])

        for point in profile.get("destinations", []):
            destination_list.insert(tk.END, point["name"])

        for route in profile.get("routes", []):
            routes_list.insert(tk.END, route["name"])

        takeoff_entry.delete(0, tk.END)
        takeoff_entry.insert(0, str(profile.get("takeOffAlt", 8)))

        speed_entry.delete(0, tk.END)
        speed_entry.insert(0, str(profile.get("speed", 7)))

        refresh_intermediates_list(profile)
        draw_profile_on_map(profile)

    def update_profile_numeric_fields(profile):
        try:
            profile["takeOffAlt"] = float(takeoff_entry.get())
            profile["speed"] = float(speed_entry.get())
        except ValueError:
            raise ValueError("TakeOffAlt y Speed deben ser numericos")

    def on_select_profile(_event=None):
        global active_profile_name, active_route_name
        profile_name = get_selected_name(profiles_list)
        if not profile_name and selected_profile.get():
            return
        selected_profile.set(profile_name or "")
        active_profile_name = profile_name
        active_route_name = None
        profile = find_profile(profile_name) if profile_name else None
        refresh_profile_details(profile)

    def add_point(point_type, coords):
        profile_name = selected_profile.get()
        if not profile_name:
            set_local_status("Selecciona primero un perfil", "red")
            return

        profile = find_profile(profile_name)
        if profile is None:
            set_local_status("Perfil no encontrado", "red")
            return

        lat, lon = float(coords[0]), float(coords[1])
        name = simpledialog.askstring("Nombre", "Nombre del punto:", parent=planner)
        if not name:
            return

        alt_str = simpledialog.askstring("Altitud", "Altitud relativa (m):", parent=planner, initialvalue="8")
        if not alt_str:
            return
        try:
            alt = float(alt_str)
        except ValueError:
            set_local_status("Altitud invalida", "red")
            return

        new_point = {"name": name.strip(), "lat": lat, "lon": lon, "alt": alt}

        if point_type == "parking":
            if find_named_point(profile.get("parkings", []), new_point["name"]) is not None:
                set_local_status("Ya existe un parking con ese nombre", "red")
                return
            profile.setdefault("parkings", []).append(new_point)

        if point_type == "destination":
            if find_named_point(profile.get("destinations", []), new_point["name"]) is not None:
                set_local_status("Ya existe un destino con ese nombre", "red")
                return
            profile.setdefault("destinations", []).append(new_point)

        refresh_profile_details(profile)
        set_local_status("Punto agregado", "green")

    def set_hub(coords):
        profile_name = selected_profile.get()
        if not profile_name:
            set_local_status("Selecciona primero un perfil", "red")
            return

        profile = find_profile(profile_name)
        if profile is None:
            set_local_status("Perfil no encontrado", "red")
            return

        alt_str = simpledialog.askstring("Altitud HUB", "Altitud del HUB (m):", parent=planner, initialvalue="8")
        if not alt_str:
            return
        try:
            alt = float(alt_str)
        except ValueError:
            set_local_status("Altitud invalida", "red")
            return

        profile["hub"] = {"lat": float(coords[0]), "lon": float(coords[1]), "alt": alt}
        refresh_profile_details(profile)
        set_local_status("HUB actualizado", "green")

    def create_profile():
        profile_name = simpledialog.askstring("Nuevo perfil", "Nombre del perfil:", parent=planner)
        if not profile_name:
            return
        profile_name = profile_name.strip()
        if not profile_name:
            return

        if find_profile(profile_name) is not None:
            set_local_status("Ya existe ese perfil", "red")
            return

        profiles_data["profiles"].append(
            {
                "name": profile_name,
                "takeOffAlt": 8,
                "speed": 7,
                "hub": None,
                "parkings": [],
                "destinations": [],
                "routes": [],
            }
        )
        refresh_profiles_list()
        set_local_status("Perfil creado", "green")

    def delete_profile():
        profile_name = selected_profile.get()
        if not profile_name:
            return

        response = messagebox.askyesno("Confirmar", "Eliminar perfil '" + profile_name + "'?", parent=planner)
        if not response:
            return

        profiles_data["profiles"] = [p for p in profiles_data["profiles"] if p.get("name") != profile_name]
        selected_profile.set("")
        refresh_profiles_list()
        refresh_profile_details(None)
        set_local_status("Perfil eliminado", "green")

    def delete_selected_point(listbox, collection_name):
        profile_name = selected_profile.get()
        if not profile_name:
            return
        profile = find_profile(profile_name)
        if profile is None:
            return

        point_name = get_selected_name(listbox)
        if not point_name:
            return

        profile[collection_name] = [p for p in profile.get(collection_name, []) if p.get("name") != point_name]
        profile["routes"] = [
            route for route in profile.get("routes", [])
            if route.get("parking") != point_name and route.get("destination") != point_name
        ]
        refresh_profile_details(profile)
        set_local_status("Punto eliminado", "green")

    def create_route():
        profile_name = selected_profile.get()
        if not profile_name:
            set_local_status("Selecciona un perfil", "red")
            return
        profile = find_profile(profile_name)
        if profile is None:
            return

        parking_name = get_selected_name(parking_list)
        destination_name = get_selected_name(destination_list)
        if not parking_name or not destination_name:
            set_local_status("Selecciona parking y destino", "red")
            return

        route_name = simpledialog.askstring("Nueva ruta", "Nombre de la ruta:", parent=planner)
        if not route_name:
            return
        route_name = route_name.strip()
        if not route_name:
            return

        for route in profile.get("routes", []):
            if route.get("name") == route_name:
                set_local_status("Ya existe una ruta con ese nombre", "red")
                return

        profile.setdefault("routes", []).append(
            {
                "name": route_name,
                "parking": parking_name,
                "destination": destination_name,
                "intermediates": [],
            }
        )
        refresh_profile_details(profile)
        set_local_status("Ruta creada", "green")

    def delete_route():
        profile_name = selected_profile.get()
        if not profile_name:
            return
        profile = find_profile(profile_name)
        if profile is None:
            return

        route_name = get_selected_name(routes_list)
        if not route_name:
            return

        profile["routes"] = [route for route in profile.get("routes", []) if route.get("name") != route_name]
        refresh_profile_details(profile)
        set_local_status("Ruta eliminada", "green")

    def select_route():
        global active_profile_name, active_route_name
        profile_name = selected_profile.get()
        route_name = get_selected_name(routes_list)
        if not profile_name or not route_name:
            set_local_status("Selecciona perfil y ruta", "red")
            return

        active_profile_name = profile_name
        active_route_name = route_name
        profile = find_profile(profile_name)
        refresh_intermediates_list(profile)
        set_local_status("Ruta activa: " + profile_name + " / " + route_name, "blue")
        set_route_status("Ruta activa: " + profile_name + " / " + route_name, "blue")

    def add_intermediate_to_route(coords):
        profile_name = selected_profile.get()
        route_name = get_selected_name(routes_list)
        if not profile_name or not route_name:
            set_local_status("Selecciona perfil y ruta antes de agregar intermedios", "red")
            return

        profile = find_profile(profile_name)
        route = get_route_by_name(profile, route_name)
        if profile is None or route is None:
            set_local_status("Ruta no encontrada", "red")
            return

        alt_str = simpledialog.askstring("Altitud intermedio", "Altitud del punto intermedio (m):", parent=planner, initialvalue="8")
        if not alt_str:
            return
        try:
            alt = float(alt_str)
        except ValueError:
            set_local_status("Altitud invalida", "red")
            return

        route.setdefault("intermediates", []).append(
            {"lat": float(coords[0]), "lon": float(coords[1]), "alt": alt}
        )

        refresh_profile_details(profile)
        set_local_status("Intermedio agregado", "green")

    def delete_selected_intermediate():
        profile_name = selected_profile.get()
        route_name = get_selected_name(routes_list)
        if not profile_name or not route_name:
            set_local_status("Selecciona perfil y ruta", "red")
            return

        sel = intermediates_list.curselection()
        if not sel:
            set_local_status("Selecciona un intermedio", "red")
            return

        profile = find_profile(profile_name)
        route = get_route_by_name(profile, route_name)
        if route is None:
            return

        index = sel[0]
        if 0 <= index < len(route.get("intermediates", [])):
            del route["intermediates"][index]
            refresh_profile_details(profile)
            set_local_status("Intermedio eliminado", "green")

    def build_selected_mission():
        profile_name = selected_profile.get() or active_profile_name
        route_name = get_selected_name(routes_list) or active_route_name
        if not profile_name or not route_name:
            raise ValueError("Selecciona perfil y ruta")

        profile = find_profile(profile_name)
        if profile is None:
            raise ValueError("Perfil no encontrado")

        update_profile_numeric_fields(profile)
        return build_mission_from_profile(profile, route_name)

    def upload_selected_mission():
        try:
            mission = build_selected_mission()
        except ValueError as ex:
            set_local_status(str(ex), "red")
            return

        if not connect_service():
            set_local_status("No hay conexion con la Raspi", "red")
            return

        send_message("uploadMission", mission)
        set_local_status("Solicitud de subida enviada", "green")

    def start_selected_mission():
        try:
            mission = build_selected_mission()
        except ValueError as ex:
            set_local_status(str(ex), "red")
            return

        if not connect_service():
            set_local_status("No hay conexion con la Raspi", "red")
            return

        send_message("startMission", mission)
        set_local_status("Solicitud de inicio enviada", "green")

    def save_all_profiles():
        profile_name = selected_profile.get()
        if profile_name:
            profile = find_profile(profile_name)
            if profile is not None:
                try:
                    update_profile_numeric_fields(profile)
                except ValueError as ex:
                    set_local_status(str(ex), "red")
                    return
        save_profiles_to_disk()
        set_local_status("Perfiles guardados", "green")

    map_widget.add_right_click_menu_command("Agregar parking", lambda coords: add_point("parking", coords), pass_coords=True)
    map_widget.add_right_click_menu_command("Agregar destino", lambda coords: add_point("destination", coords), pass_coords=True)
    map_widget.add_right_click_menu_command("Definir HUB", set_hub, pass_coords=True)
    map_widget.add_right_click_menu_command("Agregar intermedio a ruta", add_intermediate_to_route, pass_coords=True)

    tk.Button(control, text="Borrar intermedio", command=delete_selected_intermediate).grid(row=12, column=0, columnspan=2, sticky=tk.E + tk.W, padx=4, pady=2)

    tk.Button(control, text="Nuevo perfil", command=create_profile).grid(row=13, column=0, sticky=tk.E + tk.W, padx=4, pady=2)
    tk.Button(control, text="Eliminar perfil", command=delete_profile).grid(row=13, column=1, sticky=tk.E + tk.W, padx=4, pady=2)

    tk.Button(control, text="Borrar parking", command=lambda: delete_selected_point(parking_list, "parkings")).grid(row=14, column=0, sticky=tk.E + tk.W, padx=4, pady=2)
    tk.Button(control, text="Borrar destino", command=lambda: delete_selected_point(destination_list, "destinations")).grid(row=14, column=1, sticky=tk.E + tk.W, padx=4, pady=2)

    tk.Button(control, text="Crear ruta", command=create_route).grid(row=15, column=0, sticky=tk.E + tk.W, padx=4, pady=2)
    tk.Button(control, text="Borrar ruta", command=delete_route).grid(row=15, column=1, sticky=tk.E + tk.W, padx=4, pady=2)

    tk.Button(control, text="Seleccionar ruta activa", command=select_route).grid(row=16, column=0, columnspan=2, sticky=tk.E + tk.W, padx=4, pady=2)

    tk.Button(control, text="Subir mision", command=upload_selected_mission).grid(row=17, column=0, sticky=tk.E + tk.W, padx=4, pady=2)
    tk.Button(control, text="Iniciar mision", command=start_selected_mission).grid(row=17, column=1, sticky=tk.E + tk.W, padx=4, pady=2)

    tk.Button(control, text="Guardar perfiles", command=save_all_profiles).grid(row=18, column=0, sticky=tk.E + tk.W, padx=4, pady=2)
    tk.Button(control, text="Recargar perfiles", command=lambda: (load_profiles_from_disk(), refresh_profiles_list(), set_local_status("Perfiles recargados", "green"))).grid(row=18, column=1, sticky=tk.E + tk.W, padx=4, pady=2)

    profiles_list.bind("<<ListboxSelect>>", on_select_profile)
    routes_list.bind("<<ListboxSelect>>", lambda _e: refresh_intermediates_list(find_profile(selected_profile.get())))

    refresh_profiles_list()


if __name__ == "__main__":
    args = parse_args()
    raspi_ip = args.raspi_ip
    raspi_port = args.raspi_port

    load_profiles_from_disk()

    ventana = crear_ventana()
    ventana.mainloop()

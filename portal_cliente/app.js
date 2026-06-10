const API_BASE = 'http://localhost:8080/api';

const app = {
    client: null,
    orders: [],
    map: null,
    droneMarker: null,
    clientMarker: null,
    routePolyline: null,
    pollInterval: null,

    init() {
        // Init map
        this.map = L.map('map', {
            zoomControl: false,
            attributionControl: false
        }).setView([40.4168, -3.7038], 12);
        
        L.tileLayer('http://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}', {
            maxZoom: 20
        }).addTo(this.map);

        // Custom markers
        const droneIcon = L.divIcon({
            html: '<div style="background:#64b5f6;width:12px;height:12px;border-radius:50%;box-shadow:0 0 10px #64b5f6, 0 0 20px #64b5f6;"></div>',
            className: '',
            iconSize: [12, 12],
            iconAnchor: [6, 6]
        });
        
        const clientIcon = L.divIcon({
            html: '<div style="background:#ba68c8;width:12px;height:12px;border-radius:50%;box-shadow:0 0 10px #ba68c8;"></div>',
            className: '',
            iconSize: [12, 12],
            iconAnchor: [6, 6]
        });

        this.droneMarker = L.marker([0,0], {icon: droneIcon}).addTo(this.map);
        this.clientMarker = L.marker([0,0], {icon: clientIcon}).addTo(this.map);
        this.droneMarker.setOpacity(0);
        this.clientMarker.setOpacity(0);

        // Check stored login
        const stored = localStorage.getItem('drone_client');
        if (stored) {
            try {
                this.client = JSON.parse(stored);
                this.showDashboard();
            } catch (e) {}
        }
    },

    async login(e) {
        e.preventDefault();
        const btn = document.getElementById('btn-login');
        const name = document.getElementById('login-name').value;
        const address = document.getElementById('login-address').value;
        
        btn.disabled = true;
        btn.innerText = "Geocodificando...";

        try {
            const res = await fetch(`${API_BASE}/clients/login`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name, address})
            });
            const data = await res.json();
            
            if (data.error) throw new Error(data.error);
            
            this.client = data.client;
            localStorage.setItem('drone_client', JSON.stringify(this.client));
            this.showDashboard();
        } catch (err) {
            alert("Error: " + err.message);
        } finally {
            btn.disabled = false;
            btn.innerText = "Acceder";
        }
    },

    logout() {
        localStorage.removeItem('drone_client');
        this.client = null;
        if (this.pollInterval) clearInterval(this.pollInterval);
        document.getElementById('nav-user') && (document.getElementById('nav-user').style.display = 'none');
        document.getElementById('dashboard-view').classList.remove('active');
        document.getElementById('login-view').style.display = 'block';
    },

    showDashboard() {
        document.getElementById('login-view').style.display = 'none';
        document.getElementById('dashboard-view').classList.add('active');
        document.getElementById('user-name').innerText = this.client.name;

        // Set client marker
        this.clientMarker.setLatLng([this.client.latitude, this.client.longitude]);
        this.clientMarker.setOpacity(1);
        this.map.setView([this.client.latitude, this.client.longitude], 14);

        setTimeout(() => this.map.invalidateSize(), 100);

        this.fetchOrders();
        
        if (this.pollInterval) clearInterval(this.pollInterval);
        this.pollInterval = setInterval(() => {
            this.fetchOrders();
            this.fetchTelemetry();
        }, 2000);
    },

    createNewOrder() {
        document.getElementById('new-order-form').classList.remove('hidden');
    },

    async submitOrder() {
        const weight = parseFloat(document.getElementById('order-weight').value);
        try {
            const res = await fetch(`${API_BASE}/orders`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    client_id: this.client.id,
                    weight_kg: weight
                })
            });
            const data = await res.json();
            if (data.error) throw new Error(data.error);
            
            document.getElementById('new-order-form').classList.add('hidden');
            this.fetchOrders();
        } catch (err) {
            alert("Error al crear pedido: " + err.message);
        }
    },

    async fetchOrders() {
        try {
            const res = await fetch(`${API_BASE}/orders?client_id=${this.client.id}`);
            const data = await res.json();
            if (data.orders) {
                this.orders = data.orders;
                this.renderOrders();
            }
        } catch (e) {
            console.error(e);
        }
    },

    renderOrders() {
        const list = document.getElementById('orders-list');
        if (this.orders.length === 0) {
            list.innerHTML = '<p style="color:var(--text-muted)">No tienes pedidos aún.</p>';
            return;
        }

        let html = '';
        this.orders.forEach(o => {
            let label = o.status;
            if (o.status === 'en_reparto') label = 'En camino';
            
            html += `
            <div class="order-card">
                <div class="order-info">
                    <span class="order-id">Pedido #${o.id}</span>
                    <span class="order-meta">${o.weight_kg} kg • ${o.assigned_destination_name || 'Ruta auto-asignada'}</span>
                </div>
                <span class="badge ${o.status}">${label}</span>
            </div>
            `;
        });
        list.innerHTML = html;
        
        // Update tracker badge
        const active = this.orders.find(o => o.status === 'en_reparto');
        const badge = document.getElementById('track-status-badge');
        if (active) {
            badge.innerText = active.operational_state || "En reparto";
            badge.className = "badge en_reparto";
            
            if (active.route_waypoints && active.route_waypoints.length > 0) {
                const latlngs = active.route_waypoints.map(wp => [wp.lat, wp.lon]);
                if (this.routePolyline) {
                    this.routePolyline.setLatLngs(latlngs);
                } else {
                    this.routePolyline = L.polyline(latlngs, {color: '#ba68c8', weight: 4, opacity: 0.7, dashArray: '5, 10'}).addTo(this.map);
                }
            }
        } else {
            badge.innerText = "Sin actividad";
            badge.className = "badge";
            this.droneMarker.setOpacity(0);
            if (this.routePolyline) {
                this.map.removeLayer(this.routePolyline);
                this.routePolyline = null;
            }
        }
    },

    async fetchTelemetry() {
        // Only fetch telemetry if there is an active order
        if (!this.orders.find(o => o.status === 'en_reparto')) return;

        try {
            const res = await fetch(`${API_BASE}/drone/telemetry`);
            const data = await res.json();
            
            if (data.telemetry && data.telemetry.lat) {
                const tel = data.telemetry;
                document.getElementById('tel-alt').innerText = (tel.alt || 0).toFixed(1) + ' m';
                document.getElementById('tel-spd').innerText = (tel.groundSpeed || tel.speed || 0).toFixed(1) + ' m/s';
                document.getElementById('tel-hdg').innerText = (tel.heading || 0).toFixed(0) + '°';

                this.droneMarker.setLatLng([tel.lat, tel.lon]);
                this.droneMarker.setOpacity(1);
            }
        } catch (e) {
            console.error(e);
        }
    }
};

window.onload = () => app.init();

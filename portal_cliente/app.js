const API_BASE = '/api';

// Marcador circular grande con borde blanco, glifo y sombra, para que se
// distinga bien sobre la imagen de satélite. glow añade un halo de color.
function makeBadge(color, glyph, size = 28, glow = false) {
    const shadow = glow
        ? `0 0 8px ${color}, 0 0 16px ${color}, 0 2px 5px rgba(0,0,0,.55)`
        : `0 2px 5px rgba(0,0,0,.55)`;
    return L.divIcon({
        className: '',
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
        html: `<div style="width:${size}px;height:${size}px;border-radius:50%;`
            + `background:${color};border:3px solid #fff;box-shadow:${shadow};`
            + `display:flex;align-items:center;justify-content:center;color:#fff;`
            + `font-size:${Math.round(size * 0.5)}px;line-height:1;font-weight:700;">${glyph}</div>`,
    });
}

const app = {
    client: null,
    orders: [],
    map: null,
    droneMarker: null,
    clientMarker: null,
    routeLayer: null,
    pollInterval: null,

    init() {
        // Init map
        this.map = L.map('map', {
            zoomControl: false,
            attributionControl: false
        }).setView([40.4168, -3.7038], 12);

        // Teselas de satélite por HTTPS (en http:// el navegador las bloquea
        // como contenido mixto al servir la web por https).
        L.tileLayer('https://mt0.google.com/vt/lyrs=s&hl=es&x={x}&y={y}&z={z}', {
            maxZoom: 20
        }).addTo(this.map);

        // Capa donde se dibuja la ruta (línea + puntos clave) para poder limpiarla.
        this.routeLayer = L.layerGroup().addTo(this.map);

        // Marcadores grandes y diferenciados: cliente (naranja) y dron (cian con halo).
        this.droneMarker = L.marker([0, 0], {
            icon: makeBadge('#00e5ff', '✈', 32, true), zIndexOffset: 1000,
        }).addTo(this.map);
        this.clientMarker = L.marker([0, 0], {
            icon: makeBadge('#ff7043', '⌂', 30), zIndexOffset: 900,
        }).addTo(this.map);
        this.droneMarker.setOpacity(0);
        this.clientMarker.setOpacity(0);
        this.clientMarker.bindTooltip('Cliente', { direction: 'top', offset: [0, -16] });

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
                this.drawRoute(active.route_waypoints);
            }
        } else {
            badge.innerText = "Sin actividad";
            badge.className = "badge";
            this.droneMarker.setOpacity(0);
            this.routeLayer.clearLayers();
        }
    },

    // Dibuja la ruta del pedido activo: corredor parking→hub→…→destino y el
    // último tramo destino→cliente, con puntos clave grandes y diferenciados.
    drawRoute(waypoints) {
        this.routeLayer.clearLayers();
        const ll = waypoints.map(wp => [wp.lat, wp.lon]);
        if (ll.length < 2) return;

        // Casing blanco debajo para que la línea resalte sobre el satélite.
        L.polyline(ll, { color: '#ffffff', weight: 8, opacity: 0.9 }).addTo(this.routeLayer);
        // Corredor (todo menos el último tramo al cliente) en cian sólido.
        L.polyline(ll.slice(0, -1), { color: '#00bcd4', weight: 5, opacity: 1 }).addTo(this.routeLayer);
        // Último tramo destino→cliente, discontinuo en naranja.
        L.polyline(ll.slice(-2), { color: '#ff7043', weight: 5, opacity: 1, dashArray: '6, 8' }).addTo(this.routeLayer);

        const mark = (pos, color, glyph, label) => {
            L.marker(pos, { icon: makeBadge(color, glyph, 24) })
                .addTo(this.routeLayer)
                .bindTooltip(label, { permanent: true, direction: 'top', offset: [0, -12], className: 'wp-label' });
        };
        mark(ll[0], '#43a047', 'P', 'Parking');                 // origen
        if (ll.length > 3) mark(ll[1], '#fbc02d', 'H', 'HUB');  // hub
        mark(ll[ll.length - 2], '#e53935', '◆', 'Destino');     // destino (antes del cliente)
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

// Solo arranca el portal de cliente si su mapa está en la página (en admin.html
// no existe, allí se reutiliza makeBadge pero no este init).
window.addEventListener('load', () => {
    if (document.getElementById('map')) app.init();
});

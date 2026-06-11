const API_BASE = '/api';

// Icono de dron (quadcopter visto desde arriba) en SVG, para el marcador de
// telemetría. Trazo blanco para que se vea sobre el badge de color.
const DRONE_SVG = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" '
    + 'stroke="#fff" stroke-width="2" stroke-linecap="round">'
    + '<line x1="7" y1="7" x2="17" y2="17"/><line x1="17" y1="7" x2="7" y2="17"/>'
    + '<circle cx="6" cy="6" r="2.6"/><circle cx="18" cy="6" r="2.6"/>'
    + '<circle cx="6" cy="18" r="2.6"/><circle cx="18" cy="18" r="2.6"/>'
    + '<rect x="9.5" y="9.5" width="5" height="5" rx="1"/></svg>';

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
    token: null,
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
            icon: makeBadge('#00e5ff', DRONE_SVG, 34, true), zIndexOffset: 1000,
        }).addTo(this.map);
        this.clientMarker = L.marker([0, 0], {
            icon: makeBadge('#ff7043', '⌂', 30), zIndexOffset: 900,
        }).addTo(this.map);
        this.droneMarker.setOpacity(0);
        this.clientMarker.setOpacity(0);
        this.clientMarker.bindTooltip('Cliente', { direction: 'top', offset: [0, -16] });

        // Sesión guardada (token + cliente)
        this.token = localStorage.getItem('drone_token');
        const stored = localStorage.getItem('drone_client');
        if (this.token && stored) {
            try {
                this.client = JSON.parse(stored);
                this.showDashboard();
            } catch (e) {}
        }
    },

    authHeaders() {
        return { 'Authorization': 'Bearer ' + this.token, 'Content-Type': 'application/json' };
    },

    toggleAuth(e) {
        e.preventDefault();
        const login = document.getElementById('login-form');
        const reg = document.getElementById('register-form');
        const toReg = login.classList.contains('hidden') === false;
        login.classList.toggle('hidden', toReg);
        reg.classList.toggle('hidden', !toReg);
        document.getElementById('auth-subtitle').innerText = toReg ? 'Crea tu cuenta.' : 'Accede a tu cuenta.';
        document.getElementById('toggle-auth').innerText = toReg ? '¿Ya tienes cuenta? Entrar' : '¿No tienes cuenta? Crear una';
    },

    async _authRequest(endpoint, body, btn, busyText) {
        const original = btn.innerText;
        btn.disabled = true;
        btn.innerText = busyText;
        try {
            const res = await fetch(`${API_BASE}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (data.error) throw new Error(data.error);
            this.token = data.token;
            this.client = data.client;
            localStorage.setItem('drone_token', this.token);
            localStorage.setItem('drone_client', JSON.stringify(this.client));
            this.showDashboard();
        } catch (err) {
            UI.alert(err.message, 'Error');
        } finally {
            btn.disabled = false;
            btn.innerText = original;
        }
    },

    login(e) {
        e.preventDefault();
        this._authRequest('/users/login', {
            username: document.getElementById('login-user').value,
            password: document.getElementById('login-pass').value,
        }, document.getElementById('btn-login'), 'Entrando...');
    },

    register(e) {
        e.preventDefault();
        this._authRequest('/users/register', {
            username: document.getElementById('reg-user').value,
            password: document.getElementById('reg-pass').value,
            name: document.getElementById('reg-name').value,
            address: document.getElementById('reg-address').value,
        }, document.getElementById('btn-register'), 'Creando cuenta...');
    },

    logout() {
        localStorage.removeItem('drone_token');
        localStorage.removeItem('drone_client');
        this.client = null;
        this.token = null;
        if (this.pollInterval) clearInterval(this.pollInterval);
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
                headers: this.authHeaders(),
                body: JSON.stringify({ weight_kg: weight }),
            });
            const data = await res.json();
            if (data.error) throw new Error(data.error);

            document.getElementById('new-order-form').classList.add('hidden');
            this.fetchOrders();
        } catch (err) {
            UI.alert(err.message, 'Error al crear pedido');
        }
    },

    async fetchOrders() {
        try {
            const res = await fetch(`${API_BASE}/orders`, { headers: this.authHeaders() });
            if (res.status === 401) return this.logout();
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

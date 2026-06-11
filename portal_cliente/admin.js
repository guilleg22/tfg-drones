// Panel de administración: login, edición de perfiles/rutas sobre el mapa y
// monitorización de pedidos. Reutiliza makeBadge() de app.js.

const admin = {
    token: null,
    data: null,        // documento {profiles:[...]}
    profile: null,     // perfil seleccionado (referencia dentro de data)
    orders: [],
    map: null,
    layer: null,
    pick: null,        // modo de captura de clic en el mapa
    routeDraft: null,  // ruta en construcción
    needsSetup: false,

    async init() {
        this.token = localStorage.getItem('admin_token');
        try {
            const ns = await fetch('/api/admin/needs-setup').then(r => r.json());
            this.needsSetup = !!ns.needs_setup;
        } catch (e) {}
        if (this.needsSetup) {
            document.getElementById('login-subtitle').innerText =
                'No hay administrador. Crea la cuenta de admin.';
            document.getElementById('btn-admin-login').innerText = 'Crear admin';
        }
        if (this.token) this.enterPanel();
    },

    authHeaders() {
        return { 'Authorization': 'Bearer ' + this.token, 'Content-Type': 'application/json' };
    },

    async submitAuth(e) {
        e.preventDefault();
        const username = document.getElementById('admin-user').value.trim();
        const password = document.getElementById('admin-pass').value;
        const ep = this.needsSetup ? '/api/admin/register' : '/api/admin/login';
        try {
            const res = await fetch(ep, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });
            const d = await res.json();
            if (d.error) throw new Error(d.error);
            this.token = d.token;
            localStorage.setItem('admin_token', this.token);
            this.needsSetup = false;
            this.enterPanel();
        } catch (err) {
            UI.alert(err.message, 'Error');
        }
    },

    logout() {
        localStorage.removeItem('admin_token');
        this.token = null;
        document.getElementById('admin-panel-view').classList.remove('active');
        document.getElementById('admin-login-view').style.display = 'block';
    },

    async enterPanel() {
        document.getElementById('admin-login-view').style.display = 'none';
        document.getElementById('admin-panel-view').classList.add('active');
        if (!this.map) this.initMap();
        await this.loadProfiles();
        this.loadFleet();
        // Telemetría del dron en vivo (en local). En cloud el backend es stub.
        if (this.telInterval) clearInterval(this.telInterval);
        this.pollTelemetry();
        this.telInterval = setInterval(() => this.pollTelemetry(), 2000);
    },

    initMap() {
        this.map = L.map('admin-map', { attributionControl: false }).setView([41.283, 1.985], 15);
        L.tileLayer('https://mt0.google.com/vt/lyrs=s&hl=es&x={x}&y={y}&z={z}', { maxZoom: 20 }).addTo(this.map);
        this.layer = L.layerGroup().addTo(this.map);
        this.draftLayer = L.layerGroup().addTo(this.map);  // ruta en construcción
        this.droneMarker = L.marker([0, 0], {
            icon: makeBadge('#00e5ff', DRONE_SVG, 34, true), zIndexOffset: 1000,
        }).addTo(this.map);
        this.droneMarker.setOpacity(0);
        this.map.on('click', (e) => this.onMapClick(e));
        setTimeout(() => this.map.invalidateSize(), 150);
    },

    async pollTelemetry() {
        try {
            const d = await fetch('/api/drone/telemetry').then(r => r.json());
            const tel = d.telemetry || {};
            const overlay = document.getElementById('admin-telemetry');
            const hasFix = tel.lat != null && tel.lon != null;
            const active = d.state && d.state !== 'idle';
            overlay.classList.toggle('hidden', !active && !hasFix);
            document.getElementById('admin-drone-state').innerText = d.state || '—';
            if (hasFix) {
                document.getElementById('adm-tel-alt').innerText = (tel.alt || 0).toFixed(1) + ' m';
                document.getElementById('adm-tel-spd').innerText = (tel.groundSpeed || tel.speed || 0).toFixed(1) + ' m/s';
                document.getElementById('adm-tel-hdg').innerText = (tel.heading || 0).toFixed(0) + '°';
                this.droneMarker.setLatLng([tel.lat, tel.lon]).setOpacity(1);
            } else {
                this.droneMarker.setOpacity(0);
            }
        } catch (e) { /* sin telemetría */ }
    },

    // ── Perfiles ─────────────────────────────────────────────────────────
    async loadProfiles() {
        const res = await fetch('/api/admin/profiles', { headers: this.authHeaders() });
        if (res.status === 401) return this.logout();
        this.data = await res.json();
        const sel = document.getElementById('profile-select');
        sel.innerHTML = this.data.profiles.map(p => `<option>${p.name}</option>`).join('');
        if (this.data.profiles.length) this.selectProfile(this.data.profiles[0].name);
    },

    selectProfile(name) {
        this.profile = this.data.profiles.find(p => p.name === name);
        if (!this.profile) return;
        document.getElementById('profile-select').value = name;
        document.getElementById('profile-speed').value = this.profile.speed ?? 7;
        document.getElementById('profile-takeoff').value = this.profile.takeOffAlt ?? 8;
        this.renderProfile();
        this.drawProfile();
    },

    renderProfile() {
        const p = this.profile;
        document.getElementById('hub-line').innerText = p.hub
            ? `HUB: ${p.hub.lat.toFixed(5)}, ${p.hub.lon.toFixed(5)}` : 'HUB: no definido';
        const row = (label, onDel) =>
            `<li><span>${label}</span><button class="x" onclick="${onDel}">✕</button></li>`;
        document.getElementById('parkings-list').innerHTML =
            (p.parkings || []).map((pk, i) => row(pk.name, `admin.removePoint('parking',${i})`)).join('')
            || '<li class="muted">—</li>';
        document.getElementById('dests-list').innerHTML =
            (p.destinations || []).map((d, i) => row(d.name, `admin.removePoint('destination',${i})`)).join('')
            || '<li class="muted">—</li>';
        document.getElementById('routes-list').innerHTML =
            (p.routes || []).map((r, i) => {
                const n = (r.intermediates || []).length;
                const meta = `${r.parking}→${r.destination}${n ? `, ${n} int.` : ''}`;
                return `<li><span>${r.name} <small>(${meta})</small></span>`
                    + `<span class="li-btns">`
                    + `<button class="x" title="Editar waypoints" onclick="admin.editRoute(${i})">✎</button>`
                    + `<button class="x" title="Borrar" onclick="admin.removeRoute(${i})">✕</button></span></li>`;
            }).join('') || '<li class="muted">—</li>';
    },

    drawProfile() {
        if (!this.layer) return;
        this.layer.clearLayers();
        const p = this.profile;
        if (!p) return;
        const bounds = [];
        (p.parkings || []).forEach(pk => { this.marker([pk.lat, pk.lon], '#43a047', 'P', pk.name); bounds.push([pk.lat, pk.lon]); });
        if (p.hub) { this.marker([p.hub.lat, p.hub.lon], '#fbc02d', 'H', 'HUB'); bounds.push([p.hub.lat, p.hub.lon]); }
        (p.destinations || []).forEach(d => { this.marker([d.lat, d.lon], '#e53935', '◆', d.name); bounds.push([d.lat, d.lon]); });
        (p.routes || []).forEach(r => {
            const pk = (p.parkings || []).find(x => x.name === r.parking);
            const d = (p.destinations || []).find(x => x.name === r.destination);
            if (!pk || !d) return;
            const pts = [[pk.lat, pk.lon]];
            if (p.hub) pts.push([p.hub.lat, p.hub.lon]);
            (r.intermediates || []).forEach(it => pts.push([it.lat, it.lon]));
            pts.push([d.lat, d.lon]);
            L.polyline(pts, { color: '#ffffff', weight: 7, opacity: 0.85 }).addTo(this.layer);
            L.polyline(pts, { color: '#00bcd4', weight: 4, opacity: 1 }).addTo(this.layer);
        });
        if (bounds.length) this.map.fitBounds(bounds, { padding: [50, 50], maxZoom: 16 });
    },

    marker(pos, color, glyph, label) {
        const m = L.marker(pos, { icon: makeBadge(color, glyph, 24) }).addTo(this.layer);
        if (label) m.bindTooltip(label, { permanent: true, direction: 'top', offset: [0, -12], className: 'wp-label' });
        return m;
    },

    // ── Captura de puntos en el mapa ─────────────────────────────────────
    startPick(type) {
        this.pick = { type };
        this.showBanner(type === 'hub' ? 'Haz clic en el mapa para fijar el HUB.' : 'Haz clic en el mapa.');
    },

    async addPointPrompt(kind) {
        const r = await UI.form({
            title: kind === 'parking' ? 'Nuevo parking' : 'Nuevo destino',
            fields: [{ name: 'name', label: 'Nombre' }],
            submitLabel: 'Continuar',
        });
        if (!r || !r.name) return;
        this.pick = { type: 'point', kind, name: r.name };
        this.showBanner(`Haz clic en el mapa para colocar "${r.name}".`);
    },

    onMapClick(e) {
        if (!this.pick || !this.profile) return;
        const lat = e.latlng.lat, lon = e.latlng.lng;
        const p = this.profile;
        if (this.pick.type === 'hub') {
            p.hub = { lat, lon, alt: (p.hub && p.hub.alt) || 20 };
        } else if (this.pick.type === 'point') {
            const pt = { name: this.pick.name, lat, lon, alt: this.pick.kind === 'parking' ? 0 : 15 };
            if (this.pick.kind === 'parking') (p.parkings = p.parkings || []).push(pt);
            else (p.destinations = p.destinations || []).push(pt);
        } else if (this.pick.type === 'intermediate') {
            this.routeDraft.intermediates.push({ lat, lon, alt: (p.hub && p.hub.alt) || 20 });
            this.drawDraft();          // muestra el intermedio en el mapa
            this.renderRouteEditor();  // y en la lista del panel
            return; // sigue en modo intermedio
        }
        this.pick = null;
        this.hideBanner();
        this.renderProfile();
        this.drawProfile();
    },

    // Dibuja la ruta que se está creando (naranja discontinua) con sus
    // intermedios numerados, en una capa aparte para no tocar lo ya guardado.
    drawDraft() {
        if (!this.draftLayer) return;
        this.draftLayer.clearLayers();
        const p = this.profile, dr = this.routeDraft;
        if (!dr) return;
        const pk = (p.parkings || []).find(x => x.name === dr.parking);
        const d = (p.destinations || []).find(x => x.name === dr.destination);
        if (!pk || !d) return;
        const pts = [[pk.lat, pk.lon]];
        if (p.hub) pts.push([p.hub.lat, p.hub.lon]);
        dr.intermediates.forEach(it => pts.push([it.lat, it.lon]));
        pts.push([d.lat, d.lon]);
        L.polyline(pts, { color: '#ff9800', weight: 4, opacity: 0.95, dashArray: '6, 8' }).addTo(this.draftLayer);
        dr.intermediates.forEach((it, i) => {
            L.marker([it.lat, it.lon], { icon: makeBadge('#ff9800', String(i + 1), 22) }).addTo(this.draftLayer);
        });
    },

    removePoint(kind, i) {
        if (kind === 'parking') this.profile.parkings.splice(i, 1);
        else this.profile.destinations.splice(i, 1);
        this.renderProfile();
        this.drawProfile();
    },

    removeRoute(i) {
        this.profile.routes.splice(i, 1);
        this.renderProfile();
        this.drawProfile();
    },

    // ── Creación de ruta ─────────────────────────────────────────────────
    async startRouteCreation() {
        const p = this.profile;
        if (!(p.parkings || []).length || !(p.destinations || []).length)
            return UI.alert('Define al menos un parking y un destino primero.');
        const r = await UI.form({
            title: 'Crear ruta',
            fields: [
                { name: 'name', label: 'Nombre de la ruta' },
                { name: 'parking', label: 'Parking', type: 'select', options: p.parkings.map(x => x.name), value: p.parkings[0].name },
                { name: 'destination', label: 'Destino', type: 'select', options: p.destinations.map(x => x.name), value: p.destinations[0].name },
            ],
            submitLabel: 'Continuar',
        });
        if (!r || !r.name || !r.parking || !r.destination) return;
        this.routeDraft = { name: r.name, parking: r.parking, destination: r.destination, intermediates: [] };
        this.editing = false;   // ruta nueva (se añadirá al terminar)
        this.pick = { type: 'intermediate' };
        this.drawDraft();
        this.renderRouteEditor();
    },

    // Editar una ruta ya guardada: se trabaja sobre el mismo objeto (por
    // referencia), así que añadir/quitar intermedios la modifica in situ.
    editRoute(i) {
        this.routeDraft = this.profile.routes[i];
        this.routeDraft.intermediates = this.routeDraft.intermediates || [];
        this.editing = true;
        this.pick = { type: 'intermediate' };
        this.drawDraft();
        this.renderRouteEditor();
    },

    renderRouteEditor() {
        const dr = this.routeDraft;
        const ed = document.getElementById('route-editor');
        if (!dr) { ed.classList.add('hidden'); return; }
        const items = dr.intermediates.map((it, i) =>
            `<li><span>Intermedio ${i + 1}</span>`
            + `<button class="x" title="Quitar" onclick="admin.removeIntermediate(${i})">✕</button></li>`).join('')
            || '<li class="muted">Sin intermedios. Haz clic en el mapa para añadir.</li>';
        ed.innerHTML = `<div class="re-title">${this.editing ? 'Editando' : 'Nueva ruta'}: `
            + `<b>${dr.name}</b> <small>(${dr.parking}→${dr.destination})</small></div>`
            + `<p class="re-hint">Haz clic en el mapa para añadir waypoints intermedios.</p>`
            + `<ul class="edit-list">${items}</ul>`
            + `<div class="re-actions"><button class="small" onclick="admin.finishRoute()">Hecho</button>`
            + `<button class="secondary small" onclick="admin.cancelPick()">Cancelar</button></div>`;
        ed.classList.remove('hidden');
    },

    removeIntermediate(i) {
        if (!this.routeDraft) return;
        this.routeDraft.intermediates.splice(i, 1);
        this.drawDraft();
        this.renderRouteEditor();
    },

    finishRoute() {
        if (!this.routeDraft) return;
        // Si es nueva, se añade; si se editaba, ya estaba en la lista (referencia).
        if (!this.editing) {
            (this.profile.routes = this.profile.routes || []).push(this.routeDraft);
        }
        this.routeDraft = null;
        this.editing = false;
        this.pick = null;
        this.draftLayer.clearLayers();
        document.getElementById('route-editor').classList.add('hidden');
        this.renderProfile();
        this.drawProfile();
    },

    showBanner(text, withFinish) {
        const b = document.getElementById('pick-banner');
        const action = withFinish
            ? ' <button onclick="admin.finishRoute()">Terminar ruta</button>'
            : ' <button onclick="admin.cancelPick()">Cancelar</button>';
        b.innerHTML = text + action;
        b.classList.remove('hidden');
    },
    hideBanner() { document.getElementById('pick-banner').classList.add('hidden'); },
    cancelPick() {
        this.pick = null;
        this.routeDraft = null;
        this.editing = false;
        this.draftLayer.clearLayers();
        this.hideBanner();
        document.getElementById('route-editor').classList.add('hidden');
        this.drawProfile();
    },

    async saveProfiles() {
        if (this.profile) {
            this.profile.speed = parseFloat(document.getElementById('profile-speed').value) || 7;
            this.profile.takeOffAlt = parseFloat(document.getElementById('profile-takeoff').value) || 8;
        }
        const res = await fetch('/api/admin/profiles', {
            method: 'PUT', headers: this.authHeaders(), body: JSON.stringify(this.data),
        });
        const d = await res.json();
        document.getElementById('routes-status').innerText =
            d.success ? 'Cambios guardados.' : ('Error: ' + (d.error || ''));
    },

    // ── Pedidos / flota ──────────────────────────────────────────────────
    showTab(tab) {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        document.getElementById('tab-routes').classList.toggle('active', tab === 'routes');
        document.getElementById('tab-orders').classList.toggle('active', tab === 'orders');
        if (tab === 'orders') this.loadOrders();
        if (tab === 'routes') this.drawProfile();
    },

    async loadFleet() {
        const res = await fetch('/api/admin/fleet', { headers: this.authHeaders() });
        if (!res.ok) return;
        const d = await res.json();
        document.getElementById('fleet-box').innerHTML = d.fleet.map(f => {
            const c = d.categories[f.category];
            return `<div class="fleet-item"><b>${f.id}</b> <span class="muted">${f.category} · ${c.max_payload_kg}kg · ${c.battery_capacity_wh}Wh</span></div>`;
        }).join('');
    },

    async loadOrders() {
        const res = await fetch('/api/admin/orders', { headers: this.authHeaders() });
        if (res.status === 401) return this.logout();
        const d = await res.json();
        this.orders = d.orders || [];
        const list = document.getElementById('admin-orders-list');
        if (!this.orders.length) { list.innerHTML = '<p class="muted">No hay pedidos.</p>'; return; }
        list.innerHTML = this.orders.map(o => `
            <div class="order-card admin-order" onclick="admin.showOrderRoute(${o.id})">
                <div class="order-info">
                    <span class="order-id">#${o.id} · ${o.client_name || ''}</span>
                    <span class="order-meta">${o.weight_kg}kg · ${o.assigned_destination_name || '—'}
                        · <span class="badge ${o.status}">${o.status}</span></span>
                </div>
                <div class="order-actions" onclick="event.stopPropagation()">
                    <button class="mini" title="Empezar misión" onclick="admin.dispatch(${o.id})">▶ Misión</button>
                    <button class="mini danger" title="Borrar" onclick="admin.deleteOrder(${o.id})">✕</button>
                </div>
            </div>`).join('');
    },

    showOrderRoute(id) {
        const o = this.orders.find(x => x.id === id);
        if (!o || !o.route_waypoints || !o.route_waypoints.length) return;
        this.layer.clearLayers();
        const ll = o.route_waypoints.map(w => [w.lat, w.lon]);
        L.polyline(ll, { color: '#ffffff', weight: 7, opacity: 0.85 }).addTo(this.layer);
        L.polyline(ll.slice(0, -1), { color: '#00bcd4', weight: 4 }).addTo(this.layer);
        L.polyline(ll.slice(-2), { color: '#ff7043', weight: 4, dashArray: '6, 8' }).addTo(this.layer);
        this.marker(ll[0], '#43a047', 'P', 'Parking');
        this.marker(ll[ll.length - 1], '#ff7043', '⌂', o.client_name || 'Cliente');
        this.map.fitBounds(ll, { padding: [50, 50], maxZoom: 16 });
    },

    async deleteOrder(id) {
        if (!(await UI.confirm('¿Borrar el pedido #' + id + '?'))) return;
        await fetch(`/api/admin/orders/${id}`, { method: 'DELETE', headers: this.authHeaders() });
        this.loadOrders();
    },

    async dispatch(id) {
        const res = await fetch(`/api/admin/orders/${id}/dispatch`, { method: 'POST', headers: this.authHeaders() });
        const d = await res.json();
        if (d.error) return UI.alert(d.error, 'Error');
        await UI.alert('Misión iniciada. El estado del pedido se actualizará solo '
            + 'mientras el dron vuela.', 'Misión');
        this.loadOrders();
    },
};

window.addEventListener('load', () => {
    if (document.getElementById('admin-map')) admin.init();
});

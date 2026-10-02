/* Offline location overview. Data uses authenticated HA service responses only. */
const escapeText = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const stamp = value => value ? new Date(value * 1000).toLocaleString() : "Unknown";
const coordinate = (lat, lon) => Number.isFinite(lat) && Number.isFinite(lon) ? `${lat.toFixed(5)}, ${lon.toFixed(5)}` : "No fresh position";

class CamperMeshCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this.mode = "own";
    this.selection = null;
    this.busy = false;
    this.next = 0;
  }
  setConfig(config) { this.config = config; }
  set hass(hass) {
    this._hass = hass;
    if (this.isConnected && Date.now() >= this.next) this.refresh();
  }
  getCardSize() { return 8; }
  connectedCallback() {
    this.timer = setInterval(() => this.refresh(), 60000);
    this.refresh();
  }
  disconnectedCallback() { clearInterval(this.timer); }
  async refresh() {
    if (!this._hass || !this.isConnected || this.busy) return;
    this.busy = true;
    this.next = Date.now() + 60000;
    try {
      const response = await this._hass.callWS({type: "call_service", domain: "camper_mesh", service: "history", service_data: {limit: 200}, return_response: true});
      this.data = response.response;
      this.error = null;
    } catch (_) {
      this.error = "Mesh history unavailable. Check the companion integration and local configuration.";
    } finally {
      this.busy = false;
      if (this.isConnected) this.render();
    }
  }
  map(data) {
    const all = data.nodes || [];
    const nodes = this.selection ? all.filter(n => n.node === this.selection) : all;
    // For a selected repeat radio, show its individual recorded encounters.
    const history = this.selection ? (data.encounters || []).filter(e => e.node === parseInt(this.selection.slice(1), 16)) : nodes;
    const points = history.map(n => ({lat: n[this.mode + "_lat"], lon: n[this.mode + "_lon"], repeat: (all.find(x => x.node === this.selection) || n).sessions > 1,
      label: `${n.name || this.selection || "Radio"} | ${stamp(n.last)} | ${this.mode === "own" ? "Camper reception position" : "Radio reported position"}`
    })).filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lon));
    const route = this.mode === "own" ? (data.route || []).slice().reverse().map(p => ({lat: p.latitude, lon: p.longitude})).filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lon)) : [];
    const extent = [...points, ...route];
    if (!extent.length) return "<p>No fresh GPS coordinates recorded yet.</p>";
    const lats = extent.map(p => p.lat), lons = extent.map(p => p.lon);
    const minLat = Math.min(...lats), maxLat = Math.max(...lats), minLon = Math.min(...lons), maxLon = Math.max(...lons);
    const x = lon => 25 + (lon - minLon) / Math.max(maxLon - minLon, 0.0001) * 450;
    const y = lat => 25 + (maxLat - lat) / Math.max(maxLat - minLat, 0.0001) * 200;
    return `<svg viewBox="0 0 500 250" role="img" aria-label="Offline coordinate overview">
      <rect width="500" height="250" fill="var(--secondary-background-color,#eee)"/>
      <polyline points="${route.map(p => `${x(p.lon)},${y(p.lat)}`).join(" ")}" fill="none" stroke="var(--primary-color,#0288d1)" stroke-width="2"/>
      ${points.map(p => `<circle cx="${x(p.lon)}" cy="${y(p.lat)}" r="6" fill="${p.repeat ? "#e67e22" : "#158465"}"><title>${escapeText(p.label)}</title></circle>`).join("")}
      <text x="10" y="245" fill="var(--primary-text-color,#222)" font-size="10">${escapeText(coordinate(minLat, minLon))} → ${escapeText(coordinate(maxLat, maxLon))}</text>
    </svg><p class="small">Coordinate overview; no street tiles or Internet needed. Blue: camper route. Orange: repeated radio encounter. Axes rescale independently; distances are not to scale.</p>`;
  }
  render() {
    const d = this.data || {nodes: [], count: 0, repeats: 0};
    this.shadowRoot.innerHTML = `<style>
      ha-card { padding: 16px; color: var(--primary-text-color); }
      h2 { font-size: 20px; margin: 0 0 12px; } p { margin: 8px 0; }
      .small { font-size: 12px; color: var(--secondary-text-color); }
      button { font: inherit; cursor: pointer; padding: 8px; margin: 4px 4px 4px 0; max-width: 100%; overflow-wrap: anywhere; text-align: left; border: 1px solid var(--divider-color,#ccc); border-radius: 8px; background: var(--card-background-color); color: inherit; }
      .scroll { max-height: 480px; overflow: auto; } .radio { border-top: 1px solid var(--divider-color,#ccc); padding: 10px 0; }
      .repeat { border-left: 4px solid #e67e22; padding-left: 8px; } svg { width: 100%; }
    </style><ha-card><h2>Mesh encounters and GPS</h2>
      <p>${escapeText(this.error || d.status || "Loading…")} · ${escapeText(d.count)} radios · ${escapeText(d.repeats)} repeated</p>
      <p class="small">Heard through the mesh does not mean nearby. A repeat identifies a radio ID, not a person. Names and remote positions are advertised claims.</p>
      <button id="own">Camper reception locations</button><button id="remote">Reported radio locations</button><button id="clear">All radios</button>
      <p>${escapeText(this.mode === "own" ? "Camper reception locations" : "Reported radio locations")}${this.selection ? " · " + escapeText(this.selection) : ""}</p>
      ${this.map(d)}
      <div class="scroll">${(d.nodes || []).map(n => `<div class="radio ${n.sessions > 1 ? "repeat" : ""}">
        <button data-node="${escapeText(n.node)}">${escapeText(n.name)} · ${escapeText(n.node)}</button>
        <p>${escapeText(n.sessions)} encounters · last ${escapeText(stamp(n.last))}</p>
        <p class="small">First seen ${escapeText(stamp(n.first_seen))} · ${escapeText(n.via)} · RSSI ${escapeText(n.rssi ?? "unknown")}</p>
        <p class="small">Camper: ${escapeText(coordinate(n.own_lat, n.own_lon))} (${escapeText(stamp(n.own_time))})<br>
          Reported: ${escapeText(coordinate(n.remote_lat, n.remote_lon))} (${escapeText(stamp(n.remote_time))}); precision ${escapeText(n.precision_bits ?? "unknown")} bits</p>
      </div>`).join("") || "<p>No live radio receptions recorded. Historical node caches are not counted as new encounters.</p>"}</div>
    </ha-card>`;
    for (const mode of ["own", "remote"]) this.shadowRoot.getElementById(mode).onclick = () => { this.mode = mode; this.render(); };
    this.shadowRoot.getElementById("clear").onclick = () => { this.selection = null; this.render(); };
    this.shadowRoot.querySelectorAll("[data-node]").forEach(button => { button.onclick = () => { this.selection = button.dataset.node; this.render(); }; });
  }
}
if (!customElements.get("camper-mesh-card")) customElements.define("camper-mesh-card", CamperMeshCard);

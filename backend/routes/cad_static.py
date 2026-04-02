"""Serve the CAD web interface as a single-page app from the backend.

This eliminates the need for users to install Node.js or run a separate
dev server. The CAD is served at the root URL (http://localhost:8000/).
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["cad"])


@router.get("/", response_class=HTMLResponse)
async def cad_index():
    """Serve the CAD single-page application."""
    return CAD_HTML


# Inline the entire CAD as a single HTML file with embedded JS.
# This avoids needing to bundle React — we use a lightweight vanilla JS approach.
CAD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LSPDFR CAD System</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #1a1a2e; color: #e0e0e0; }
  .header { background: #16213e; padding: 12px 20px; display: flex; align-items: center; gap: 16px; border-bottom: 2px solid #0f3460; }
  .header h1 { font-size: 18px; color: #00d4ff; }
  .header .status { font-size: 12px; padding: 4px 8px; border-radius: 4px; }
  .status.connected { background: #0a3d0a; color: #4caf50; }
  .status.disconnected { background: #3d0a0a; color: #f44336; }
  .tabs { display: flex; background: #16213e; border-bottom: 1px solid #0f3460; }
  .tab { padding: 10px 20px; cursor: pointer; border: none; background: none; color: #888; font-size: 14px; }
  .tab.active { color: #00d4ff; border-bottom: 2px solid #00d4ff; }
  .tab:hover { color: #ccc; }
  .content { padding: 20px; max-width: 1200px; margin: 0 auto; }
  table { width: 100%; border-collapse: collapse; margin-top: 12px; }
  th { background: #16213e; padding: 10px; text-align: left; font-size: 13px; color: #888; }
  td { padding: 10px; border-bottom: 1px solid #2a2a4a; font-size: 13px; }
  tr.priority-1 { border-left: 4px solid #f44336; }
  tr.priority-2 { border-left: 4px solid #ff9800; }
  tr.priority-3 { border-left: 4px solid #4caf50; }
  tr:hover { background: #1e1e3a; cursor: pointer; }
  input, select { background: #2a2a4a; border: 1px solid #3a3a5a; color: #e0e0e0; padding: 8px 12px; border-radius: 4px; font-size: 13px; }
  input:focus { border-color: #00d4ff; outline: none; }
  button { background: #0f3460; color: #e0e0e0; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
  button:hover { background: #1a4a8a; }
  .search-bar { display: flex; gap: 8px; margin-bottom: 16px; }
  .search-bar input { flex: 1; }
  .card { background: #16213e; border: 1px solid #2a2a4a; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
  .card h3 { color: #00d4ff; margin-bottom: 8px; }
  .card p { margin: 4px 0; font-size: 13px; }
  .card label { color: #888; }
  .form-group { display: flex; flex-direction: column; gap: 8px; max-width: 400px; margin-bottom: 16px; }
  .success { color: #4caf50; }
  .error { color: #f44336; }
  .detail-panel { background: #0d1b2a; border: 1px solid #1b2838; border-radius: 8px; padding: 16px; margin-top: 8px; }
  .bolo-alert { background: #3d1a0a; border: 1px solid #f44336; border-radius: 8px; padding: 12px; margin-bottom: 8px; animation: flash 1s; }
  @keyframes flash { 0%,100% { opacity: 1; } 50% { opacity: 0.7; } }
  h2 { color: #00d4ff; margin-bottom: 16px; font-size: 16px; }
</style>
</head>
<body>
<div class="header">
  <h1>LSPDFR CAD System</h1>
  <span id="ws-status" class="status disconnected">Disconnected</span>
</div>
<div class="tabs">
  <button class="tab active" onclick="showTab('calls')">Call Board</button>
  <button class="tab" onclick="showTab('persons')">Person Search</button>
  <button class="tab" onclick="showTab('vehicles')">Vehicle Search</button>
  <button class="tab" onclick="showTab('warrants')">Warrants</button>
  <button class="tab" onclick="showTab('citations')">New Citation</button>
</div>
<div class="content" id="content"></div>

<script>
const API = '';
let ws = null;
let calls = [];
let bolos = [];
let currentTab = 'calls';

// --- WebSocket ---
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(proto + '//' + location.host + '/ws/cad?api_key=dispatch-secret');
  ws.onopen = () => { document.getElementById('ws-status').className = 'status connected'; document.getElementById('ws-status').textContent = 'Connected'; };
  ws.onclose = () => { document.getElementById('ws-status').className = 'status disconnected'; document.getElementById('ws-status').textContent = 'Disconnected'; setTimeout(connectWS, 3000); };
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'call_update') { upsertCall(msg.call); if (currentTab === 'calls') renderCalls(); }
      if (msg.type === 'status_update') { /* could update unit status display */ }
      if (msg.type === 'bolo_alert') { bolos.unshift(msg.bolo); if (currentTab === 'calls') renderCalls(); }
    } catch {}
  };
}
connectWS();

function upsertCall(call) {
  const idx = calls.findIndex(c => c._id === call._id);
  if (idx >= 0) calls[idx] = call; else calls.push(call);
  calls.sort((a, b) => a.priority - b.priority);
}

// --- API helpers ---
async function api(path, opts) {
  const r = await fetch(API + path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// --- Tab navigation ---
function showTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  render();
}

function render() {
  const c = document.getElementById('content');
  if (currentTab === 'calls') renderCalls();
  else if (currentTab === 'persons') renderPersonSearch();
  else if (currentTab === 'vehicles') renderVehicleSearch();
  else if (currentTab === 'warrants') renderWarrants();
  else if (currentTab === 'citations') renderCitationForm();
}

// --- Call Board ---
async function renderCalls() {
  if (calls.length === 0) { try { calls = await api('/api/calls'); calls.sort((a,b) => a.priority - b.priority); } catch {} }
  const c = document.getElementById('content');
  const priorityColor = p => p === 1 ? '#f44336' : p === 2 ? '#ff9800' : '#4caf50';
  let html = '<h2>Active Calls</h2>';
  if (bolos.length > 0) {
    html += bolos.map(b => '<div class="bolo-alert"><strong>BOLO:</strong> ' + esc(b.description) + (b.suspect_description ? ' — Suspect: ' + esc(b.suspect_description) : '') + '</div>').join('');
  }
  html += '<table><thead><tr><th>Call #</th><th>Type</th><th>Priority</th><th>Location</th><th>Units</th><th>Status</th></tr></thead><tbody>';
  for (const call of calls) {
    html += '<tr class="priority-' + call.priority + '" onclick="showCallDetail(\\'' + call._id + '\\')">';
    html += '<td>' + esc(call.call_number||'—') + '</td>';
    html += '<td>' + esc(call.type) + '</td>';
    html += '<td style="color:' + priorityColor(call.priority) + '">' + call.priority + '</td>';
    html += '<td>' + esc(call.location?.street||'Unknown') + '</td>';
    html += '<td>' + (call.assigned_units?.join(', ')||'—') + '</td>';
    html += '<td>' + esc(call.status) + '</td></tr>';
  }
  html += '</tbody></table>';
  html += '<div id="call-detail"></div>';
  if (calls.length === 0) html += '<p style="margin-top:12px;color:#888">No active calls.</p>';
  c.innerHTML = html;
}

function showCallDetail(id) {
  const call = calls.find(c => c._id === id);
  if (!call) return;
  const d = document.getElementById('call-detail');
  let html = '<div class="detail-panel">';
  html += '<h3>Call #' + esc(call.call_number||'') + ' — ' + esc(call.type) + '</h3>';
  html += '<p><label>Description:</label> ' + esc(call.description||'') + '</p>';
  if (call.suspect_description) html += '<p><label>Suspect:</label> ' + esc(call.suspect_description) + '</p>';
  html += '<p><label>Status:</label> ' + esc(call.status) + '</p>';
  html += '<p><label>Created:</label> ' + new Date(call.created_at).toLocaleString() + '</p>';
  html += '<h4 style="margin-top:12px;color:#888">Notes</h4>';
  if (call.notes?.length) { call.notes.forEach(n => { html += '<p><em>' + new Date(n.timestamp).toLocaleString() + '</em> — <strong>' + esc(n.author) + ':</strong> ' + esc(n.text) + '</p>'; }); }
  else html += '<p style="color:#666">No notes.</p>';
  html += '<div style="margin-top:12px;display:flex;gap:8px"><input id="note-author" placeholder="Author" style="width:120px"><input id="note-text" placeholder="Add note..." style="flex:1"><button onclick="addNote(\\'' + id + '\\')">Add</button></div>';
  html += '<div style="margin-top:8px;display:flex;gap:8px"><input id="disposition" placeholder="Disposition" value="' + esc(call.disposition||'') + '"><button onclick="setDisposition(\\'' + id + '\\')">Update</button></div>';
  html += '</div>';
  d.innerHTML = html;
}

async function addNote(id) {
  const text = document.getElementById('note-text').value;
  const author = document.getElementById('note-author').value;
  if (!text || !author) return;
  try { const updated = await api('/api/calls/' + id, { method: 'PUT', body: JSON.stringify({ note: { text, author } }) }); upsertCall(updated); renderCalls(); } catch {}
}

async function setDisposition(id) {
  const d = document.getElementById('disposition').value;
  if (!d) return;
  try { const updated = await api('/api/calls/' + id, { method: 'PUT', body: JSON.stringify({ disposition: d }) }); upsertCall(updated); renderCalls(); } catch {}
}

// --- Person Search ---
function renderPersonSearch() {
  document.getElementById('content').innerHTML = '<h2>Person Search</h2><div class="search-bar"><input id="person-q" placeholder="Name or DOB (YYYY-MM-DD)"><button onclick="searchPersons()">Search</button></div><div id="person-results"></div>';
}
async function searchPersons() {
  const q = document.getElementById('person-q').value;
  if (!q) return;
  try {
    const results = await api('/api/persons?q=' + encodeURIComponent(q));
    document.getElementById('person-results').innerHTML = results.length === 0 ? '<p style="color:#888">No results.</p>' :
      results.map(p => '<div class="card"><h3>' + esc(p.name) + '</h3><p><label>DOB:</label> ' + esc(p.date_of_birth) + '</p><p><label>License:</label> ' + esc(p.license_status) + '</p><p><label>Description:</label> ' + esc(p.physical_description?.gender||'') + ', ' + esc(p.physical_description?.race||'') + ', ' + esc(p.physical_description?.height||'') + '</p>' + (p.prior_offenses?.length ? '<p><label>Priors:</label> ' + p.prior_offenses.map(o => esc(o.offense)).join(', ') + '</p>' : '') + (p.active_warrants?.length ? '<p style="color:#f44336"><strong>Active Warrants: ' + p.active_warrants.length + '</strong></p>' : '') + '</div>').join('');
  } catch (e) { document.getElementById('person-results').innerHTML = '<p class="error">' + esc(e.message) + '</p>'; }
}

// --- Vehicle Search ---
function renderVehicleSearch() {
  document.getElementById('content').innerHTML = '<h2>Vehicle Search</h2><div class="search-bar"><input id="vehicle-q" placeholder="Plate, make, or model"><button onclick="searchVehicles()">Search</button></div><div id="vehicle-results"></div>';
}
async function searchVehicles() {
  const q = document.getElementById('vehicle-q').value;
  if (!q) return;
  try {
    const results = await api('/api/vehicles?q=' + encodeURIComponent(q));
    document.getElementById('vehicle-results').innerHTML = results.length === 0 ? '<p style="color:#888">No results.</p>' :
      results.map(v => '<div class="card"><h3>' + esc(v.plate) + '</h3><p><label>Make:</label> ' + esc(v.make) + ' <label>Model:</label> ' + esc(v.model) + ' <label>Color:</label> ' + esc(v.color) + '</p><p><label>Owner:</label> ' + esc(v.registered_owner) + '</p>' + (v.flags?.length ? '<p style="color:#f44336"><strong>Flags:</strong> ' + v.flags.map(esc).join(', ') + '</p>' : '') + '</div>').join('');
  } catch (e) { document.getElementById('vehicle-results').innerHTML = '<p class="error">' + esc(e.message) + '</p>'; }
}

// --- Warrants ---
function renderWarrants() {
  document.getElementById('content').innerHTML = '<h2>Active Warrants</h2><div class="search-bar"><input id="w-name" placeholder="Person name"><input id="w-charge" placeholder="Charge"><button onclick="searchWarrants()">Filter</button></div><div id="warrant-results">Loading...</div><hr style="margin:20px 0;border-color:#2a2a4a"><h2>Create Warrant</h2><div class="form-group"><input id="nw-name" placeholder="Person Name"><input id="nw-charge" placeholder="Charge"><input id="nw-authority" placeholder="Issuing Authority"><button onclick="createWarrant()">Create Warrant</button><p id="nw-msg"></p></div>';
  searchWarrants();
}
async function searchWarrants() {
  try {
    const params = new URLSearchParams({ active: 'true' });
    const name = document.getElementById('w-name')?.value; if (name) params.set('person_name', name);
    const charge = document.getElementById('w-charge')?.value; if (charge) params.set('charge', charge);
    const results = await api('/api/warrants?' + params);
    document.getElementById('warrant-results').innerHTML = results.length === 0 ? '<p style="color:#888">No active warrants.</p>' :
      '<table><thead><tr><th>Person</th><th>Charge</th><th>Authority</th><th>Date</th><th></th></tr></thead><tbody>' +
      results.map(w => '<tr><td>' + esc(w.person_name) + '</td><td>' + esc(w.charge) + '</td><td>' + esc(w.issuing_authority) + '</td><td>' + new Date(w.date_issued).toLocaleDateString() + '</td><td><button onclick="serveWarrant(\\'' + w._id + '\\')">Serve</button></td></tr>').join('') + '</tbody></table>';
  } catch {}
}
async function serveWarrant(id) { try { await api('/api/warrants/' + id + '/serve', { method: 'PUT' }); searchWarrants(); } catch {} }
async function createWarrant() {
  try {
    await api('/api/warrants', { method: 'POST', body: JSON.stringify({ person_name: document.getElementById('nw-name').value, charge: document.getElementById('nw-charge').value, issuing_authority: document.getElementById('nw-authority').value, date_issued: new Date().toISOString() }) });
    document.getElementById('nw-msg').innerHTML = '<span class="success">Warrant created.</span>';
    searchWarrants();
  } catch (e) { document.getElementById('nw-msg').innerHTML = '<span class="error">' + esc(e.message) + '</span>'; }
}

// --- Citation Form ---
function renderCitationForm() {
  document.getElementById('content').innerHTML = '<h2>Create Citation</h2><div class="form-group"><input id="c-name" placeholder="Person Name"><input id="c-violation" placeholder="Violation Type"><input id="c-location" placeholder="Location"><input id="c-callsign" placeholder="Officer Callsign"><button onclick="createCitation()">Create Citation</button><p id="c-msg"></p></div>';
}
async function createCitation() {
  try {
    await api('/api/citations', { method: 'POST', body: JSON.stringify({ person_name: document.getElementById('c-name').value, violation_type: document.getElementById('c-violation').value, location: document.getElementById('c-location').value, date: new Date().toISOString(), officer_callsign: document.getElementById('c-callsign').value }) });
    document.getElementById('c-msg').innerHTML = '<span class="success">Citation created.</span>';
  } catch (e) { document.getElementById('c-msg').innerHTML = '<span class="error">' + esc(e.message) + '</span>'; }
}

function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; }

// Initial render
render();
</script>
</body>
</html>"""

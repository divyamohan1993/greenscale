'use strict';

const API = '/api';

function $(id) { return document.getElementById(id); }
function fmt(n, d=1) { return Number(n).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }); }
function esc(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function ciColour(g) {
    const t = Math.min(1, Math.max(0, g / 700));
    const h = (1 - t) * 120;
    return `hsl(${h}, 70%, 45%)`;
}
function toast(msg, isErr=false) {
    const t = $('toast');
    t.textContent = msg;
    t.classList.toggle('error', isErr);
    t.classList.add('show');
    clearTimeout(t._h);
    t._h = setTimeout(() => t.classList.remove('show'), 3000);
}

// ---- map -----------------------------------------------------------------

let map, regionLayer = {}, userMarker, requestLine;
function initMap() {
    map = L.map('map', {
        center: [20, 20], zoom: 2, minZoom: 2, maxZoom: 6,
        worldCopyJump: true, attributionControl: true,
    });
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap &copy; CartoDB',
        subdomains: 'abcd', maxZoom: 8,
    }).addTo(map);
}

function renderRegions(regions) {
    for (const r of regions) {
        const colour = ciColour(r.ci_g_per_kwh);
        const radius = 7 + (r.ci_g_per_kwh / 100);
        if (regionLayer[r.region]) {
            regionLayer[r.region].setStyle({ fillColor: colour, color: colour });
            regionLayer[r.region].setRadius(radius);
        } else {
            const m = L.circleMarker([r.lat, r.lon], {
                radius, color: colour, fillColor: colour,
                fillOpacity: 0.65, weight: 2,
            }).addTo(map);
            m.bindPopup(() => regionPopup(r));
            regionLayer[r.region] = m;
        }
    }
}
function regionPopup(r) {
    return `<b>${esc(r.display)}</b><br/>
        region: <code>${esc(r.region)}</code><br/>
        carbon: <b>${fmt(r.ci_g_per_kwh,0)}</b> gCO<sub>2</sub>/kWh<br/>
        rtt: ${fmt(r.rtt_ms,0)} ms<br/>
        cold P: ${fmt(r.cold_p*100,0)}%<br/>
        cost: $${Number(r.cost_usd_hr).toFixed(4)}/hr`;
}

// ---- region list (DOM-built, no innerHTML for dynamic data) -------------

function renderRegionList(regions) {
    const el = $('region-list');
    el.replaceChildren();
    regions
        .slice()
        .sort((a,b) => a.ci_g_per_kwh - b.ci_g_per_kwh)
        .forEach(r => {
            const colour = ciColour(r.ci_g_per_kwh);
            const row = document.createElement('div');
            row.className = 'region-row';
            row.dataset.region = r.region;

            const dot = document.createElement('div');
            dot.className = 'region-dot';
            dot.style.background = colour; dot.style.color = colour;

            const mid = document.createElement('div');
            const name = document.createElement('div');
            name.className = 'region-name'; name.textContent = r.display;
            const meta = document.createElement('div');
            meta.className = 'region-meta';
            meta.textContent = `${r.region} - rtt ${fmt(r.rtt_ms,0)}ms - cold ${fmt(r.cold_p*100,0)}%`;
            mid.append(name, meta);

            const ci = document.createElement('div');
            ci.className = 'region-ci'; ci.textContent = fmt(r.ci_g_per_kwh,0);

            row.append(dot, mid, ci);
            el.appendChild(row);
        });
    $('ts-regions').textContent = new Date().toLocaleTimeString();
}

// ---- charts --------------------------------------------------------------

let chartCi, chartScore;
function chartTheme() {
    Chart.defaults.color = '#94a3b8';
    Chart.defaults.borderColor = '#1f2937';
    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.font.size = 11;
}

function renderCiChart(regions) {
    const labels = regions.map(r => r.display);
    const data = regions.map(r => r.ci_g_per_kwh);
    const colours = regions.map(r => ciColour(r.ci_g_per_kwh));
    if (!chartCi) {
        chartCi = new Chart($('chart-ci'), {
            type: 'bar',
            data: { labels, datasets: [{ data, backgroundColor: colours, borderRadius: 4, barThickness: 22 }] },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: {
                    callbacks: { label: (c) => `${fmt(c.raw,0)} gCO2/kWh` }
                } },
                scales: {
                    x: { ticks: { autoSkip: false, maxRotation: 25, minRotation: 25 }, grid: { display: false } },
                    y: { beginAtZero: true, suggestedMax: 800, title: { display: true, text: 'gCO2/kWh' } },
                },
            },
        });
    } else {
        chartCi.data.labels = labels;
        chartCi.data.datasets[0].data = data;
        chartCi.data.datasets[0].backgroundColor = colours;
        chartCi.update('none');
    }
}

function renderScoreChart(decision) {
    const candidates = decision.candidates;
    const labels = candidates.map(c => c.display);
    const lat    = candidates.map(c => c.score_breakdown.lat);
    const carbon = candidates.map(c => c.score_breakdown.carbon);
    const cold   = candidates.map(c => c.score_breakdown.cold);
    const cost   = candidates.map(c => c.score_breakdown.cost);
    const data = {
        labels,
        datasets: [
            { label: 'latency',    data: lat,    backgroundColor: '#60a5fa' },
            { label: 'carbon',     data: carbon, backgroundColor: '#4ade80' },
            { label: 'cold-start', data: cold,   backgroundColor: '#f59e0b' },
            { label: 'cost',       data: cost,   backgroundColor: '#a78bfa' },
        ],
    };
    if (!chartScore) {
        chartScore = new Chart($('chart-score'), {
            type: 'bar', data,
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { position: 'top', labels: { boxWidth: 10, padding: 8 } } },
                scales: {
                    x: { stacked: true, ticks: { autoSkip: false, maxRotation: 25, minRotation: 25 }, grid: { display: false } },
                    y: { stacked: true, beginAtZero: true, title: { display: true, text: 'weighted score (lower = chosen)' } },
                },
            },
        });
    } else {
        chartScore.data = data;
        chartScore.update('none');
    }
}

// ---- decisions feed (DOM-built) ------------------------------------------

function renderDecisions(decisions) {
    const el = $('decisions');
    el.replaceChildren();
    if (!decisions.length) {
        const div = document.createElement('div');
        div.style.cssText = 'color:var(--muted);font-size:12px;padding:14px 0;';
        div.textContent = 'No decisions yet. Click "Route a request" or wait for activity.';
        el.appendChild(div);
        return;
    }
    decisions.forEach(d => {
        const same = d.chosen_region === d.baseline_region;
        const row = document.createElement('div');
        row.className = 'decision';

        const arrow = document.createElement('div');
        arrow.className = 'decision-arrow' + (same ? ' same' : '');
        arrow.textContent = same ? '=' : '→';

        const mid = document.createElement('div');
        const text = document.createElement('div');
        text.className = 'decision-text';
        if (same) {
            const b = document.createElement('b'); b.textContent = d.chosen_region;
            text.append(b, document.createTextNode(' (latency-optimal)'));
        } else {
            const baseSpan = document.createElement('span');
            baseSpan.className = 'baseline'; baseSpan.textContent = d.baseline_region;
            const arrowText = document.createTextNode(' → ');
            const chosenB = document.createElement('b'); chosenB.textContent = d.chosen_region;
            text.append(baseSpan, arrowText, chosenB);
        }
        const meta = document.createElement('div');
        meta.className = 'decision-meta';
        const ts = new Date(d.ts).toLocaleTimeString();
        meta.textContent = `${ts} - ${(d.reason || '').slice(0,80)}`;
        mid.append(text, meta);

        const saved = document.createElement('div');
        saved.className = 'decision-saved';
        const sg = Number(d.carbon_saved_g || 0);
        saved.textContent = same ? '0.00g' : (sg >= 0 ? `+${sg.toFixed(2)}g` : `${sg.toFixed(2)}g`);

        row.append(arrow, mid, saved);
        el.appendChild(row);
    });
}

// ---- stats ---------------------------------------------------------------

function renderStats(stats) {
    if (!stats || !stats.connected) return;
    $('s-total').textContent = fmt(stats.total_requests || 0, 0);
    $('s-saved').textContent = `${fmt(stats.total_carbon_saved_g || 0, 3)} g`;
    $('s-reroutes').textContent = fmt(stats.reroutes || 0, 0);
    $('s-overhead').textContent = `${fmt(stats.avg_latency_overhead_ms || 0, 0)} ms`;
}

// ---- API -----------------------------------------------------------------

async function jget(path) {
    const r = await fetch(API + path, { credentials: 'omit' });
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.json();
}
async function jpost(path, body) {
    const r = await fetch(API + path, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${r.status} ${path}: ${await r.text()}`);
    return r.json();
}

// ---- weights -------------------------------------------------------------

function readWeights() {
    return {
        lat:    parseFloat($('w-lat').value),
        carbon: parseFloat($('w-carbon').value),
        cold:   parseFloat($('w-cold').value),
        cost:   parseFloat($('w-cost').value),
    };
}
function bindWeights() {
    for (const k of ['lat','carbon','cold','cost']) {
        const input = $('w-' + k), label = $('wv-' + k);
        input.addEventListener('input', () => { label.textContent = parseFloat(input.value).toFixed(2); });
    }
}

// ---- demo ----------------------------------------------------------------

function drawRequestArc(userLat, userLon, region) {
    if (requestLine) map.removeLayer(requestLine);
    if (userMarker)  map.removeLayer(userMarker);
    userMarker = L.circleMarker([userLat, userLon], {
        radius: 6, color: '#60a5fa', fillColor: '#60a5fa', fillOpacity: 0.8, weight: 2,
    }).addTo(map);
    requestLine = L.polyline([[userLat, userLon], [region.lat, region.lon]], {
        color: '#4ade80', weight: 2, opacity: 0.8, dashArray: '4,4',
    }).addTo(map);
}

async function runDemo() {
    const lat = parseFloat($('lat').value);
    const lon = parseFloat($('lon').value);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) { toast('Invalid lat/lon', true); return; }
    const btn = $('btn-go'); btn.disabled = true; btn.textContent = 'Routing...';
    try {
        const d = await jpost('/v1/demo-request', { user_lat: lat, user_lon: lon, weights: readWeights() });
        drawRequestArc(lat, lon, { lat: d.chosen.lat, lon: d.chosen.lon });
        toast(`${d.chosen.display} chosen - ${d.reason}`);
        renderScoreChart(d);
        await refreshAll();
    } catch (e) {
        toast(String(e.message || e), true);
    } finally {
        btn.disabled = false; btn.textContent = 'Route a request';
    }
}

function bindUI() {
    $('btn-go').addEventListener('click', runDemo);
    document.querySelectorAll('.demo-presets button').forEach(b =>
        b.addEventListener('click', () => {
            $('lat').value = b.dataset.lat;
            $('lon').value = b.dataset.lon;
        }));
}

// ---- refresh loop --------------------------------------------------------

async function refreshRegions() {
    const lat = parseFloat($('lat').value) || 19.0760;
    const lon = parseFloat($('lon').value) || 72.8777;
    try {
        const r = await jget(`/v1/regions?user_lat=${lat}&user_lon=${lon}`);
        renderRegions(r.regions);
        renderRegionList(r.regions);
        renderCiChart(r.regions);
    } catch (e) {
        toast('region snapshot failed: ' + e.message, true);
    }
}
async function refreshDecisions() {
    try {
        const d = await jget('/v1/decisions/recent?limit=20');
        renderDecisions(d.decisions || []);
    } catch (e) { /* db may be cold */ }
}
async function refreshStats() {
    try {
        const s = await jget('/v1/stats');
        renderStats(s);
    } catch (e) { /* db may be cold */ }
}
async function refreshAll() {
    await Promise.all([refreshRegions(), refreshDecisions(), refreshStats()]);
}

document.addEventListener('DOMContentLoaded', async () => {
    chartTheme();
    initMap();
    bindWeights();
    bindUI();
    await refreshAll();
    setInterval(refreshRegions, 8000);
    setInterval(refreshDecisions, 6000);
    setInterval(refreshStats, 12000);
});

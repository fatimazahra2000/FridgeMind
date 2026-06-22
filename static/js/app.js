// ---- STATE ----
let allProducts = [];
let wasteChart = null;
let expiryChart = null;
let scannerInstance = null;
let scannerActive = false;
let editingId = null;
let liveInterval = null;

// ---- TOAST ----
function showToast(msg, type = 'info') {
  const icons = { success: '✅', danger: '❌', warning: '⚠️', info: 'ℹ️' };
  const c = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.innerHTML = `<span>${icons[type] || '•'}</span><span>${msg}</span>`;
  c.appendChild(t);
  setTimeout(() => {
    t.style.animation = 'slideOut .25s ease forwards';
    setTimeout(() => t.remove(), 250);
  }, 3500);
}

// ---- NAVIGATION ----
function showPage(id) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll(`.nav-btn[data-page="${id}"]`).forEach(b => b.classList.add('active'));

  const titles = {
    'page-dashboard': 'Dashboard',
    'page-stock': 'Stock',
    'page-scanner': 'Scanner QR / Code-barres',
  };
  document.getElementById('topbarTitle').textContent = titles[id] || '';

  if (id === 'page-scanner') {
    initScanner();
    document.getElementById('toggleScanBtn').textContent = 'Arreter la camera';
  } else {
    stopScanner().then(() => {
      if (document.getElementById('toggleScanBtn'))
        document.getElementById('toggleScanBtn').textContent = 'Demarrer la camera';
    });
  }
}

// ---- LOAD KPIs ----
async function loadKPIs() {
  const res = await fetch('/api/kpis');
  const data = await res.json();

  document.getElementById('totalProducts').textContent = data.total;
  document.getElementById('expiredProducts').textContent = data.expired;
  document.getElementById('nearExpiryProducts').textContent = data.near;
  document.getElementById('wasteCost').textContent = data.waste.toFixed(2) + ' DH';

  // Update nav badge
  const badge = document.getElementById('alertBadge');
  const alertCount = data.expired + data.near;
  badge.textContent = alertCount;
  badge.classList.toggle('show', alertCount > 0);

  // Alert banners
  const expiredBanner = document.getElementById('expiredBanner');
  const nearBanner = document.getElementById('nearBanner');
  expiredBanner.classList.toggle('show', data.expired > 0);
  nearBanner.classList.toggle('show', data.near > 0);
  if (data.expired > 0) expiredBanner.querySelector('span').textContent = `⛔ ${data.expired} product(s) are expired — remove them immediately.`;
  if (data.near > 0) nearBanner.querySelector('span').textContent = `⚠️ ${data.near} product(s) expire within 7 days.`;

  // Charts
  updateCharts(data, allProducts);
}

// ---- CHARTS ----
function updateCharts(kpiData, products) {
  // Waste chart (bar)
  const wasteCtx = document.getElementById('wasteChart').getContext('2d');
  if (wasteChart) wasteChart.destroy();
  wasteChart = new Chart(wasteCtx, {
    type: 'bar',
    data: {
      labels: kpiData.chart_labels.length ? kpiData.chart_labels : ['No data'],
      datasets: [{
        label: 'Value at risk (DH)',
        data: kpiData.chart_values.length ? kpiData.chart_values : [0],
        backgroundColor: kpiData.chart_labels.map((_, i) =>
          `hsla(${200 + i * 30}, 80%, 55%, 0.85)`),
        borderRadius: 6,
        borderSkipped: false,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, grid: { color: '#F1F5F9' }, ticks: { font: { size: 11 } } },
        x: { grid: { display: false }, ticks: { font: { size: 11 } } }
      }
    }
  });

  // Expiry status doughnut
  const expiryCtx = document.getElementById('expiryChart').getContext('2d');
  if (expiryChart) expiryChart.destroy();
  const ok = kpiData.total - kpiData.expired - kpiData.near;
  expiryChart = new Chart(expiryCtx, {
    type: 'doughnut',
    data: {
      labels: ['OK', 'Expiring soon', 'Expired'],
      datasets: [{
        data: [Math.max(ok, 0), kpiData.near, kpiData.expired],
        backgroundColor: ['#10B981', '#F59E0B', '#EF4444'],
        borderWidth: 0,
        hoverOffset: 6
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 11 }, padding: 12, boxWidth: 12 } }
      }
    }
  });
}

// ---- LOAD PRODUCTS ----
async function loadProducts() {
  const res = await fetch('/api/products');
  allProducts = await res.json();
  renderTable(allProducts);
}

async function refreshAll() {
  const btn = document.getElementById('refreshBtn');
  if (btn) { btn.textContent = '↻ ...'; btn.disabled = true; }
  await loadProducts();
  await loadKPIs();
  if (btn) { btn.textContent = '↻ Refresh'; btn.disabled = false; }
  showToast('Stock mis a jour', 'success');
}

function renderTable(products) {
  const tbody = document.getElementById('stockTable');
  if (!products.length) {
    tbody.innerHTML = `<tr><td colspan="7">
      <div class="empty-state">
        <div class="empty-icon">📦</div>
        <h3>No products yet</h3>
        <p>Add your first product to get started.</p>
      </div>
    </td></tr>`;
    return;
  }
  const today = new Date();
  today.setHours(0,0,0,0);
  tbody.innerHTML = products.map(p => {
    const exp = new Date(p.expiry);
    const diff = Math.round((exp - today) / 86400000);
    let badge = '', rowClass = '';
    if (diff < 0) {
      badge = `<span class="badge badge-expired">🔴 Expired</span>`;
      rowClass = 'style="background:#FFF5F5"';
    } else if (diff <= 7) {
      badge = `<span class="badge badge-near">🟡 ${diff}d left</span>`;
      rowClass = 'style="background:#FFFBEB"';
    } else {
      badge = `<span class="badge badge-ok">🟢 OK</span>`;
    }
    return `<tr ${rowClass}>
      <td class="product-name">${p.name}</td>
      <td>${p.qty}</td>
      <td>${parseFloat(p.price).toFixed(2)} DH</td>
      <td>${p.expiry}</td>
      <td><code style="font-size:11px;background:#F1F5F9;padding:2px 6px;border-radius:4px">${p.barcode || '—'}</code></td>
      <td>${badge}</td>
      <td>
        <div style="display:flex;gap:6px">
          <button class="btn btn-outline btn-sm" onclick="openEdit(${p.id})">✏️ Edit</button>
          <button class="btn btn-danger btn-sm" onclick="deleteProduct(${p.id})">🗑️</button>
        </div>
      </td>
    </tr>`;
  }).join('');
}

// ---- SEARCH ----
function filterTable() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  const filtered = allProducts.filter(p =>
    p.name.toLowerCase().includes(q) ||
    (p.barcode || '').toLowerCase().includes(q)
  );
  renderTable(filtered);
}

// ---- MODAL ----
function openAddModal() {
  editingId = null;
  document.getElementById('modalTitle').textContent = 'Add Product';
  document.getElementById('inp-name').value = '';
  document.getElementById('inp-qty').value = '1';
  document.getElementById('inp-price').value = '0';
  document.getElementById('inp-expiry').value = '';
  document.getElementById('inp-barcode').value = '';
  document.getElementById('modalOverlay').classList.add('open');
}

function openEdit(id) {
  const p = allProducts.find(x => x.id === id);
  if (!p) return;
  editingId = id;
  document.getElementById('modalTitle').textContent = 'Edit Product';
  document.getElementById('inp-name').value = p.name;
  document.getElementById('inp-qty').value = p.qty;
  document.getElementById('inp-price').value = p.price;
  document.getElementById('inp-expiry').value = p.expiry;
  document.getElementById('inp-barcode').value = p.barcode || '';
  document.getElementById('modalOverlay').classList.add('open');
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('open');
  editingId = null;
}

async function saveProduct() {
  const data = {
    name: document.getElementById('inp-name').value.trim(),
    qty: parseInt(document.getElementById('inp-qty').value),
    price: parseFloat(document.getElementById('inp-price').value),
    expiry: document.getElementById('inp-expiry').value,
    barcode: document.getElementById('inp-barcode').value.trim()
  };
  if (!data.name || !data.expiry) { showToast('Please fill required fields', 'warning'); return; }

  try {
    if (editingId) {
      await fetch(`/api/products/${editingId}`, {
        method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
      });
      showToast('Product updated', 'success');
    } else {
      await fetch('/api/products', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
      });
      showToast('Product added', 'success');
    }
    closeModal();
    await loadProducts();
    await loadKPIs();
  } catch(e) {
    showToast('Error saving product', 'danger');
  }
}

async function deleteProduct(id) {
  if (!confirm('Delete this product?')) return;
  await fetch(`/api/products/${id}`, { method: 'DELETE' });
  showToast('Product deleted', 'warning');
  await loadProducts();
  await loadKPIs();
}

// ---- EXPORT PDF ----
async function exportPDF() {
  showToast('Generating PDF…', 'info');
  const a = document.createElement('a');
  a.href = '/api/export/pdf';
  a.download = 'fridge_report.pdf';
  a.click();
}

// ---- SCANNER ----
let lastScannedCode = null;
let scanCooldown = false;

function initScanner() {
  if (scannerActive) return;

  const container = document.getElementById('reader');
  container.innerHTML = '';
  document.getElementById('scanResult').className = 'scan-result';
  document.getElementById('scanResult').textContent = 'Pointez la camera vers un code-barres ou QR code...';
  document.getElementById('scanDetail').innerHTML = '<p style="color:var(--text-muted);font-size:13px">Le resultat apparaitra ici.</p>';

  scannerInstance = new Html5Qrcode('reader');

  const config = {
    fps: 15,
    qrbox: { width: 280, height: 160 },  // rectangle pour EAN-13
    formatsToSupport: [
      Html5QrcodeSupportedFormats.QR_CODE,
      Html5QrcodeSupportedFormats.EAN_13,
      Html5QrcodeSupportedFormats.EAN_8,
      Html5QrcodeSupportedFormats.CODE_128,
      Html5QrcodeSupportedFormats.CODE_39,
      Html5QrcodeSupportedFormats.UPC_A,
      Html5QrcodeSupportedFormats.UPC_E,
    ],
    aspectRatio: 1.5,
    disableFlip: false,
  };

  scannerInstance.start(
    { facingMode: 'environment' },
    config,
    async (decodedText, decodedResult) => {
      // anti-double scan — ignore si même code dans les 3 secondes
      if (scanCooldown && decodedText === lastScannedCode) return;
      lastScannedCode = decodedText;
      scanCooldown = true;
      setTimeout(() => { scanCooldown = false; }, 3000);

      document.getElementById('scannedCode').textContent = 'Code detecte : ' + decodedText;
      await lookupBarcode(decodedText);
    },
    () => {} // erreurs frame ignorees silencieusement
  ).then(() => {
    scannerActive = true;
    document.getElementById('scanStatus').textContent = 'Camera active';
    document.getElementById('scanStatus').style.color = 'var(--success)';
  }).catch(err => {
    showToast('Camera inaccessible — verifie les permissions', 'danger');
    document.getElementById('scanStatus').textContent = 'Camera indisponible';
    document.getElementById('scanStatus').style.color = 'var(--danger)';
  });
}

async function stopScanner() {
  if (scannerInstance && scannerActive) {
    try { await scannerInstance.stop(); } catch(e) {}
    scannerActive = false;
    scannerInstance = null;
    document.getElementById('scanStatus').textContent = 'Camera arretee';
    document.getElementById('scanStatus').style.color = 'var(--text-muted)';
  }
}

async function toggleScanner() {
  if (scannerActive) {
    await stopScanner();
    document.getElementById('toggleScanBtn').textContent = 'Demarrer la camera';
  } else {
    initScanner();
    document.getElementById('toggleScanBtn').textContent = 'Arreter la camera';
  }
}

async function lookupBarcode(code) {
  const res = await fetch('/api/scan', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ barcode: code })
  });
  const data = await res.json();
  const resultEl = document.getElementById('scanResult');
  const detailEl = document.getElementById('scanDetail');

  if (data.found) {
    const p = data.product;
    resultEl.className = 'scan-result found';
    resultEl.textContent = `✅ Found: ${p.name}`;
    detailEl.innerHTML = `
      <div class="product-detail-row"><span class="product-detail-label">Name</span><strong>${p.name}</strong></div>
      <div class="product-detail-row"><span class="product-detail-label">Qty</span><span>${p.qty}</span></div>
      <div class="product-detail-row"><span class="product-detail-label">Price</span><span>${p.price} DH</span></div>
      <div class="product-detail-row"><span class="product-detail-label">Expiry</span><span>${p.expiry}</span></div>
    `;
    showToast(`Found: ${p.name}`, 'success');
  } else {
    resultEl.className = 'scan-result not-found';
    resultEl.textContent = `❌ Not found — code: ${code}`;
    detailEl.innerHTML = `<p style="color:var(--text-muted);font-size:13px">This barcode is not in your stock. <button class="btn btn-primary btn-sm" onclick="openAddWithBarcode('${code}')">Add it</button></p>`;
  }
}

function openAddWithBarcode(code) {
  showPage('page-stock');
  openAddModal();
  setTimeout(() => document.getElementById('inp-barcode').value = code, 100);
}

function manualLookup() {
  const code = document.getElementById('manualBarcode').value.trim();
  if (!code) return;
  document.getElementById('scannedCode').textContent = code;
  lookupBarcode(code);
}

// ---- LIVE UPDATE ----
function startLiveUpdate() {
  clearInterval(liveInterval);
  liveInterval = setInterval(async () => {
    await loadKPIs();
    await loadProducts();
  }, 30000);
}

// ---- INIT ----
async function init() {
  await loadProducts();
  await loadKPIs();
  showPage('page-dashboard');
  startLiveUpdate();

  // Keyboard close modal
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
}

init();

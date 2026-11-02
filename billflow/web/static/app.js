/**
 * BillFlow Enterprise POS & Business Management App
 * Clean, modern JavaScript - No emojis, high performance
 */

const API_BASE = window.location.origin;

// On a phone the session can expire (or the PIN can change): go back to the PIN page.
const nativeFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const res = await nativeFetch(...args);
  // A wrong staff PIN also answers 401, but that is not an expired session.
  const isStaffLogin = String(args[0]).includes('/api/staff/login');
  if (res.status === 401 && !isStaffLogin) window.location.href = '/login';
  return res;
};

const state = {
  activeView: 'overview',
  theme: localStorage.getItem('billflow_theme') || 'zinc-dark',
  products: [],
  categories: [],
  customers: [],
  staff: [],
  posFilteredProducts: [],
  selectedCategory: 'all',
  posSearchTerm: '',
  cart: [],
  staffMe: { id: null, name: '' },
  appliedCoupon: null,
  selectedCustomer: null,
  paymentMode: 'Cash',
  charts: {},
  shop: {  // replaced by /api/settings as soon as the page loads
    shop_name: '', shop_phone: '', shop_address: '', shop_gstin: '',
    currency: 'INR', currency_symbol: 'Rs.', currency_locale: 'en-IN', timezone: '', today: '', week: ''
  }
};

function formatMoney(val) {
  const num = Number(val) || 0;
  const symbol = state.shop.currency_symbol;
  const gap = /[A-Za-z]$/.test(symbol) ? ' ' : '';  // "Ksh 5.00" but "$5.00"
  const digits = Math.abs(num).toLocaleString(state.shop.currency_locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return (num < 0 ? '-' : '') + symbol + gap + digits;
}

// Today's date (YYYY-MM-DD) in the shop's time zone, whatever time zone this device is in.
function shopToday() {
  if (state.shop.timezone) {
    try {
      return new Intl.DateTimeFormat('en-CA', { timeZone: state.shop.timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
    } catch (err) { /* fall through */ }
  }
  return state.shop.today || new Date().toISOString().split('T')[0];
}

function esc(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function loadShop() {
  try {
    const res = await fetch(`${API_BASE}/api/settings`);
    if (res.ok) state.shop = { ...state.shop, ...(await res.json()) };
  } catch (err) {
    console.error('Shop settings error:', err);
  }
  const subtitle = document.getElementById('brand-subtitle');
  if (subtitle && state.shop.shop_name) subtitle.innerText = state.shop.shop_name;
  document.title = state.shop.shop_name ? `${state.shop.shop_name} - BillFlow` : 'BillFlow';
}

// Calendar cells are too narrow for a full amount on a phone, so show 12.3k instead.
function formatCalendarAmount(val) {
  if (!window.matchMedia('(max-width: 820px)').matches) return formatMoney(val);
  return val >= 1000 ? `${(val / 1000).toFixed(1)}k` : String(Math.round(val));
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return isNaN(d) ? dateStr : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

document.addEventListener('DOMContentLoaded', async () => {
  await loadShop();
  loadStaffMe();
  initTheme();
  setupNavigation();
  setupModals();
  setupPOSHandlers();

  // Set default dates for EOD, Cash Register, GST
  const todayStr = shopToday();
  const eodDate = document.getElementById('eod-date-input');
  if (eodDate) eodDate.value = todayStr;
  const cashDate = document.getElementById('cash-reg-date');
  if (cashDate) cashDate.value = todayStr;
  const expDate = document.getElementById('new-exp-date');
  if (expDate) expDate.value = todayStr;
  const gstFrom = document.getElementById('gst-from-date');
  if (gstFrom) gstFrom.value = `${todayStr.slice(0, 4)}-01-01`;
  const rosterWeek = document.getElementById('roster-week-input');
  if (rosterWeek && !rosterWeek.value) rosterWeek.value = state.shop.week;
  const gstTo = document.getElementById('gst-to-date');
  if (gstTo) gstTo.value = todayStr;

  switchView('overview');
});

function initTheme() {
  document.documentElement.setAttribute('data-theme', state.theme);
  const selector = document.getElementById('theme-select');
  if (selector) {
    selector.value = state.theme;
    selector.addEventListener('change', (e) => {
      state.theme = e.target.value;
      document.documentElement.setAttribute('data-theme', state.theme);
      localStorage.setItem('billflow_theme', state.theme);
      if (state.activeView === 'overview') loadOverview();
      if (state.activeView === 'analytics_plus') loadAnalyticsPlus();
    });
  }

  const sbPosSelector = document.getElementById('sidebar-pos-select');
  if (sbPosSelector) {
    const savedPos = localStorage.getItem('billflow_sidebar_pos') || 'left';
    sbPosSelector.value = savedPos;
    document.documentElement.setAttribute('data-sidebar-pos', savedPos);
    sbPosSelector.addEventListener('change', (e) => {
      const pos = e.target.value;
      document.documentElement.setAttribute('data-sidebar-pos', pos);
      localStorage.setItem('billflow_sidebar_pos', pos);
    });
  }
}

function setupNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const view = item.getAttribute('data-view');
      if (view) switchView(view);
    });
  });
}

function switchView(viewName) {
  state.activeView = viewName;
  document.body.dataset.view = viewName;
  closeSidebar();
  const scroller = document.querySelector('.content-area');
  if (scroller) scroller.scrollTop = 0;
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.getAttribute('data-view') === viewName);
  });
  document.querySelectorAll('.view-panel').forEach(el => {
    el.classList.toggle('active', el.id === `view-${viewName}`);
  });

  const titleMap = {
    overview: 'Executive Dashboard',
    pos: 'POS Billing Terminal',
    products: 'Products & Inventory',
    customers: 'Customer CRM',
    coupons: 'Promotions & Coupons',
    eod: 'End of Day (EOD) Reconciliation',
    cash_register: 'Cash Register & Float',
    purchase_orders: 'Stock Purchase Orders',
    stock: 'Stock Control',
    refunds: 'Refunds & Returns',
    audit: 'Audit Log',
    staff: 'Staff Management',
    roster: 'Weekly Shift Roster',
    salary: 'Payroll & Salary Slips',
    targets: 'Sales Targets',
    expenses: 'Operational Expenses',
    holidays: 'Holidays Calendar',
    calendar: 'Sales Calendar Heatmap',
    gst: 'GST Tax Filing Report',
    breakeven: 'Break-Even Analysis',
    insights: 'Business Insights',
    analytics_plus: 'Day & Peak Patterns',
    settings: 'Settings & Export'
  };
  const titleEl = document.getElementById('current-page-title');
  if (titleEl) titleEl.innerText = titleMap[viewName] || 'Dashboard';

  // Load View Data
  switch (viewName) {
    case 'overview': loadOverview(); break;
    case 'pos': loadPOS(); break;
    case 'products': loadProducts(); break;
    case 'customers': loadCustomers(); break;
    case 'coupons': loadCoupons(); break;
    case 'eod': loadEOD(); break;
    case 'cash_register': loadCashRegister(); break;
    case 'purchase_orders': loadPurchaseOrders(); break;
    case 'stock': loadStockControl(); break;
    case 'refunds': searchRefundBills(); break;
    case 'audit': loadAuditLog(); break;
    case 'staff': loadStaff(); break;
    case 'roster': loadRoster(); break;
    case 'salary': loadSalary(); break;
    case 'targets': loadTargets(); break;
    case 'expenses': loadExpenses(); break;
    case 'holidays': loadHolidays(); break;
    case 'calendar': loadCalendarHeat(); break;
    case 'gst': loadGSTReport(); break;
    case 'breakeven': loadBreakEven(); break;
    case 'insights': loadInsights(); break;
    case 'analytics_plus': loadAnalyticsPlus(); break;
    case 'settings': loadSettings(); break;
  }
}

// ---------------- 1. Overview ---------------- //

async function loadOverview() {
  try {
    const res = await fetch(`${API_BASE}/api/overview`);
    const data = await res.json();

    document.getElementById('kpi-revenue').innerText = formatMoney(data.total_revenue);
    document.getElementById('kpi-bills').innerText = data.total_bills;
    document.getElementById('kpi-aov').innerText = formatMoney(data.avg_order_value);
    document.getElementById('kpi-stock').innerText = `${data.low_stock_count} Items`;

    const billsBody = document.getElementById('recent-bills-tbody');
    if (billsBody) {
      billsBody.innerHTML = (data.recent_bills || []).map(b => `
        <tr>
          <td><span style="font-weight:600; color:var(--accent)">#${b.id}</span></td>
          <td>${formatDate(b.date)}</td>
          <td>${b.customer || 'Walk-in'}</td>
          <td><span class="status-badge ${b.payment_mode ? b.payment_mode.toLowerCase() : 'cash'}">${b.payment_mode || 'Cash'}</span></td>
          <td style="font-weight:600">${formatMoney(b.total)}</td>
          <td><button class="quick-btn" style="padding:3px 8px; font-size:0.72rem;" onclick="viewReceipt(${b.id})">Receipt</button></td>
        </tr>
      `).join('');
    }

    const topProdList = document.getElementById('top-products-list');
    if (topProdList) {
      const maxUnits = Math.max(...(data.top_products || []).map(p => p.units_sold), 1);
      topProdList.innerHTML = (data.top_products || []).map(p => {
        const pct = Math.round((p.units_sold / maxUnits) * 100);
        return `
          <div style="margin-bottom: 12px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:3px; font-size:0.8rem;">
              <span style="font-weight:600">${p.name}</span>
              <span style="color:var(--text-dim); font-size:0.72rem;">${p.units_sold} sold (${formatMoney(p.revenue)})</span>
            </div>
            <div style="height:5px; background:var(--bg-subtle); border-radius:3px; overflow:hidden;">
              <div style="width:${pct}%; height:100%; background:var(--accent); border-radius:3px;"></div>
            </div>
          </div>
        `;
      }).join('');
    }

    loadRevenueChart();
  } catch (err) {
    console.error('Overview load error:', err);
  }
}

async function loadRevenueChart() {
  try {
    const res = await fetch(`${API_BASE}/api/chart-data?days=30`);
    const data = await res.json();
    const ctx = document.getElementById('revenueChart');
    if (!ctx) return;

    if (state.charts.revenue) state.charts.revenue.destroy();

    const isLight = state.theme === 'zinc-light';
    const gridColor = isLight ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.08)';
    const textColor = isLight ? '#64748b' : '#a1a1aa';

    state.charts.revenue = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.labels.map(l => l.slice(5)),
        datasets: [{
          label: 'Daily Revenue',
          data: data.revenues,
          borderColor: '#10b981',
          backgroundColor: 'rgba(16, 185, 129, 0.12)',
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 2.5
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 9 } } },
          y: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 9 }, callback: (v) => state.shop.currency_symbol + (v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v) } }
        }
      }
    });
  } catch (err) {
    console.error('Chart error:', err);
  }
}

// ---------------- 2. POS Terminal ---------------- //

async function loadPOS() {
  try {
    const [pRes, cRes] = await Promise.all([
      fetch(`${API_BASE}/api/products`),
      fetch(`${API_BASE}/api/customers`)
    ]);
    const pData = await pRes.json();
    const cData = await cRes.json();

    state.products = pData.products || [];
    state.categories = pData.categories || [];
    state.customers = cData || [];

    renderCategoryChips();
    renderCustomerDropdown();
    filterAndRenderPOSProducts();
    renderCart();
  } catch (err) {
    console.error('POS load error:', err);
  }
}

function renderCategoryChips() {
  const container = document.getElementById('pos-category-chips');
  if (!container) return;
  const cats = ['all', ...state.categories];
  container.innerHTML = cats.map(c => `
    <button class="cat-chip ${state.selectedCategory === c ? 'active' : ''}" onclick="selectPOSCategory('${c}')">
      ${c.toUpperCase()}
    </button>
  `).join('');
}

function selectPOSCategory(cat) {
  state.selectedCategory = cat;
  renderCategoryChips();
  filterAndRenderPOSProducts();
}

function filterAndRenderPOSProducts() {
  const container = document.getElementById('pos-products-grid');
  if (!container) return;
  const term = state.posSearchTerm.toLowerCase().trim();
  const filtered = state.products.filter(p => {
    const matchesCat = state.selectedCategory === 'all' || p.category.toLowerCase() === state.selectedCategory.toLowerCase();
    const matchesSearch = !term || p.name.toLowerCase().includes(term) || (p.hsn_code && p.hsn_code.toLowerCase().includes(term))
      || (p.sku && p.sku.toLowerCase().includes(term)) || (p.barcode && p.barcode.toLowerCase().includes(term));
    return matchesCat && matchesSearch;
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding:30px; color:var(--text-dim);">No matching products found.</div>`;
    return;
  }

  container.innerHTML = filtered.map(p => `
    <div class="prod-card" onclick="addToCart(${p.id})">
      <div>
        <span class="prod-cat-tag">${p.category}</span>
        <div class="prod-title">${p.name}</div>
      </div>
      <div class="prod-footer">
        <span class="prod-price">${formatMoney(p.price)}</span>
        <span class="prod-stock ${p.quantity <= 0 ? 'oversold' : ''}">${p.quantity <= 0 ? `${p.quantity} in stock` : `${p.quantity} left`}</span>
      </div>
    </div>
  `).join('');
}

function renderCustomerDropdown() {
  const sel = document.getElementById('pos-customer-select');
  if (!sel) return;
  sel.innerHTML = `<option value="">Walk-in Customer</option>` + state.customers.map(c => `
    <option value="${c.id}">${c.name} (${c.phone || 'No phone'}) - ${c.tag}</option>
  `).join('');
}

function addToCart(productId) {
  const prod = state.products.find(p => p.id === productId);
  if (!prod) return;

  // A sale is never blocked by the stock count (the shelf is the truth, the count may be stale);
  // the cart flags lines that go past what the system thinks is on hand.
  const existing = state.cart.find(it => it.id === productId);
  if (existing) existing.qty += 1;
  else state.cart.push({ id: prod.id, name: prod.name, price: prod.price, gst_rate: prod.gst_rate, max_stock: prod.quantity, qty: 1 });
  renderCart();
}

function updateCartQty(productId, delta) {
  const item = state.cart.find(it => it.id === productId);
  if (!item) return;
  item.qty += delta;
  if (item.qty <= 0) state.cart = state.cart.filter(it => it.id !== productId);
  renderCart();
}

function renderCart() {
  const list = document.getElementById('cart-items-list');
  const countEl = document.getElementById('cart-count-badge');
  const checkoutBtn = document.getElementById('checkout-action-btn');

  const totalItems = state.cart.reduce((sum, it) => sum + it.qty, 0);
  if (countEl) countEl.innerText = `${totalItems} items`;
  const cartBar = document.getElementById('mobile-cart-bar');
  if (cartBar) cartBar.hidden = state.cart.length === 0;

  if (state.cart.length === 0) {
    if (list) list.innerHTML = `<div style="text-align:center; padding:25px; color:var(--text-dim); font-size:0.8rem;">Cart is empty. Click any product to add.</div>`;
    if (checkoutBtn) checkoutBtn.disabled = true;
    updateCartTotals(0, 0, 0, 0);
    return;
  }

  if (checkoutBtn) checkoutBtn.disabled = false;

  if (list) {
    list.innerHTML = state.cart.map(it => `
      <div class="cart-item">
        <div class="cart-item-info">
          <div class="cart-item-title">${esc(it.name)}</div>
          <div class="cart-item-unit">${formatMoney(it.price)} x ${it.qty}</div>
          ${it.qty > it.max_stock ? `<div class="cart-oversold">System shows ${Math.max(it.max_stock, 0)} in stock. Stock will go negative.</div>` : ''}
        </div>
        <div class="cart-qty-ctrl">
          <button class="qty-btn" onclick="updateCartQty(${it.id}, -1)">-</button>
          <span style="font-weight:600; font-size:0.8rem; width:16px; text-align:center;">${it.qty}</span>
          <button class="qty-btn" onclick="updateCartQty(${it.id}, 1)">+</button>
        </div>
        <div class="cart-item-total">${formatMoney(it.price * it.qty)}</div>
      </div>
    `).join('');
  }

  const subtotal = state.cart.reduce((sum, it) => sum + (it.price * it.qty), 0);
  // Preview only: the server recomputes this from its own prices and GST rates.
  const discount = Math.min(state.appliedCoupon ? (state.appliedCoupon.discount || 0) : 0, subtotal);
  const taxable = subtotal - discount;
  const keep = subtotal > 0 ? taxable / subtotal : 0;
  const tax = Number(state.cart.reduce((sum, it) => sum + it.price * it.qty * keep * (it.gst_rate ?? 18) / 100, 0).toFixed(2));
  const grandTotal = Number((taxable + tax).toFixed(2));

  updateCartTotals(subtotal, discount, tax, grandTotal);
  const cartSummary = document.getElementById('mobile-cart-summary');
  if (cartSummary) cartSummary.innerText = `${totalItems} items - ${formatMoney(grandTotal)}`;
}

function updateCartTotals(subtotal, discount, tax, grandTotal) {
  document.getElementById('cart-subtotal').innerText = formatMoney(subtotal);
  document.getElementById('cart-discount').innerText = formatMoney(discount);
  document.getElementById('cart-tax').innerText = formatMoney(tax);
  document.getElementById('cart-grand-total').innerText = formatMoney(grandTotal);

  state.currentSubtotal = subtotal;
  state.currentDiscount = discount;
  state.currentTax = tax;
  state.currentGrandTotal = grandTotal;
}

function setupPOSHandlers() {
  const searchInput = document.getElementById('pos-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      state.posSearchTerm = e.target.value;
      filterAndRenderPOSProducts();
    });
    // A barcode scanner types the code and presses Enter: put that exact product in the cart.
    searchInput.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      const code = e.target.value.trim().toLowerCase();
      if (!code) return;
      const match = state.products.find(p => (p.barcode && p.barcode.toLowerCase() === code) || (p.sku && p.sku.toLowerCase() === code));
      if (!match) return;
      e.preventDefault();
      addToCart(match.id);
      e.target.value = '';
      state.posSearchTerm = '';
      filterAndRenderPOSProducts();
    });
  }

  const couponBtn = document.getElementById('apply-coupon-btn');
  if (couponBtn) {
    couponBtn.addEventListener('click', async () => {
      const code = (document.getElementById('pos-coupon-input')?.value || '').trim();
      if (!code) return;
      try {
        const res = await fetch(`${API_BASE}/api/coupons/validate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code, subtotal: state.currentSubtotal || 0 })
        });
        const data = await res.json();
        if (data.valid) {
          state.appliedCoupon = data;
          alert(`Coupon '${data.code}' applied. Discount: ${formatMoney(data.discount)}`);
          renderCart();
        } else {
          alert(data.message || 'Invalid coupon');
        }
      } catch (err) {
        alert('Failed to validate coupon');
      }
    });
  }
}

function openCheckoutModal() {
  document.getElementById('modal-total-display').innerText = formatMoney(state.currentGrandTotal);
  document.getElementById('cash-tendered-input').value = Math.ceil(state.currentGrandTotal);
  updateChangeDisplay();
  openModal('checkout-modal');
}

function selectPayMode(mode) {
  state.paymentMode = mode;
  document.querySelectorAll('.pay-mode-card').forEach(el => {
    el.classList.toggle('active', el.getAttribute('data-mode') === mode);
  });
  document.getElementById('cash-details-group').style.display = (mode === 'Cash') ? 'flex' : 'none';
}

function updateChangeDisplay() {
  const tendered = parseFloat(document.getElementById('cash-tendered-input')?.value || 0);
  const change = Math.max(0, tendered - state.currentGrandTotal);
  document.getElementById('cash-change-display').innerText = formatMoney(change);
}

async function submitCheckout() {
  const custSelect = document.getElementById('pos-customer-select');
  const custId = custSelect?.value ? parseInt(custSelect.value) : null;
  const custName = custSelect?.options[custSelect.selectedIndex]?.text?.split(' (')[0] || 'Walk-in Customer';

  const payload = {
    items: state.cart,
    customer_id: custId,
    customer_name: custName,
    payment_mode: state.paymentMode,
    coupon_code: state.appliedCoupon ? state.appliedCoupon.code : '',
    discount: state.currentDiscount || 0
  };

  try {
    const res = await fetch(`${API_BASE}/api/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();

    if (result.success) {
      closeModal('checkout-modal');
      state.cart = [];
      state.appliedCoupon = null;
      renderCart();
      viewReceipt(result.bill_id);
      loadPOS();
      if ((result.negative_stock || []).length) {
        showToast(`Stock is now negative for: ${result.negative_stock.join(', ')}. Recount or receive stock to correct it.`);
      }
    } else {
      alert(result.error || 'Checkout failed');
    }
  } catch (err) {
    alert('Checkout error: ' + err.message);
  }
}

// ---------------- 3. Products & Stock ---------------- //

async function loadProducts() {
  try {
    const showArchived = !!document.getElementById('show-archived')?.checked;
    const res = await fetch(`${API_BASE}/api/products${showArchived ? '?include_archived=1' : ''}`);
    const data = await res.json();
    const tbody = document.getElementById('products-tbody');
    if (!tbody) return;

    // The shared catalog (Adjust, stocktake, edit) only ever holds live products.
    const rows = data.products || [];
    state.catalog = rows.filter(p => !p.archived);
    tbody.innerHTML = rows.map(p => {
      const margin = p.cost > 0 && p.price > 0 ? `${Math.round((p.price - p.cost) / p.price * 100)}%` : '-';
      const codes = [p.sku, p.barcode, p.hsn_code ? `HSN ${p.hsn_code}` : ''].filter(Boolean).map(esc).join(' &middot; ');
      const badge = p.quantity <= 0 ? 'stock-empty' : (p.low ? 'stock-low' : 'stock-ok');
      const actions = p.archived
        ? `<button class="quick-btn accent" style="padding:3px 8px; font-size:0.72rem;" onclick="restoreProduct(${p.id})">Restore</button>`
        : `<button class="quick-btn" style="padding:3px 8px; font-size:0.72rem;" onclick="openProductModal(${p.id})">Edit</button>
          <button class="quick-btn" style="padding:3px 8px; font-size:0.72rem;" onclick="openAdjustModal(${p.id})">Adjust</button>
          <button class="quick-btn danger" style="padding:3px 8px; font-size:0.72rem;" onclick="archiveProduct(${p.id})">Archive</button>`;
      return `
      <tr class="${p.archived ? 'row-archived' : ''}">
        <td>#${p.id}</td>
        <td style="font-weight:600">${esc(p.name)}${p.archived ? ' <span class="status-badge inactive">Archived</span>' : ''}${codes ? `<div style="font-weight:400; font-size:0.72rem; color:var(--text-dim);">${codes}</div>` : ''}</td>
        <td><span class="cat-chip" style="padding:2px 7px; font-size:0.68rem;">${esc(p.category)}</span></td>
        <td style="font-weight:600">${formatMoney(p.price)}</td>
        <td>${p.cost > 0 ? formatMoney(p.cost) : '<span style="color:var(--text-dim)">not set</span>'}</td>
        <td>${margin}</td>
        <td><span class="status-badge ${badge}">${p.quantity} units${p.quantity < 0 ? ' (oversold)' : ''}</span></td>
        <td>${p.reorder_level}</td>
        <td>${p.supplier_name ? esc(p.supplier_name) : '-'}</td>
        <td style="white-space:nowrap;">${actions}</td>
      </tr>`;
    }).join('');
  } catch (err) {
    console.error('Products load error:', err);
  }
}

// Sends JSON and returns { ok, data }; when ok is false, data.error holds the server's message.
async function apiSend(method, path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  let data = {};
  try { data = await res.json(); } catch (err) { /* no body */ }
  return { ok: res.ok, data };
}

function fieldValue(id) {
  return document.getElementById(id)?.value ?? '';
}

async function loadSuppliersList() {
  try {
    const res = await fetch(`${API_BASE}/api/suppliers`);
    state.suppliers = res.ok ? await res.json() : [];
  } catch (err) {
    state.suppliers = [];
  }
  return state.suppliers;
}

function supplierOptions(selectedId, emptyLabel) {
  return `<option value="">${esc(emptyLabel)}</option>` + (state.suppliers || []).map(s =>
    `<option value="${s.id}" ${s.id === selectedId ? 'selected' : ''}>${esc(s.name)}</option>`).join('');
}

async function openProductModal(id) {
  await loadSuppliersList();
  const p = id ? (state.catalog || []).find(x => x.id === id) : null;
  state.editingProductId = p ? p.id : null;
  document.getElementById('product-modal-title').innerText = p ? `Edit Product #${p.id}` : 'Add Product';
  // Stock is only typed in for a new product; after that it changes through Adjust, with a reason.
  document.getElementById('new-prod-stock-group').style.display = p ? 'none' : '';
  const set = (fieldId, value) => { const el = document.getElementById(fieldId); if (el) el.value = value ?? ''; };
  set('new-prod-name', p?.name);
  set('new-prod-price', p?.price);
  set('new-prod-stock', '');
  set('new-prod-gst', p ? p.gst_rate : 18);
  set('new-prod-hsn', p?.hsn_code);
  set('new-prod-cost', p && p.cost > 0 ? p.cost : '');
  set('new-prod-reorder', p ? p.reorder_level : 10);
  set('new-prod-sku', p?.sku);
  set('new-prod-barcode', p?.barcode);
  const cat = document.getElementById('new-prod-category');
  if (cat && p && ![...cat.options].some(o => o.value === p.category)) cat.add(new Option(p.category, p.category));
  if (cat && p) cat.value = p.category;
  document.getElementById('new-prod-supplier').innerHTML = supplierOptions(p?.supplier_id ?? null, 'No supplier');
  document.getElementById('product-modal-error').innerText = '';
  openModal('add-product-modal');
}

async function archiveProduct(id) {
  const p = (state.catalog || []).find(x => x.id === id);
  if (!confirm(`Archive "${p ? p.name : '#' + id}"? It disappears from the POS and lists, but its sales and stock history are kept. You can restore it any time.`)) return;
  await fetch(`${API_BASE}/api/products/${id}`, { method: 'DELETE' });
  state.products = [];
  loadProducts();
}

async function restoreProduct(id) {
  const { ok, data } = await apiSend('POST', `/api/products/${id}/restore`);
  if (!ok) { alert(data.error || 'Could not restore the product.'); return; }
  state.products = [];
  loadProducts();
}

async function submitNewProduct() {
  const errorEl = document.getElementById('product-modal-error');
  const name = fieldValue('new-prod-name').trim();
  const price = parseFloat(fieldValue('new-prod-price'));
  if (!name || !(price > 0)) { errorEl.innerText = 'Valid name and price required.'; return; }

  const body = {
    name, price,
    category: fieldValue('new-prod-category'),
    hsn_code: fieldValue('new-prod-hsn').trim(),
    gst_rate: fieldValue('new-prod-gst') || 18,
    cost: fieldValue('new-prod-cost'),
    reorder_level: fieldValue('new-prod-reorder'),
    sku: fieldValue('new-prod-sku').trim(),
    barcode: fieldValue('new-prod-barcode').trim(),
    supplier_id: fieldValue('new-prod-supplier') || null
  };
  const editing = state.editingProductId;
  if (!editing) body.quantity = parseInt(fieldValue('new-prod-stock') || 0) || 0;
  const { ok, data } = await apiSend(editing ? 'PUT' : 'POST', editing ? `/api/products/${editing}` : '/api/products', body);
  if (!ok) { errorEl.innerText = data.error || 'Could not save the product.'; return; }
  closeModal('add-product-modal');
  state.products = [];  // the POS and order screens fetch the list again
  loadProducts();
}

async function openAdjustModal(productId) {
  if (!state.stockReasons) {
    const res = await fetch(`${API_BASE}/api/stock/reasons`);
    state.stockReasons = await res.json();
  }
  if (!state.catalog || !state.catalog.length) {
    const res = await fetch(`${API_BASE}/api/products`);
    state.catalog = (await res.json()).products || [];
  }
  const sel = document.getElementById('adj-product');
  sel.innerHTML = state.catalog.map(p => `<option value="${p.id}">${esc(p.name)} (${p.quantity} on hand)</option>`).join('');
  if (productId) sel.value = productId;
  // "Edited" is what the product editor records; people pick a real reason here.
  document.getElementById('adj-reason').innerHTML = state.stockReasons.reasons.filter(r => r !== 'Edited')
    .map(r => `<option>${esc(r)}</option>`).join('');
  document.getElementById('adj-reason').onchange = updateAdjustHint;
  document.getElementById('adj-direction').value = '-1';
  document.getElementById('adj-qty').value = 1;
  document.getElementById('adj-note').value = '';
  document.getElementById('adj-error').innerText = '';
  updateAdjustHint();
  openModal('adjust-stock-modal');
}

function updateAdjustHint() {
  const isWriteOff = (state.stockReasons?.write_offs || []).includes(fieldValue('adj-reason'));
  document.getElementById('adj-hint').innerText = isWriteOff
    ? 'Write-off: input tax credit claimed on these goods has to be reversed in your GST return.' : '';
}

async function submitAdjustment() {
  const errorEl = document.getElementById('adj-error');
  const qty = parseInt(fieldValue('adj-qty'));
  if (!(qty >= 1)) { errorEl.innerText = 'Quantity must be at least 1.'; return; }
  const { ok, data } = await apiSend('POST', '/api/stock/adjust', {
    product_id: parseInt(fieldValue('adj-product')),
    qty: parseInt(fieldValue('adj-direction')) * qty,
    reason: fieldValue('adj-reason'),
    note: fieldValue('adj-note').trim()
  });
  if (!ok) { errorEl.innerText = data.error || 'Could not save the adjustment.'; return; }
  closeModal('adjust-stock-modal');
  state.products = [];
  if (state.activeView === 'stock') loadStockControl(); else loadProducts();
}

// ---------------- 4. Customer CRM ---------------- //

async function loadCustomers() {
  try {
    const res = await fetch(`${API_BASE}/api/customers`);
    const customers = await res.json();
    const tbody = document.getElementById('customers-tbody');
    if (!tbody) return;

    tbody.innerHTML = (customers || []).map(c => `
      <tr>
        <td>#${c.id}</td>
        <td style="font-weight:600">${c.name}</td>
        <td>${c.phone || '-'}</td>
        <td>${c.email || '-'}</td>
        <td><span class="status-badge paid">${c.tag || 'Regular'}</span></td>
        <td style="font-weight:600">${formatMoney(c.total_spent)}</td>
        <td>${c.visit_count}</td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('Customers load error:', err);
  }
}

async function submitNewCustomer() {
  const name = document.getElementById('new-cust-name')?.value;
  const phone = document.getElementById('new-cust-phone')?.value;
  const email = document.getElementById('new-cust-email')?.value;
  const tag = document.getElementById('new-cust-tag')?.value;

  if (!name) { alert('Name is required.'); return; }

  await fetch(`${API_BASE}/api/customers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, phone, email, tag })
  });
  closeModal('add-customer-modal');
  loadCustomers();
}

// ---------------- 5. Coupons ---------------- //

async function loadCoupons() {
  try {
    const res = await fetch(`${API_BASE}/api/coupons`);
    const coupons = await res.json();
    const tbody = document.getElementById('coupons-tbody');
    if (!tbody) return;

    tbody.innerHTML = (coupons || []).map(c => `
      <tr>
        <td style="font-weight:700">${c.code}</td>
        <td>${c.type === 'percent' ? 'Percent' : 'Flat'}</td>
        <td>${c.type === 'percent' ? c.value + '%' : formatMoney(c.value)}</td>
        <td>${formatMoney(c.min_bill || 0)}</td>
        <td>${c.expiry || 'No Expiry'}</td>
        <td><span class="status-badge ${c.active ? 'active' : 'inactive'}">${c.active ? 'Active' : 'Disabled'}</span></td>
        <td>${c.usage_count || 0}</td>
        <td>
          <button class="quick-btn" style="padding:2px 7px; font-size:0.7rem;" onclick="toggleCoupon(${c.id})">${c.active ? 'Disable' : 'Enable'}</button>
          <button class="quick-btn danger" style="padding:2px 7px; font-size:0.7rem;" onclick="deleteCoupon(${c.id})">Delete</button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('Coupons error:', err);
  }
}

async function toggleCoupon(id) {
  await fetch(`${API_BASE}/api/coupons/${id}/toggle`, { method: 'PUT' });
  loadCoupons();
}

async function deleteCoupon(id) {
  if (!confirm('Delete this coupon?')) return;
  await fetch(`${API_BASE}/api/coupons/${id}`, { method: 'DELETE' });
  loadCoupons();
}

async function submitNewCoupon() {
  const code = document.getElementById('new-coup-code')?.value;
  const type = document.getElementById('new-coup-type')?.value;
  const value = parseFloat(document.getElementById('new-coup-val')?.value || 0);
  const min_bill = parseFloat(document.getElementById('new-coup-min')?.value || 0);
  const expiry = document.getElementById('new-coup-exp')?.value;
  const description = document.getElementById('new-coup-desc')?.value;

  if (!code || value <= 0) { alert('Valid code and value required'); return; }

  await fetch(`${API_BASE}/api/coupons`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, type, value, min_bill, expiry, description })
  });
  closeModal('add-coupon-modal');
  loadCoupons();
}

// ---------------- 6. End of Day (EOD) ---------------- //

async function loadEOD() {
  const dt = document.getElementById('eod-date-input')?.value || shopToday();
  try {
    const res = await fetch(`${API_BASE}/api/eod?date=${dt}`);
    const data = await res.json();

    document.getElementById('eod-rev').innerText = formatMoney(data.revenue);
    document.getElementById('eod-refunds').innerText = formatMoney(data.refunds);
    document.getElementById('eod-net').innerText = formatMoney(data.net_revenue);
    document.getElementById('eod-exp').innerText = formatMoney(data.expenses);

    const payList = document.getElementById('eod-payment-list');
    if (payList) {
      payList.innerHTML = Object.entries(data.payment_breakdown || {}).map(([mode, amt]) => `
        <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid var(--border-subtle); font-size:0.8rem;">
          <span style="font-weight:600">${mode}</span>
          <span style="font-variant-numeric:tabular-nums">${formatMoney(amt)}</span>
        </div>
      `).join('') || '<div style="color:var(--text-dim); font-size:0.8rem;">No transactions recorded.</div>';
    }

    const staffList = document.getElementById('eod-staff-list');
    if (staffList) {
      staffList.innerHTML = (data.staff_performance || []).map(s => `
        <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid var(--border-subtle); font-size:0.8rem;">
          <span>${s.name} (${s.bills} bills)</span>
          <span style="font-weight:600; font-variant-numeric:tabular-nums">${formatMoney(s.total)}</span>
        </div>
      `).join('') || '<div style="color:var(--text-dim); font-size:0.8rem;">No staff sales.</div>';
    }
  } catch (err) {
    console.error('EOD error:', err);
  }
}

// ---------------- 7. Cash Register ---------------- //

async function loadCashRegister() {
  const dt = document.getElementById('cash-reg-date')?.value || shopToday();
  try {
    const res = await fetch(`${API_BASE}/api/cash-register?date=${dt}`);
    const data = await res.json();

    document.getElementById('reg-opening').innerText = formatMoney(data.balance.opening);
    document.getElementById('reg-sales').innerText = '+' + formatMoney(data.balance.sales_cash);
    document.getElementById('reg-out').innerText = '-' + formatMoney(data.balance.expenses + data.balance.refunds);
    document.getElementById('reg-closing').innerText = formatMoney(data.balance.closing);

    const tbody = document.getElementById('cash-register-tbody');
    if (tbody) {
      tbody.innerHTML = (data.logs || []).map(l => `
        <tr>
          <td><span class="status-badge ${l.amount >= 0 ? 'paid' : 'stock-empty'}">${l.type}</span></td>
          <td>${l.desc}</td>
          <td style="font-weight:600; font-variant-numeric:tabular-nums">${formatMoney(l.amount)}</td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Cash register error:', err);
  }
}

async function submitOpeningCash() {
  const dt = document.getElementById('cash-reg-date')?.value || shopToday();
  const amt = parseFloat(document.getElementById('opening-cash-amt')?.value || 0);

  await fetch(`${API_BASE}/api/cash-register/opening`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date: dt, amount: amt })
  });
  closeModal('set-opening-cash-modal');
  loadCashRegister();
}

// ---------------- 8. Purchase Orders ---------------- //

async function loadPurchaseOrders() {
  try {
    const res = await fetch(`${API_BASE}/api/purchase-orders`);
    const data = await res.json();

    const statusClass = { Received: 'active', Pending: 'pending', 'Partly received': 'info', Cancelled: 'cancelled' };
    const tbody = document.getElementById('po-tbody');
    if (tbody) {
      tbody.innerHTML = (data.orders || []).map(o => {
        const received = o.qty_received || 0;
        const remaining = o.qty_ordered - received;
        const open = o.status === 'Pending' || o.status === 'Partly received';
        return `
        <tr>
          <td>#${o.id}</td>
          <td>${esc(o.date)}</td>
          <td style="font-weight:600">${esc(o.product_name)}</td>
          <td>${o.qty_ordered}</td>
          <td>${received}</td>
          <td>${formatMoney(o.unit_cost)}</td>
          <td>${o.supplier ? esc(o.supplier) : '-'}</td>
          <td><span class="status-badge ${statusClass[o.status] || 'cancelled'}">${esc(o.status)}</span></td>
          <td style="white-space:nowrap;">
            ${open ? `
              <button class="quick-btn accent" style="padding:2px 7px; font-size:0.7rem;" onclick="receivePO(${o.id}, ${remaining})">Receive</button>
              <button class="quick-btn danger" style="padding:2px 7px; font-size:0.7rem;" onclick="cancelPO(${o.id})">Cancel</button>
            ` : '-'}
          </td>
        </tr>`;
      }).join('') || '<tr><td colspan="9" style="color:var(--text-dim)">No purchase orders yet.</td></tr>';
    }

    // Populate Product dropdown for New PO
    const pSel = document.getElementById('new-po-prod');
    if (pSel) {
      if (state.products.length === 0) {
        const pRes = await fetch(`${API_BASE}/api/products`);
        const pData = await pRes.json();
        state.products = pData.products || [];
      }
      pSel.innerHTML = state.products.map(p => `
        <option value="${p.id}" data-cost="${p.cost || 0}" data-supplier="${p.supplier_id || ''}">${esc(p.name)} (Current: ${p.quantity})</option>
      `).join('');
      await loadSuppliersList();
      updatePOCost();
      pSel.onchange = updatePOCost;
    }
    renderSuppliers();
  } catch (err) {
    console.error('PO error:', err);
  }
}

// A new order starts from the product's own average cost and supplier.
function updatePOCost() {
  const pSel = document.getElementById('new-po-prod');
  const opt = pSel?.options[pSel.selectedIndex];
  if (!opt) return;
  const cost = parseFloat(opt.getAttribute('data-cost') || 0);
  const costInput = document.getElementById('new-po-cost');
  if (costInput) costInput.value = cost > 0 ? cost.toFixed(2) : '';
  const supplierId = parseInt(opt.getAttribute('data-supplier')) || null;
  const supSel = document.getElementById('new-po-supplier-id');
  if (supSel) supSel.innerHTML = supplierOptions(supplierId, 'None or type a name');
}

async function receivePO(id, remaining) {
  const answer = prompt(`How many units arrived for order #${id}? (up to ${remaining})`, remaining);
  if (answer === null) return;
  const { ok, data } = await apiSend('POST', `/api/purchase-orders/${id}/receive`, { qty: parseInt(answer) });
  if (!ok) alert(data.error || 'Could not receive this order.');
  state.products = [];
  loadPurchaseOrders();
}

async function cancelPO(id) {
  if (!confirm(`Cancel order #${id}? Anything already received stays in stock.`)) return;
  const { ok, data } = await apiSend('POST', `/api/purchase-orders/${id}/cancel`);
  if (!ok) alert(data.error || 'Could not cancel this order.');
  loadPurchaseOrders();
}

function renderSuppliers() {
  const tbody = document.getElementById('supplier-tbody');
  if (!tbody) return;
  const linked = {};
  (state.products || []).forEach(p => { if (p.supplier_id) linked[p.supplier_id] = (linked[p.supplier_id] || 0) + 1; });
  tbody.innerHTML = (state.suppliers || []).map(s => `
    <tr>
      <td style="font-weight:600">${esc(s.name)}</td>
      <td>${s.phone ? esc(s.phone) : '-'}</td>
      <td>${s.gstin ? esc(s.gstin) : '-'}</td>
      <td>${linked[s.id] || 0}</td>
      <td style="white-space:nowrap;">
        <button class="quick-btn" style="padding:2px 7px; font-size:0.7rem;" onclick="openSupplierModal(${s.id})">Edit</button>
        <button class="quick-btn danger" style="padding:2px 7px; font-size:0.7rem;" onclick="deleteSupplier(${s.id})">Delete</button>
      </td>
    </tr>`).join('') || '<tr><td colspan="5" style="color:var(--text-dim)">No suppliers yet.</td></tr>';
}

function openSupplierModal(id) {
  const s = id ? (state.suppliers || []).find(x => x.id === id) : null;
  state.editingSupplierId = s ? s.id : null;
  document.getElementById('supplier-modal-title').innerText = s ? 'Edit Supplier' : 'Add Supplier';
  for (const key of ['name', 'phone', 'gstin', 'email', 'address']) {
    document.getElementById(`sup-${key}`).value = s ? (s[key] || '') : '';
  }
  document.getElementById('supplier-modal-error').innerText = '';
  openModal('supplier-modal');
}

async function submitSupplier() {
  const body = {};
  for (const key of ['name', 'phone', 'gstin', 'email', 'address']) body[key] = fieldValue(`sup-${key}`).trim();
  const errorEl = document.getElementById('supplier-modal-error');
  if (!body.name) { errorEl.innerText = 'Supplier name is required.'; return; }
  const id = state.editingSupplierId;
  const { ok, data } = await apiSend(id ? 'PUT' : 'POST', id ? `/api/suppliers/${id}` : '/api/suppliers', body);
  if (!ok) { errorEl.innerText = data.error || 'Could not save the supplier.'; return; }
  closeModal('supplier-modal');
  loadPurchaseOrders();
}

async function deleteSupplier(id) {
  const s = (state.suppliers || []).find(x => x.id === id);
  if (!confirm(`Delete supplier "${s ? s.name : id}"? Products and orders linked to it keep their details.`)) return;
  await apiSend('DELETE', `/api/suppliers/${id}`);
  state.products = [];
  loadPurchaseOrders();
}

async function quickReorderAll() {
  const res = await fetch(`${API_BASE}/api/purchase-orders/reorder-all`, { method: 'POST' });
  const data = await res.json();
  alert(`Generated ${data.created} purchase order(s) for low stock items.`);
  loadPurchaseOrders();
}

async function submitNewPO() {
  const errorEl = document.getElementById('po-modal-error');
  const { ok, data } = await apiSend('POST', '/api/purchase-orders', {
    product_id: fieldValue('new-po-prod'),
    qty_ordered: parseInt(fieldValue('new-po-qty') || 10),
    unit_cost: fieldValue('new-po-cost'),
    supplier_id: fieldValue('new-po-supplier-id') || null,
    supplier: fieldValue('new-po-supp').trim(),
    note: fieldValue('new-po-note').trim()
  });
  if (!ok) { if (errorEl) errorEl.innerText = data.error || 'Could not create the order.'; return; }
  if (errorEl) errorEl.innerText = '';
  closeModal('add-po-modal');
  loadPurchaseOrders();
}

// ---------------- 9. Refunds ---------------- //

async function searchRefundBills() {
  const q = document.getElementById('refund-search-input')?.value || '';
  try {
    const res = await fetch(`${API_BASE}/api/refunds/search?q=${encodeURIComponent(q)}`);
    const bills = await res.json();
    const tbody = document.getElementById('refund-search-tbody');
    if (tbody) {
      tbody.innerHTML = (bills || []).map(b => `
        <tr>
          <td><span style="font-weight:600">#${b.id}</span></td>
          <td>${formatDate(b.date)}</td>
          <td>${esc(b.customer)}</td>
          <td style="font-weight:600">${formatMoney(b.total)}</td>
          <td><span class="status-badge paid">${esc(b.payment_mode || 'Cash')}</span></td>
          <td>
            <button class="quick-btn danger" style="padding:2px 7px; font-size:0.7rem;" onclick="openReturnModal(${b.id})">Return Items</button>
          </td>
        </tr>
      `).join('') || '<tr><td colspan="6" style="color:var(--text-dim)">No matching invoices.</td></tr>';
    }
  } catch (err) {
    console.error('Refund search error:', err);
  }
}

const RETURN_STATUS_LABELS = {
  restock: 'Back on the shelf',
  damaged: 'Damaged (not restocked)',
  write_off: 'Write-off (not restocked)'
};

async function openReturnModal(billId) {
  state.returnBillId = billId;
  state.returnLines = [];
  document.getElementById('return-modal-title').innerText = `Return items from invoice #${billId}`;
  document.getElementById('return-error').innerText = '';
  document.getElementById('return-reason').value = 'Customer return';
  document.getElementById('return-tbody').innerHTML = '<tr><td colspan="5" style="color:var(--text-dim)">Loading...</td></tr>';
  openModal('return-modal');
  try {
    const res = await fetch(`${API_BASE}/api/refunds/${billId}`);
    state.returnLines = await res.json();
  } catch (err) {
    document.getElementById('return-error').innerText = 'Could not load this invoice.';
    return;
  }
  renderReturnLines();
}

function renderReturnLines() {
  const lines = state.returnLines;
  const submit = document.getElementById('return-submit');
  if (!lines.length) {
    document.getElementById('return-tbody').innerHTML =
      '<tr><td colspan="5" style="color:var(--text-dim)">Everything on this invoice has already been returned.</td></tr>';
    submit.disabled = true;
    updateReturnTotal();
    return;
  }
  submit.disabled = false;
  document.getElementById('return-tbody').innerHTML = lines.map((l, i) => `
    <tr>
      <td style="font-weight:600">${esc(l.name)}<div style="font-weight:400; font-size:0.72rem; color:var(--text-dim);">${formatMoney(l.price)} each</div></td>
      <td>${l.sold}</td>
      <td>${l.available}${l.already_returned ? `<div style="font-size:0.72rem; color:var(--text-dim);">${l.already_returned} already returned</div>` : ''}</td>
      <td><input type="number" min="0" max="${l.available}" step="1" value="0" class="modern-input no-icon" style="max-width:80px; padding:6px 8px;"
           oninput="setReturnQty(${i}, this)" aria-label="Quantity to return for ${esc(l.name)}"></td>
      <td><select class="modern-input no-icon" style="padding:6px 8px; font-size:0.78rem;" onchange="setReturnStatus(${i}, this.value)" aria-label="Where ${esc(l.name)} goes">
        ${Object.entries(RETURN_STATUS_LABELS).map(([v, label]) => `<option value="${v}">${label}</option>`).join('')}
      </select></td>
    </tr>`).join('');
  lines.forEach(l => { l.returnQty = 0; l.status = 'restock'; });
  updateReturnTotal();
}

function setReturnQty(i, input) {
  const l = state.returnLines[i];
  l.returnQty = Math.min(Math.max(parseInt(input.value) || 0, 0), l.available);
  if (String(l.returnQty) !== input.value && input.value !== '') input.value = l.returnQty;
  updateReturnTotal();
}

function setReturnStatus(i, value) {
  state.returnLines[i].status = value;
  updateReturnTotal();
}

function returnSelectAll() {
  const inputs = document.querySelectorAll('#return-tbody input[type="number"]');
  state.returnLines.forEach((l, i) => {
    l.returnQty = l.available;
    if (inputs[i]) inputs[i].value = l.available;
  });
  updateReturnTotal();
}

function updateReturnTotal() {
  const chosen = state.returnLines.filter(l => l.returnQty > 0);
  // Item value only; the credit note adds back each line's GST share and any bill discount.
  const value = chosen.reduce((sum, l) => sum + l.price * l.returnQty, 0);
  document.getElementById('return-total').innerText = chosen.length ? `Items value: ${formatMoney(value)}` : '';
  const writeOff = chosen.some(l => l.status === 'write_off');
  document.getElementById('return-hint').innerText = writeOff
    ? 'Write-off: input tax credit claimed on these goods has to be reversed in your GST return.'
    : 'Only items marked "Back on the shelf" are added back to stock.';
}

async function submitReturn() {
  const errorEl = document.getElementById('return-error');
  const lines = state.returnLines.filter(l => l.returnQty > 0)
    .map(l => ({ product_id: l.product_id, qty: l.returnQty, status: l.status }));
  if (!lines.length) { errorEl.innerText = 'Choose at least one item and a quantity.'; return; }
  const { ok, data } = await apiSend('POST', '/api/refunds', {
    bill_id: state.returnBillId,
    reason: fieldValue('return-reason').trim() || 'Customer return',
    lines
  });
  if (!ok) { errorEl.innerText = data.error || 'Could not record the return.'; return; }
  closeModal('return-modal');
  state.products = [];
  showToast(`Credit note ${data.credit_note} issued for ${formatMoney(data.amount)}.`, true);
  searchRefundBills();
}

// ---------------- 10. Staff Directory ---------------- //

async function loadStaff() {
  try {
    const res = await fetch(`${API_BASE}/api/staff`);
    const staff = await res.json();
    state.staff = staff;

    const tbody = document.getElementById('staff-tbody');
    if (tbody) {
      tbody.innerHTML = staff.map(s => `
        <tr>
          <td>#${s.id}</td>
          <td style="font-weight:600">${esc(s.name)}</td>
          <td>${esc(s.phone || '-')}</td>
          <td>${esc(s.role)}</td>
          <td>${esc(s.shift_start)} - ${esc(s.shift_end)}</td>
          <td>${s.commission_pct}%</td>
          <td>${formatMoney(s.salary)}</td>
          <td><span class="status-badge ${s.has_pin ? 'active' : 'pending'}">${s.has_pin ? 'PIN set' : 'No PIN'}</span></td>
          <td><span class="status-badge ${s.active ? 'active' : 'inactive'}">${s.active ? 'Active' : 'Inactive'}</span></td>
          <td style="white-space:nowrap;">
            <button class="quick-btn" style="padding:2px 7px; font-size:0.7rem;" onclick="openStaffPinModal(${s.id})">${s.has_pin ? 'Change PIN' : 'Set PIN'}</button>
            <button class="quick-btn" style="padding:2px 7px; font-size:0.7rem;" onclick="toggleStaff(${s.id})">${s.active ? 'Disable' : 'Activate'}</button>
            <button class="quick-btn danger" style="padding:2px 7px; font-size:0.7rem;" onclick="deleteStaff(${s.id})">Delete</button>
          </td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Staff load error:', err);
  }
}

async function toggleStaff(id) {
  await fetch(`${API_BASE}/api/staff/${id}/toggle`, { method: 'PUT' });
  loadStaff();
}

async function deleteStaff(id) {
  if (!confirm('Delete staff member?')) return;
  await fetch(`${API_BASE}/api/staff/${id}`, { method: 'DELETE' });
  loadStaff();
}

async function submitNewStaff() {
  const name = document.getElementById('new-staff-name')?.value;
  const phone = document.getElementById('new-staff-phone')?.value;
  const role = document.getElementById('new-staff-role')?.value;
  const shift_start = document.getElementById('new-staff-start')?.value;
  const shift_end = document.getElementById('new-staff-end')?.value;
  const salary = parseFloat(document.getElementById('new-staff-sal')?.value || 20000);
  const commission_pct = parseFloat(document.getElementById('new-staff-comm')?.value || 1.0);

  const errorEl = document.getElementById('staff-modal-error');
  if (!name) { errorEl.innerText = 'Staff name required.'; return; }

  const { ok, data } = await apiSend('POST', '/api/staff', {
    name, phone, role, shift_start, shift_end, salary, commission_pct, pin: fieldValue('new-staff-pin').trim()
  });
  if (!ok) { errorEl.innerText = data.error || 'Could not save the staff member.'; return; }
  errorEl.innerText = '';
  document.getElementById('new-staff-pin').value = '';
  closeModal('add-staff-modal');
  loadStaff();
}

// ---------------- Staff sign-in & audit log ---------------- //

function showToast(message, ok) {
  document.querySelector('.toast')?.remove();
  const el = document.createElement('div');
  el.className = `toast${ok ? ' ok' : ''}`;
  el.setAttribute('role', 'status');
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 6000);
}

async function loadStaffMe() {
  try {
    const res = await fetch(`${API_BASE}/api/staff/me`);
    if (res.ok) state.staffMe = await res.json();
  } catch (err) {
    console.error('Staff identity error:', err);
  }
  renderStaffChip();
}

function renderStaffChip() {
  const chip = document.getElementById('staff-chip');
  if (!chip) return;
  const me = state.staffMe;
  chip.classList.toggle('signed-in', !!me.id);
  chip.textContent = me.id ? me.name : 'Sign in as staff';
  chip.title = me.id ? `Signed in as ${me.name}. Click to sign out.` : 'Who is at the till';
}

function openStaffLogin() {
  if (state.staffMe.id) {
    if (confirm(`Sign ${state.staffMe.name} out?`)) staffLogout();
    return;
  }
  document.getElementById('staff-login-pin').value = '';
  document.getElementById('staff-login-error').innerText = '';
  openModal('staff-login-modal');
  document.getElementById('staff-login-pin').focus();
}

async function submitStaffLogin() {
  const errorEl = document.getElementById('staff-login-error');
  const pin = fieldValue('staff-login-pin').trim();
  if (!pin) { errorEl.innerText = 'Enter your PIN.'; return; }
  const { ok, data } = await apiSend('POST', '/api/staff/login', { pin });
  if (!ok) { errorEl.innerText = data.error || 'Could not sign in.'; return; }
  closeModal('staff-login-modal');
  state.staffMe = { id: data.id, name: data.name, role: data.role };
  renderStaffChip();
  showToast(`Signed in as ${data.name}.`, true);
}

async function staffLogout() {
  await apiSend('POST', '/api/staff/logout');
  state.staffMe = { id: null, name: '' };
  renderStaffChip();
}

function openStaffPinModal(id) {
  const s = (state.staff || []).find(x => x.id === id);
  state.pinStaffId = id;
  document.getElementById('staff-pin-title').innerText = `PIN for ${s ? s.name : '#' + id}`;
  document.getElementById('staff-pin-input').value = '';
  document.getElementById('staff-pin-error').innerText = '';
  openModal('staff-pin-modal');
  document.getElementById('staff-pin-input').focus();
}

async function submitStaffPin() {
  const errorEl = document.getElementById('staff-pin-error');
  const { ok, data } = await apiSend('PUT', `/api/staff/${state.pinStaffId}/pin`, { pin: fieldValue('staff-pin-input').trim() });
  if (!ok) { errorEl.innerText = data.error || 'Could not save the PIN.'; return; }
  closeModal('staff-pin-modal');
  loadStaff();
}

async function loadAuditLog() {
  const tbody = document.getElementById('audit-tbody');
  if (!tbody) return;
  const staffSel = document.getElementById('audit-staff');
  if (staffSel && !staffSel.dataset.ready) {
    try {
      const staff = await (await fetch(`${API_BASE}/api/staff`)).json();
      staffSel.innerHTML = '<option value="">Everyone</option>' +
        staff.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
      staffSel.dataset.ready = '1';
    } catch (err) { /* the filter just stays on Everyone */ }
  }
  const params = new URLSearchParams({ limit: 300 });
  if (fieldValue('audit-entity')) params.set('entity', fieldValue('audit-entity'));
  if (fieldValue('audit-staff')) params.set('staff_id', fieldValue('audit-staff'));
  try {
    const rows = await (await fetch(`${API_BASE}/api/audit-log?${params}`)).json();
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td style="white-space:nowrap;">${esc(String(r.date).slice(0, 16))}</td>
        <td style="font-weight:600">${r.staff_name ? esc(r.staff_name) : '<span style="color:var(--text-dim)">Unidentified</span>'}</td>
        <td><span class="status-badge info">${esc(String(r.action).replace(/_/g, ' '))}</span></td>
        <td>${esc(r.entity)}${r.entity_id ? ` #${esc(r.entity_id)}` : ''}</td>
        <td style="color:var(--text-dim)">${esc(r.detail || '')}</td>
      </tr>`).join('') || '<tr><td colspan="5" style="color:var(--text-dim)">Nothing recorded yet.</td></tr>';
  } catch (err) {
    console.error('Audit log error:', err);
  }
}

// ---------------- 11. Shift Roster ---------------- //

async function loadRoster() {
  const week = document.getElementById('roster-week-input')?.value || state.shop.week;
  try {
    const res = await fetch(`${API_BASE}/api/roster?week=${week}`);
    const data = await res.json();
    const tbody = document.getElementById('roster-tbody');
    if (tbody) {
      tbody.innerHTML = (data.roster || []).map(r => `
        <tr>
          <td style="font-weight:600">${r.staff_name}</td>
          <td>${r.staff_role}</td>
          <td>${r.monday || '09:00 - 18:00'}</td>
          <td>${r.tuesday || '09:00 - 18:00'}</td>
          <td>${r.wednesday || '09:00 - 18:00'}</td>
          <td>${r.thursday || '09:00 - 18:00'}</td>
          <td>${r.friday || '09:00 - 18:00'}</td>
          <td>${r.saturday || '10:00 - 19:00'}</td>
          <td>${r.sunday || 'Off'}</td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Roster error:', err);
  }
}

// ---------------- 12. Payroll & Salary ---------------- //

async function loadSalary() {
  try {
    const res = await fetch(`${API_BASE}/api/salary`);
    const data = await res.json();
    const tbody = document.getElementById('salary-tbody');
    if (tbody) {
      tbody.innerHTML = (data || []).map(s => `
        <tr>
          <td style="font-weight:600">${s.name}</td>
          <td>${s.role}</td>
          <td>${formatMoney(s.base_salary)}</td>
          <td>${formatMoney(s.sales_total)}</td>
          <td style="color:var(--accent)">+${formatMoney(s.commission_amt)} (${s.commission_pct}%)</td>
          <td style="color:var(--danger)">-${formatMoney(s.advances)}</td>
          <td style="font-weight:700">${formatMoney(s.net_salary)}</td>
        </tr>
      `).join('');
    }

    const advSel = document.getElementById('adv-staff-select');
    if (advSel) {
      advSel.innerHTML = (data || []).map(s => `<option value="${s.staff_id}">${s.name}</option>`).join('');
    }
  } catch (err) {
    console.error('Salary error:', err);
  }
}

async function submitSalaryAdvance() {
  const staff_id = document.getElementById('adv-staff-select')?.value;
  const amount = parseFloat(document.getElementById('adv-amount')?.value || 0);
  const note = document.getElementById('adv-note')?.value;

  if (amount <= 0) { alert('Valid amount required'); return; }

  await fetch(`${API_BASE}/api/salary/advance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ staff_id, amount, note })
  });
  closeModal('add-advance-modal');
  loadSalary();
}

// ---------------- 13. Sales Targets ---------------- //

async function loadTargets() {
  try {
    const res = await fetch(`${API_BASE}/api/targets`);
    const data = await res.json();

    document.getElementById('target-amt').innerText = formatMoney(data.overall_target);
    document.getElementById('target-rev').innerText = formatMoney(data.overall_revenue);
    document.getElementById('target-pct').innerText = `${data.overall_pct}%`;

    const tbody = document.getElementById('staff-targets-tbody');
    if (tbody) {
      tbody.innerHTML = (data.staff_targets || []).map(s => `
        <tr>
          <td style="font-weight:600">${s.name}</td>
          <td>${s.role}</td>
          <td>${formatMoney(s.target)}</td>
          <td>${formatMoney(s.revenue)}</td>
          <td><span class="status-badge ${s.pct >= 100 ? 'active' : 'pending'}">${s.pct}%</span></td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Targets error:', err);
  }
}

async function submitTargetUpdate() {
  const amt = parseFloat(document.getElementById('target-input-val')?.value || 0);
  await fetch(`${API_BASE}/api/targets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_amt: amt })
  });
  closeModal('edit-target-modal');
  loadTargets();
}

// ---------------- 14. Expenses ---------------- //

async function loadExpenses() {
  try {
    const res = await fetch(`${API_BASE}/api/expenses`);
    const data = await res.json();

    const tbody = document.getElementById('expenses-tbody');
    if (tbody) {
      tbody.innerHTML = (data.expenses || []).map(e => `
        <tr>
          <td>${e.date}</td>
          <td><span class="status-badge info">${e.category}</span></td>
          <td style="font-weight:600">${formatMoney(e.amount)}</td>
          <td>${e.note || '-'}</td>
          <td><button class="quick-btn danger" style="padding:2px 7px; font-size:0.7rem;" onclick="deleteExpense(${e.id})">Delete</button></td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Expenses error:', err);
  }
}

async function deleteExpense(id) {
  if (!confirm('Delete expense?')) return;
  await fetch(`${API_BASE}/api/expenses/${id}`, { method: 'DELETE' });
  loadExpenses();
}

async function submitNewExpense() {
  const date = document.getElementById('new-exp-date')?.value;
  const category = document.getElementById('new-exp-cat')?.value;
  const amount = parseFloat(document.getElementById('new-exp-amt')?.value || 0);
  const note = document.getElementById('new-exp-note')?.value;

  if (amount <= 0) { alert('Valid amount required'); return; }

  await fetch(`${API_BASE}/api/expenses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date, category, amount, note })
  });
  closeModal('add-expense-modal');
  loadExpenses();
}

// ---------------- 15. Holidays ---------------- //

async function loadHolidays() {
  try {
    const res = await fetch(`${API_BASE}/api/holidays`);
    const data = await res.json();

    const tbody = document.getElementById('holidays-tbody');
    if (tbody) {
      tbody.innerHTML = (data || []).map(h => `
        <tr>
          <td>${h.date}</td>
          <td style="font-weight:600">${h.name}</td>
          <td><span class="status-badge info">${h.type}</span></td>
          <td><button class="quick-btn danger" style="padding:2px 7px; font-size:0.7rem;" onclick="deleteHoliday(${h.id})">Delete</button></td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Holidays error:', err);
  }
}

async function deleteHoliday(id) {
  if (!confirm('Delete holiday?')) return;
  await fetch(`${API_BASE}/api/holidays/${id}`, { method: 'DELETE' });
  loadHolidays();
}

async function submitNewHoliday() {
  const date = document.getElementById('new-hol-date')?.value;
  const name = document.getElementById('new-hol-name')?.value;
  const type = document.getElementById('new-hol-type')?.value;

  if (!date || !name) { alert('Date and Name required'); return; }

  await fetch(`${API_BASE}/api/holidays`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date, name, type })
  });
  closeModal('add-holiday-modal');
  loadHolidays();
}

// ---------------- 16. Sales Calendar Heatmap ---------------- //

async function loadCalendarHeat() {
  const monthVal = document.getElementById('cal-month-select')?.value || '2026-11';
  const [year, month] = monthVal.split('-');

  try {
    const res = await fetch(`${API_BASE}/api/calendar-heat?year=${year}&month=${month}`);
    const data = await res.json();

    const grid = document.getElementById('calendar-heatmap-container');
    if (!grid) return;

    const daysOfWeek = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    let html = daysOfWeek.map(d => `<div class="cal-header-day">${d}</div>`).join('');

    // First day offset
    const firstDay = new Date(year, month - 1, 1).getDay();
    for (let i = 0; i < firstDay; i++) {
      html += `<div style="min-height:50px;"></div>`;
    }

    html += (data.days || []).map(d => `
      <div class="cal-day-box ${d.revenue > 0 ? 'has-sales' : ''}">
        <span class="cal-day-num">${d.day}</span>
        <span class="cal-day-amt">${d.revenue > 0 ? formatCalendarAmount(d.revenue) : '-'}</span>
      </div>
    `).join('');

    grid.innerHTML = html;
  } catch (err) {
    console.error('Calendar heat error:', err);
  }
}

// ---------------- 17. GST Tax Report ---------------- //

async function loadGSTReport() {
  const from = document.getElementById('gst-from-date')?.value;
  const to = document.getElementById('gst-to-date')?.value;

  try {
    const res = await fetch(`${API_BASE}/api/gst-report?from=${from}&to=${to}`);
    const data = await res.json();

    document.getElementById('gst-taxable').innerText = formatMoney(data.taxable_total);
    document.getElementById('gst-cgst').innerText = formatMoney(data.cgst);
    document.getElementById('gst-sgst').innerText = formatMoney(data.sgst);
    document.getElementById('gst-total').innerText = formatMoney(data.total_tax);

    const tbody = document.getElementById('gst-tbody');
    if (tbody) {
      tbody.innerHTML = (data.hsn_breakdown || []).map(r => {
        const taxable = Number(r.taxable_val);
        const cgst = taxable * 0.09;
        const sgst = taxable * 0.09;
        return `
          <tr>
            <td style="font-weight:600">${r.hsn_code || 'General'}</td>
            <td>${r.category}</td>
            <td>${r.qty}</td>
            <td>${formatMoney(taxable)}</td>
            <td>${formatMoney(cgst)}</td>
            <td>${formatMoney(sgst)}</td>
          </tr>
        `;
      }).join('');
    }
  } catch (err) {
    console.error('GST error:', err);
  }
}

// ---------------- 18. Break-Even Analysis ---------------- //

async function loadBreakEven() {
  const now = new Date();
  try {
    const res = await fetch(`${API_BASE}/api/breakeven?year=${now.getFullYear()}&month=${now.getMonth() + 1}`);
    const data = await res.json();

    document.getElementById('be-fixed').innerText = formatMoney(data.fixed_costs);
    document.getElementById('be-rev').innerText = formatMoney(data.revenue);
    document.getElementById('be-status').innerText = data.breakeven_reached ? 'Break-Even Achieved' : `Shortfall: ${formatMoney(data.shortfall)}`;
    document.getElementById('be-status').style.color = data.breakeven_reached ? 'var(--accent)' : 'var(--warning)';
    document.getElementById('be-units').innerText = data.units_needed ? `${data.units_needed} units (${data.top_product})` : '-';
  } catch (err) {
    console.error('Breakeven error:', err);
  }
}

// ---------------- 19. Business Insights ---------------- //

async function loadInsights() {
  try {
    const res = await fetch(`${API_BASE}/api/insights`);
    const data = await res.json();

    const deadTbody = document.getElementById('dead-stock-tbody');
    if (deadTbody) {
      deadTbody.innerHTML = (data.dead_stock || []).map(p => `
        <tr><td>${p.name}</td><td>${p.quantity}</td></tr>
      `).join('') || '<tr><td colspan="2" style="color:var(--text-dim)">No stagnant stock.</td></tr>';
    }

    const reorderTbody = document.getElementById('reorder-sug-tbody');
    if (reorderTbody) {
      reorderTbody.innerHTML = (data.reorder_suggestions || []).map(p => `
        <tr><td>${p.name}</td><td style="color:var(--danger)">${p.quantity}</td><td>${formatMoney(p.price)}</td></tr>
      `).join('') || '<tr><td colspan="3" style="color:var(--text-dim)">All stock levels healthy.</td></tr>';
    }
  } catch (err) {
    console.error('Insights error:', err);
  }
}

// ---------------- 20. Peak Patterns ---------------- //

async function loadAnalyticsPlus() {
  try {
    const res = await fetch(`${API_BASE}/api/analytics-plus`);
    const data = await res.json();

    const ctx = document.getElementById('dayAvgChart');
    if (ctx) {
      if (state.charts.dayAvg) state.charts.dayAvg.destroy();

      const isLight = state.theme === 'zinc-light';
      const textColor = isLight ? '#64748b' : '#a1a1aa';
      const gridColor = isLight ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.08)';

      state.charts.dayAvg = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: data.labels,
          datasets: [{
            label: 'Avg Revenue',
            data: data.averages,
            backgroundColor: '#10b981',
            borderRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: gridColor }, ticks: { color: textColor } },
            y: { grid: { color: gridColor }, ticks: { color: textColor, callback: (v) => state.shop.currency_symbol + v.toLocaleString(state.shop.currency_locale) } }
          }
        }
      });
    }

    const predBox = document.getElementById('day-prediction-box');
    if (predBox) {
      predBox.innerText = `${data.best_day}. Forecast: ${data.prediction}`;
    }
  } catch (err) {
    console.error('Analytics plus error:', err);
  }
}

// ---------------- 21. Settings & Store ---------------- //

async function loadSettings() {
  loadMobileAccess();
  loadDatabaseInfo();
  loadSetupCard();
  try {
    const res = await fetch(`${API_BASE}/api/settings`);
    const data = await res.json();

    const sName = document.getElementById('setting-shop-name');
    if (sName) sName.value = data.shop_name || '';
    const sPhone = document.getElementById('setting-shop-phone');
    if (sPhone) sPhone.value = data.shop_phone || '';
    const sAddr = document.getElementById('setting-shop-address');
    if (sAddr) sAddr.value = data.shop_address || '';
    const sGstin = document.getElementById('setting-shop-gstin');
    if (sGstin) sGstin.value = data.shop_gstin || '';
    const sCurrency = document.getElementById('setting-shop-currency');
    if (sCurrency) {
      sCurrency.replaceChildren(...data.currencies.map(c => new Option(`${c.code} - ${c.name} (${c.symbol})`, c.code)));
      sCurrency.value = data.currency;
    }
  } catch (err) {
    console.error('Settings error:', err);
  }
}

async function loadDatabaseInfo() {
  const title = document.getElementById('db-status-title');
  const detail = document.getElementById('db-status-detail');
  if (!title || !detail) return;
  try {
    const info = await (await fetch(`${API_BASE}/api/db-info`)).json();
    title.innerText = `${info.label} connected`;
    detail.innerText = `${info.location} - ${info.counts.bills} bills, ${info.counts.products} products, ${info.counts.customers} customers - ${info.version}`;
  } catch (err) {
    title.innerText = 'Database not reachable';
    detail.innerText = '';
  }
}

async function saveStoreSettings() {
  const shop_name = document.getElementById('setting-shop-name')?.value;
  const shop_phone = document.getElementById('setting-shop-phone')?.value;
  const shop_address = document.getElementById('setting-shop-address')?.value;
  const shop_gstin = document.getElementById('setting-shop-gstin')?.value;
  const currency = document.getElementById('setting-shop-currency')?.value;

  const res = await fetch(`${API_BASE}/api/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ shop_name, shop_phone, shop_address, shop_gstin, currency })
  });
  const result = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(result.error || 'Could not save the settings.');
    return;
  }
  alert('Settings saved successfully.');
  window.location.reload();  // so every amount and the receipt pick up the change
}

async function loadSetupCard() {
  const card = document.getElementById('setup-card');
  if (!card) return;
  try {
    const res = await fetch(`${API_BASE}/api/setup/state`);
    if (!res.ok) {  // other devices (phones) cannot change setup
      card.hidden = true;
      return;
    }
    const info = await res.json();
    const zone = info.settings.timezone || `this computer's own (${info.system_timezone || 'unknown'})`;
    document.getElementById('setup-summary').innerText =
      `Database: ${info.database ? info.database.display : 'not chosen yet'}. Time zone: ${zone}. Phone sharing: ${info.share.enabled ? 'on' : 'off'}.`;
    card.hidden = false;
  } catch (err) {
    card.hidden = true;
  }
}

// ---------------- Mobile layout & access ---------------- //

function toggleSidebar() {
  document.body.classList.toggle('sidebar-open');
}

function closeSidebar() {
  document.body.classList.remove('sidebar-open');
}

function showCartPanel() {
  document.querySelector('.pos-cart-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function signOut() {
  await fetch(`${API_BASE}/api/logout`, { method: 'POST' });
  window.location.href = '/login';
}

async function loadMobileAccess() {
  const box = document.getElementById('mobile-access-body');
  if (!box) return;
  const codeStyle = 'font-family:monospace; font-size:0.95rem; padding:10px 12px; background:var(--bg-subtle); border:1px solid var(--border); border-radius:var(--radius-sm); margin-top:6px; word-break:break-all; user-select:all;';
  const add = (text, style) => {
    const row = document.createElement('div');
    row.textContent = text;
    if (style) row.style.cssText = style;
    box.appendChild(row);
    return row;
  };

  try {
    const res = await fetch(`${API_BASE}/api/network-info`);
    const info = await res.json();
    box.replaceChildren();

    if (!info.lan_enabled) {
      add('Mobile access is off. To let phones on your Wi-Fi use BillFlow, restart it with:', 'font-size:0.85rem;');
      add('python3 run.py --lan', codeStyle);
      return;
    }

    if (!info.local) {
      add('This device is signed in with the access PIN.', 'font-size:0.85rem;');
      const btn = document.createElement('button');
      btn.className = 'quick-btn';
      btn.style.marginTop = '10px';
      btn.textContent = 'Sign out of this device';
      btn.onclick = signOut;
      box.appendChild(btn);
      return;
    }

    add('Open this address in the phone browser (the phone must be on the same Wi-Fi):', 'font-size:0.85rem;');
    (info.urls.length ? info.urls : ['No network address found. Is this computer connected to Wi-Fi?'])
      .forEach(url => add(url, codeStyle));
    add('Access PIN', 'font-size:0.75rem; font-weight:600; color:var(--text-muted); margin-top:14px;');
    add(info.pin, codeStyle + ' font-size:1.4rem; letter-spacing:0.3em; font-weight:700;');
    add('Each phone asks for the PIN once. If the phone cannot connect, this computer\'s firewall may be blocking port '
      + info.port + '. Use this on a network you trust: the PIN is sent unencrypted.',
      'font-size:0.75rem; color:var(--text-dim); margin-top:12px;');
  } catch (err) {
    console.error('Mobile access error:', err);
  }
}

// ---------------- Receipt Viewer ---------------- //

async function viewReceipt(billId) {
  try {
    const res = await fetch(`${API_BASE}/api/bills/${billId}`);
    const data = await res.json();
    const { bill, items } = data;

    const paper = document.getElementById('receipt-paper-content');
    if (!paper) return;

    const shop = state.shop;
    const shopLines = [shop.shop_address, shop.shop_phone && `Phone: ${shop.shop_phone}`, shop.shop_gstin && `GSTIN: ${shop.shop_gstin}`].filter(Boolean);
    paper.innerHTML = `
      <div class="r-center" style="font-weight:700; font-size:1rem; letter-spacing:1px;">${esc(shop.shop_name).toUpperCase()}</div>
      ${shopLines.map(line => `<div class="r-center" style="font-size:0.75rem; color:#666;">${esc(line)}</div>`).join('')}
      <div class="r-divider"></div>
      ${bill.credit_note ? `<div class="r-center" style="font-weight:700; letter-spacing:1px;">CREDIT NOTE ${esc(bill.credit_note)}</div>
      <div class="r-row"><span>AGAINST INVOICE:</span><span>#${esc(bill.refund_of)}</span></div>` : ''}
      <div class="r-row"><span>${bill.credit_note ? 'REFUND BILL #:' : 'INVOICE #:'}</span><span style="font-weight:700">#${bill.id}</span></div>
      <div class="r-row"><span>DATE:</span><span>${esc(bill.date)}</span></div>
      <div class="r-row"><span>CUSTOMER:</span><span>${esc(bill.customer || 'Walk-in')}</span></div>
      <div class="r-row"><span>PAYMENT:</span><span>${esc(bill.payment_mode || 'Cash')}</span></div>
      <div class="r-divider"></div>
      <div style="font-weight:700; margin-bottom:6px;">ITEMS:</div>
      ${(items || []).map(it => `
        <div class="r-row">
          <span>${esc(it.name)} x ${it.qty}</span>
          <span>${formatMoney(it.price * it.qty)}</span>
        </div>
      `).join('')}
      <div class="r-divider"></div>
      <div class="r-row"><span>Subtotal:</span><span>${formatMoney(bill.subtotal)}</span></div>
      ${bill.discount > 0 ? `<div class="r-row"><span>Discount:</span><span>-${formatMoney(bill.discount)}</span></div>` : ''}
      <div class="r-row"><span>GST:</span><span>${formatMoney(bill.tax)}</span></div>
      <div class="r-divider"></div>
      <div class="r-row" style="font-weight:700; font-size:0.95rem;">
        <span>TOTAL:</span><span>${formatMoney(bill.total)}</span>
      </div>
      <div class="r-divider"></div>
      <div class="r-center" style="font-size:0.72rem; margin-top:8px;">THANK YOU FOR YOUR BUSINESS</div>
    `;

    openModal('receipt-modal');
  } catch (err) {
    alert('Failed to load receipt.');
  }
}

// ---------------- Stock Control ---------------- //

async function loadStockControl() {
  try {
    const res = await fetch(`${API_BASE}/api/products`);
    state.catalog = (await res.json()).products || [];
  } catch (err) {
    console.error('Stock control error:', err);
    return;
  }
  const sel = document.getElementById('mv-product');
  if (sel) {
    const chosen = sel.value;
    sel.innerHTML = '<option value="">All products</option>' +
      state.catalog.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
    sel.value = chosen;
  }
  loadStockKpis();
  switchStockTab(state.stockTab || 'movements');
}

function switchStockTab(tab) {
  state.stockTab = tab;
  document.querySelectorAll('[data-stock-tab]').forEach(b => b.classList.toggle('active', b.dataset.stockTab === tab));
  document.querySelectorAll('.stock-tab').forEach(el => { el.hidden = el.id !== `stock-tab-${tab}`; });
  if (tab === 'movements') loadMovements();
  else if (tab === 'count') renderStocktake();
  else if (tab === 'value') loadValuation();
}

async function loadStockKpis() {
  try {
    const days = fieldValue('profit-days') || 30;
    const [valRes, profitRes, checkRes] = await Promise.all([
      fetch(`${API_BASE}/api/stock/valuation`),
      fetch(`${API_BASE}/api/stock/profit?days=${days}`),
      fetch(`${API_BASE}/api/stock/check`)
    ]);
    const val = await valRes.json(), profit = await profitRes.json(), check = await checkRes.json();
    document.getElementById('kpi-stock-value').innerText = formatMoney(val.total_value);
    document.getElementById('kpi-stock-value-sub').innerText = val.items_without_cost
      ? `${val.items_without_cost} item(s) in stock have no cost yet` : `${val.units} units at weighted-average cost`;
    document.getElementById('kpi-retail-value').innerText = formatMoney(val.retail_value);
    document.getElementById('kpi-profit-days').innerText = `${profit.days} days`;
    document.getElementById('kpi-gross-profit').innerText = formatMoney(profit.gross_profit);
    document.getElementById('kpi-gross-profit-sub').innerText = profit.margin_pct === null
      ? 'No sales with a known cost yet' : `${profit.margin_pct}% margin on items with a known cost`;
    document.getElementById('kpi-ledger').innerText = check.ok ? 'Balanced' : `${check.mismatches.length} off`;
    const pill = document.getElementById('kpi-ledger-pill');
    pill.innerText = check.ok ? 'OK' : 'Check';
    pill.className = `kpi-pill ${check.ok ? 'up' : 'warning'}`;
    document.getElementById('kpi-ledger-sub').innerText = check.ok
      ? 'On hand matches the sum of every movement'
      : `Out: ${check.mismatches.slice(0, 3).map(m => m.name).join(', ')}`;
  } catch (err) {
    console.error('Stock KPI error:', err);
  }
}

const MOVEMENT_BADGE = { Sale: 'info', Refund: 'active', Return: 'active', Purchase: 'paid', Adjustment: 'pending', Stocktake: 'pending', Opening: 'cash' };

async function loadMovements() {
  const tbody = document.getElementById('mv-tbody');
  if (!tbody) return;
  const params = new URLSearchParams({ limit: 300 });
  if (fieldValue('mv-product')) params.set('product_id', fieldValue('mv-product'));
  if (fieldValue('mv-type')) params.set('type', fieldValue('mv-type'));
  try {
    const res = await fetch(`${API_BASE}/api/stock/movements?${params}`);
    const rows = await res.json();
    tbody.innerHTML = rows.map(m => `
      <tr>
        <td style="white-space:nowrap;">${esc(String(m.date).slice(0, 16))}</td>
        <td style="font-weight:600">${esc(m.product_name)}</td>
        <td><span class="status-badge ${MOVEMENT_BADGE[m.type] || 'info'}">${esc(m.type)}</span></td>
        <td style="font-weight:700; color:${m.qty > 0 ? 'var(--accent)' : 'var(--danger)'};">${m.qty > 0 ? '+' : ''}${m.qty}</td>
        <td>${m.balance}</td>
        <td>${esc(m.reason || '')}</td>
        <td style="color:var(--text-dim)">${esc(m.note || '')}</td>
      </tr>`).join('') || '<tr><td colspan="7" style="color:var(--text-dim)">No stock movements yet.</td></tr>';
  } catch (err) {
    console.error('Movements error:', err);
  }
}

// What has been typed into the stocktake so far, by product id; kept while the list is filtered.
state.counts = {};

function renderStocktake() {
  const tbody = document.getElementById('count-tbody');
  if (!tbody) return;
  const term = fieldValue('count-search').trim().toLowerCase();
  const shown = (state.catalog || []).filter(p => !term || p.name.toLowerCase().includes(term)
    || (p.sku || '').toLowerCase().includes(term) || (p.barcode || '').toLowerCase() === term);
  tbody.innerHTML = shown.map(p => `
    <tr data-pid="${p.id}">
      <td style="font-weight:600">${esc(p.name)}${p.sku ? `<div style="font-weight:400; font-size:0.72rem; color:var(--text-dim);">${esc(p.sku)}</div>` : ''}</td>
      <td>${p.quantity}</td>
      <td><input type="number" min="0" step="1" class="modern-input no-icon" style="max-width:110px; padding:6px 8px;"
           value="${state.counts[p.id] ?? ''}" oninput="recordCount(${p.id}, this)" aria-label="Counted quantity for ${esc(p.name)}"></td>
      <td class="count-var"></td>
      <td class="count-val"></td>
    </tr>`).join('') || '<tr><td colspan="5" style="color:var(--text-dim)">No matching products.</td></tr>';
  tbody.querySelectorAll('tr[data-pid]').forEach(updateCountRow);
  updateCountSummary();
}

function recordCount(pid, input) {
  if (input.value === '') delete state.counts[pid];
  else state.counts[pid] = Math.max(0, parseInt(input.value) || 0);
  updateCountRow(input.closest('tr'));
  updateCountSummary();
}

function updateCountRow(tr) {
  const p = state.catalog.find(x => x.id === parseInt(tr.dataset.pid));
  const counted = state.counts[p.id];
  const variance = counted === undefined ? null : counted - p.quantity;
  const varCell = tr.querySelector('.count-var'), valCell = tr.querySelector('.count-val');
  varCell.innerText = variance === null ? '' : `${variance > 0 ? '+' : ''}${variance}`;
  varCell.style.color = variance ? (variance > 0 ? 'var(--accent)' : 'var(--danger)') : '';
  valCell.innerText = variance ? formatMoney(variance * (p.cost || 0)) : '';
}

function updateCountSummary() {
  const counted = Object.keys(state.counts).map(Number);
  const diffs = counted.map(id => ({ p: state.catalog.find(x => x.id === id), c: state.counts[id] }))
    .filter(d => d.p && d.c !== d.p.quantity);
  const net = diffs.reduce((a, d) => a + d.c - d.p.quantity, 0);
  const value = diffs.reduce((a, d) => a + (d.c - d.p.quantity) * (d.p.cost || 0), 0);
  document.getElementById('count-summary').innerText = counted.length
    ? `${counted.length} counted, ${diffs.length} different from the system, net ${net > 0 ? '+' : ''}${net} units (${formatMoney(value)} at cost).`
    : 'Nothing counted yet.';
}

async function postStocktake() {
  const ids = Object.keys(state.counts);
  if (!ids.length) { alert('Type at least one count first.'); return; }
  if (!confirm(`Post ${ids.length} count(s)? Stock for those items is set to what you counted.`)) return;
  const { ok, data } = await apiSend('POST', '/api/stock/stocktake', {
    counts: ids.map(id => ({ product_id: Number(id), counted: state.counts[id] }))
  });
  if (!ok) { alert(data.error || 'Could not post the count.'); return; }
  alert(`Count posted: ${data.adjusted} of ${data.counted} item(s) changed, net ${data.net_units} units (${formatMoney(data.value_change)} at cost).`);
  state.counts = {};
  state.products = [];
  loadStockControl();
}

async function loadValuation() {
  const days = fieldValue('profit-days') || 30;
  try {
    const [valRes, profitRes] = await Promise.all([
      fetch(`${API_BASE}/api/stock/valuation`),
      fetch(`${API_BASE}/api/stock/profit?days=${days}`)
    ]);
    const val = await valRes.json(), profit = await profitRes.json();
    const pct = v => (v === null || v === undefined ? '-' : `${v}%`);
    document.getElementById('profit-note').innerText = profit.uncosted_units
      ? `${profit.uncosted_units} unit(s) sold had no cost and are left out of profit.` : 'Before GST and bill discounts.';
    document.getElementById('profit-tbody').innerHTML = profit.items.map(i => `
      <tr>
        <td style="font-weight:600">${esc(i.name)}</td>
        <td>${i.units}</td>
        <td>${formatMoney(i.sales)}</td>
        <td>${formatMoney(i.cogs)}</td>
        <td style="font-weight:700; color:${i.gross_profit >= 0 ? 'var(--accent)' : 'var(--danger)'};">${formatMoney(i.gross_profit)}</td>
        <td>${pct(i.margin_pct)}</td>
      </tr>`).join('') || '<tr><td colspan="6" style="color:var(--text-dim)">No sales in this period.</td></tr>';
    document.getElementById('value-tbody').innerHTML = [...val.items].sort((a, b) => b.value - a.value).map(i => `
      <tr>
        <td style="font-weight:600">${esc(i.name)}</td>
        <td>${i.quantity}</td>
        <td>${i.cost > 0 ? formatMoney(i.cost) : '<span style="color:var(--text-dim)">not set</span>'}</td>
        <td>${formatMoney(i.value)}</td>
        <td>${pct(i.margin_pct)}</td>
      </tr>`).join('') || '<tr><td colspan="5" style="color:var(--text-dim)">No products yet.</td></tr>';
    loadStockKpis();
  } catch (err) {
    console.error('Valuation error:', err);
  }
}

// ---------------- Modal Helpers ---------------- //

function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('active');
}

function setupModals() {
  document.querySelectorAll('.modal-overlay').forEach(modal => {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.remove('active');
    });
  });
}

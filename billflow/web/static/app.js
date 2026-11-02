/**
 * BillFlow Enterprise POS & Business Management App
 * Clean, modern JavaScript - No emojis, high performance
 */

const API_BASE = window.location.origin;

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
  appliedCoupon: null,
  selectedCustomer: null,
  paymentMode: 'Cash',
  charts: {}
};

function formatINR(val) {
  const num = Number(val) || 0;
  return 'Rs. ' + num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return isNaN(d) ? dateStr : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  setupNavigation();
  setupModals();
  setupPOSHandlers();

  // Set default dates for EOD, Cash Register, GST
  const todayStr = new Date().toISOString().split('T')[0];
  const eodDate = document.getElementById('eod-date-input');
  if (eodDate) eodDate.value = todayStr;
  const cashDate = document.getElementById('cash-reg-date');
  if (cashDate) cashDate.value = todayStr;
  const expDate = document.getElementById('new-exp-date');
  if (expDate) expDate.value = todayStr;
  const gstFrom = document.getElementById('gst-from-date');
  if (gstFrom) gstFrom.value = `${new Date().getFullYear()}-01-01`;
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
    refunds: 'Refunds & Returns',
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
    case 'refunds': searchRefundBills(); break;
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

    document.getElementById('kpi-revenue').innerText = formatINR(data.total_revenue);
    document.getElementById('kpi-bills').innerText = data.total_bills;
    document.getElementById('kpi-aov').innerText = formatINR(data.avg_order_value);
    document.getElementById('kpi-stock').innerText = `${data.low_stock_count} Items`;

    const billsBody = document.getElementById('recent-bills-tbody');
    if (billsBody) {
      billsBody.innerHTML = (data.recent_bills || []).map(b => `
        <tr>
          <td><span style="font-weight:600; color:var(--accent)">#${b.id}</span></td>
          <td>${formatDate(b.date)}</td>
          <td>${b.customer || 'Walk-in'}</td>
          <td><span class="status-badge ${b.payment_mode ? b.payment_mode.toLowerCase() : 'cash'}">${b.payment_mode || 'Cash'}</span></td>
          <td style="font-weight:600">${formatINR(b.total)}</td>
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
              <span style="color:var(--text-dim); font-size:0.72rem;">${p.units_sold} sold (${formatINR(p.revenue)})</span>
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
          y: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 9 }, callback: (v) => 'Rs.' + (v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v) } }
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
    const matchesSearch = !term || p.name.toLowerCase().includes(term) || (p.hsn_code && p.hsn_code.toLowerCase().includes(term));
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
        <span class="prod-price">${formatINR(p.price)}</span>
        <span class="prod-stock">${p.quantity} left</span>
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

  const existing = state.cart.find(it => it.id === productId);
  if (existing) {
    if (existing.qty < prod.quantity) existing.qty += 1;
    else { alert(`Available stock limit reached (${prod.quantity}).`); return; }
  } else {
    state.cart.push({ id: prod.id, name: prod.name, price: prod.price, max_stock: prod.quantity, qty: 1 });
  }
  renderCart();
}

function updateCartQty(productId, delta) {
  const item = state.cart.find(it => it.id === productId);
  if (!item) return;
  item.qty += delta;
  if (item.qty <= 0) state.cart = state.cart.filter(it => it.id !== productId);
  else if (item.qty > item.max_stock) item.qty = item.max_stock;
  renderCart();
}

function renderCart() {
  const list = document.getElementById('cart-items-list');
  const countEl = document.getElementById('cart-count-badge');
  const checkoutBtn = document.getElementById('checkout-action-btn');

  const totalItems = state.cart.reduce((sum, it) => sum + it.qty, 0);
  if (countEl) countEl.innerText = `${totalItems} items`;

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
          <div class="cart-item-title">${it.name}</div>
          <div class="cart-item-unit">${formatINR(it.price)} x ${it.qty}</div>
        </div>
        <div class="cart-qty-ctrl">
          <button class="qty-btn" onclick="updateCartQty(${it.id}, -1)">-</button>
          <span style="font-weight:600; font-size:0.8rem; width:16px; text-align:center;">${it.qty}</span>
          <button class="qty-btn" onclick="updateCartQty(${it.id}, 1)">+</button>
        </div>
        <div class="cart-item-total">${formatINR(it.price * it.qty)}</div>
      </div>
    `).join('');
  }

  const subtotal = state.cart.reduce((sum, it) => sum + (it.price * it.qty), 0);
  let discount = state.appliedCoupon ? (state.appliedCoupon.discount || 0) : 0;
  const taxable = Math.max(0, subtotal - discount);
  const tax = Number((taxable * 0.18).toFixed(2));
  const grandTotal = Number((taxable + tax).toFixed(2));

  updateCartTotals(subtotal, discount, tax, grandTotal);
}

function updateCartTotals(subtotal, discount, tax, grandTotal) {
  document.getElementById('cart-subtotal').innerText = formatINR(subtotal);
  document.getElementById('cart-discount').innerText = formatINR(discount);
  document.getElementById('cart-tax').innerText = formatINR(tax);
  document.getElementById('cart-grand-total').innerText = formatINR(grandTotal);

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
          alert(`Coupon '${data.code}' applied. Discount: ${formatINR(data.discount)}`);
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
  document.getElementById('modal-total-display').innerText = formatINR(state.currentGrandTotal);
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
  document.getElementById('cash-change-display').innerText = formatINR(change);
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
    const res = await fetch(`${API_BASE}/api/products`);
    const data = await res.json();
    const tbody = document.getElementById('products-tbody');
    if (!tbody) return;

    tbody.innerHTML = (data.products || []).map(p => `
      <tr>
        <td>#${p.id}</td>
        <td style="font-weight:600">${p.name}</td>
        <td><span class="cat-chip" style="padding:2px 7px; font-size:0.68rem;">${p.category}</span></td>
        <td style="font-weight:600">${formatINR(p.price)}</td>
        <td><span class="status-badge ${p.quantity < 10 ? 'stock-low' : 'stock-ok'}">${p.quantity} units</span></td>
        <td>${p.hsn_code || '-'}</td>
        <td>
          <button class="quick-btn" style="padding:3px 8px; font-size:0.72rem;" onclick="quickEditProduct(${p.id}, '${p.name}', ${p.price}, ${p.quantity})">Edit</button>
          <button class="quick-btn danger" style="padding:3px 8px; font-size:0.72rem;" onclick="deleteProduct(${p.id})">Delete</button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('Products load error:', err);
  }
}

function quickEditProduct(id, name, price, qty) {
  const newPrice = prompt(`Update price for "${name}":`, price);
  if (newPrice === null) return;
  const newStock = prompt(`Update stock quantity for "${name}":`, qty);
  if (newStock === null) return;

  fetch(`${API_BASE}/api/products/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ price: parseFloat(newPrice), quantity: parseInt(newStock) })
  }).then(() => loadProducts());
}

async function deleteProduct(id) {
  if (!confirm(`Delete product #${id}?`)) return;
  await fetch(`${API_BASE}/api/products/${id}`, { method: 'DELETE' });
  loadProducts();
}

async function submitNewProduct() {
  const name = document.getElementById('new-prod-name')?.value;
  const price = parseFloat(document.getElementById('new-prod-price')?.value || 0);
  const quantity = parseInt(document.getElementById('new-prod-stock')?.value || 0);
  const category = document.getElementById('new-prod-category')?.value;
  const hsn = document.getElementById('new-prod-hsn')?.value;

  if (!name || price <= 0) { alert('Valid name and price required.'); return; }

  await fetch(`${API_BASE}/api/products`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, price, quantity, category, hsn_code: hsn })
  });
  closeModal('add-product-modal');
  loadProducts();
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
        <td style="font-weight:600">${formatINR(c.total_spent)}</td>
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
        <td>${c.type === 'percent' ? c.value + '%' : formatINR(c.value)}</td>
        <td>${formatINR(c.min_bill || 0)}</td>
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
  const dt = document.getElementById('eod-date-input')?.value || new Date().toISOString().split('T')[0];
  try {
    const res = await fetch(`${API_BASE}/api/eod?date=${dt}`);
    const data = await res.json();

    document.getElementById('eod-rev').innerText = formatINR(data.revenue);
    document.getElementById('eod-refunds').innerText = formatINR(data.refunds);
    document.getElementById('eod-net').innerText = formatINR(data.net_revenue);
    document.getElementById('eod-exp').innerText = formatINR(data.expenses);

    const payList = document.getElementById('eod-payment-list');
    if (payList) {
      payList.innerHTML = Object.entries(data.payment_breakdown || {}).map(([mode, amt]) => `
        <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid var(--border-subtle); font-size:0.8rem;">
          <span style="font-weight:600">${mode}</span>
          <span style="font-variant-numeric:tabular-nums">${formatINR(amt)}</span>
        </div>
      `).join('') || '<div style="color:var(--text-dim); font-size:0.8rem;">No transactions recorded.</div>';
    }

    const staffList = document.getElementById('eod-staff-list');
    if (staffList) {
      staffList.innerHTML = (data.staff_performance || []).map(s => `
        <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid var(--border-subtle); font-size:0.8rem;">
          <span>${s.name} (${s.bills} bills)</span>
          <span style="font-weight:600; font-variant-numeric:tabular-nums">${formatINR(s.total)}</span>
        </div>
      `).join('') || '<div style="color:var(--text-dim); font-size:0.8rem;">No staff sales.</div>';
    }
  } catch (err) {
    console.error('EOD error:', err);
  }
}

// ---------------- 7. Cash Register ---------------- //

async function loadCashRegister() {
  const dt = document.getElementById('cash-reg-date')?.value || new Date().toISOString().split('T')[0];
  try {
    const res = await fetch(`${API_BASE}/api/cash-register?date=${dt}`);
    const data = await res.json();

    document.getElementById('reg-opening').innerText = formatINR(data.balance.opening);
    document.getElementById('reg-sales').innerText = '+' + formatINR(data.balance.sales_cash);
    document.getElementById('reg-out').innerText = '-' + formatINR(data.balance.expenses + data.balance.refunds);
    document.getElementById('reg-closing').innerText = formatINR(data.balance.closing);

    const tbody = document.getElementById('cash-register-tbody');
    if (tbody) {
      tbody.innerHTML = (data.logs || []).map(l => `
        <tr>
          <td><span class="status-badge ${l.amount >= 0 ? 'paid' : 'stock-empty'}">${l.type}</span></td>
          <td>${l.desc}</td>
          <td style="font-weight:600; font-variant-numeric:tabular-nums">${formatINR(l.amount)}</td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Cash register error:', err);
  }
}

async function submitOpeningCash() {
  const dt = document.getElementById('cash-reg-date')?.value || new Date().toISOString().split('T')[0];
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

    const tbody = document.getElementById('po-tbody');
    if (tbody) {
      tbody.innerHTML = (data.orders || []).map(o => `
        <tr>
          <td>#${o.id}</td>
          <td>${o.date}</td>
          <td style="font-weight:600">${o.product_name}</td>
          <td>${o.qty_ordered}</td>
          <td>${formatINR(o.unit_cost)}</td>
          <td>${o.supplier || '-'}</td>
          <td><span class="status-badge ${o.status === 'Received' ? 'active' : (o.status === 'Pending' ? 'pending' : 'cancelled')}">${o.status}</span></td>
          <td>
            ${o.status === 'Pending' ? `
              <button class="quick-btn accent" style="padding:2px 7px; font-size:0.7rem;" onclick="receivePO(${o.id})">Mark Received</button>
              <button class="quick-btn danger" style="padding:2px 7px; font-size:0.7rem;" onclick="cancelPO(${o.id})">Cancel</button>
            ` : '-'}
          </td>
        </tr>
      `).join('');
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
        <option value="${p.id}" data-name="${p.name}" data-price="${p.price}">${p.name} (Current: ${p.quantity})</option>
      `).join('');
      updatePOCost();
      pSel.onchange = updatePOCost;
    }
  } catch (err) {
    console.error('PO error:', err);
  }
}

function updatePOCost() {
  const pSel = document.getElementById('new-po-prod');
  const opt = pSel?.options[pSel.selectedIndex];
  if (opt) {
    const price = parseFloat(opt.getAttribute('data-price') || 0);
    const costInput = document.getElementById('new-po-cost');
    if (costInput) costInput.value = (price * 0.7).toFixed(2);
  }
}

async function receivePO(id) {
  await fetch(`${API_BASE}/api/purchase-orders/${id}/receive`, { method: 'POST' });
  loadPurchaseOrders();
}

async function cancelPO(id) {
  await fetch(`${API_BASE}/api/purchase-orders/${id}/cancel`, { method: 'POST' });
  loadPurchaseOrders();
}

async function quickReorderAll() {
  const res = await fetch(`${API_BASE}/api/purchase-orders/reorder-all`, { method: 'POST' });
  const data = await res.json();
  alert(`Generated ${data.created} purchase order(s) for low stock items.`);
  loadPurchaseOrders();
}

async function submitNewPO() {
  const pSel = document.getElementById('new-po-prod');
  const opt = pSel?.options[pSel.selectedIndex];
  const pid = pSel?.value;
  const pname = opt?.getAttribute('data-name');
  const qty = parseInt(document.getElementById('new-po-qty')?.value || 10);
  const cost = parseFloat(document.getElementById('new-po-cost')?.value || 0);
  const supplier = document.getElementById('new-po-supp')?.value;
  const note = document.getElementById('new-po-note')?.value;

  await fetch(`${API_BASE}/api/purchase-orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_id: pid, product_name: pname, qty_ordered: qty, unit_cost: cost, supplier, note })
  });
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
          <td>${b.customer}</td>
          <td style="font-weight:600">${formatINR(b.total)}</td>
          <td><span class="status-badge paid">${b.payment_mode || 'Cash'}</span></td>
          <td>
            <button class="quick-btn danger" style="padding:2px 7px; font-size:0.7rem;" onclick="processRefundPrompt(${b.id}, '${b.customer}', ${b.total})">
              Process Refund
            </button>
          </td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Refund search error:', err);
  }
}

async function processRefundPrompt(billId, customer, total) {
  const reason = prompt(`Refund Invoice #${billId} (${customer}) for ${formatINR(total)}?\nEnter Reason:`, 'Customer Return');
  if (reason === null) return;

  const res = await fetch(`${API_BASE}/api/refunds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bill_id: billId, reason })
  });
  const data = await res.json();
  if (data.success) {
    alert(`Refund #${data.refund_id} recorded. Stock returned to inventory.`);
    searchRefundBills();
  }
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
          <td style="font-weight:600">${s.name}</td>
          <td>${s.phone || '-'}</td>
          <td>${s.role}</td>
          <td>${s.shift_start} - ${s.shift_end}</td>
          <td>${s.commission_pct}%</td>
          <td>${formatINR(s.salary)}</td>
          <td><span class="status-badge ${s.active ? 'active' : 'inactive'}">${s.active ? 'Active' : 'Inactive'}</span></td>
          <td>
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

  if (!name) { alert('Staff name required'); return; }

  await fetch(`${API_BASE}/api/staff`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, phone, role, shift_start, shift_end, salary, commission_pct })
  });
  closeModal('add-staff-modal');
  loadStaff();
}

// ---------------- 11. Shift Roster ---------------- //

async function loadRoster() {
  const week = document.getElementById('roster-week-input')?.value || '2026-W45';
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
          <td>${formatINR(s.base_salary)}</td>
          <td>${formatINR(s.sales_total)}</td>
          <td style="color:var(--accent)">+${formatINR(s.commission_amt)} (${s.commission_pct}%)</td>
          <td style="color:var(--danger)">-${formatINR(s.advances)}</td>
          <td style="font-weight:700">${formatINR(s.net_salary)}</td>
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

    document.getElementById('target-amt').innerText = formatINR(data.overall_target);
    document.getElementById('target-rev').innerText = formatINR(data.overall_revenue);
    document.getElementById('target-pct').innerText = `${data.overall_pct}%`;

    const tbody = document.getElementById('staff-targets-tbody');
    if (tbody) {
      tbody.innerHTML = (data.staff_targets || []).map(s => `
        <tr>
          <td style="font-weight:600">${s.name}</td>
          <td>${s.role}</td>
          <td>${formatINR(s.target)}</td>
          <td>${formatINR(s.revenue)}</td>
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
          <td style="font-weight:600">${formatINR(e.amount)}</td>
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
        <span class="cal-day-amt">${d.revenue > 0 ? formatINR(d.revenue) : '-'}</span>
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

    document.getElementById('gst-taxable').innerText = formatINR(data.taxable_total);
    document.getElementById('gst-cgst').innerText = formatINR(data.cgst);
    document.getElementById('gst-sgst').innerText = formatINR(data.sgst);
    document.getElementById('gst-total').innerText = formatINR(data.total_tax);

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
            <td>${formatINR(taxable)}</td>
            <td>${formatINR(cgst)}</td>
            <td>${formatINR(sgst)}</td>
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

    document.getElementById('be-fixed').innerText = formatINR(data.fixed_costs);
    document.getElementById('be-rev').innerText = formatINR(data.revenue);
    document.getElementById('be-status').innerText = data.breakeven_reached ? 'Break-Even Achieved' : `Shortfall: ${formatINR(data.shortfall)}`;
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
        <tr><td>${p.name}</td><td style="color:var(--danger)">${p.quantity}</td><td>${formatINR(p.price)}</td></tr>
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
            y: { grid: { color: gridColor }, ticks: { color: textColor, callback: (v) => 'Rs.' + v.toLocaleString('en-IN') } }
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
  try {
    const res = await fetch(`${API_BASE}/api/settings`);
    const data = await res.json();

    const sName = document.getElementById('setting-shop-name');
    if (sName) sName.value = data.shop_name || 'BillFlow Store';
    const sPhone = document.getElementById('setting-shop-phone');
    if (sPhone) sPhone.value = data.shop_phone || '';
    const sAddr = document.getElementById('setting-shop-address');
    if (sAddr) sAddr.value = data.shop_address || '';
  } catch (err) {
    console.error('Settings error:', err);
  }
}

async function saveStoreSettings() {
  const shop_name = document.getElementById('setting-shop-name')?.value;
  const shop_phone = document.getElementById('setting-shop-phone')?.value;
  const shop_address = document.getElementById('setting-shop-address')?.value;
  const currency = document.getElementById('setting-shop-currency')?.value;

  await fetch(`${API_BASE}/api/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ shop_name, shop_phone, shop_address, currency })
  });
  alert('Settings saved successfully.');
}

// ---------------- Receipt Viewer ---------------- //

async function viewReceipt(billId) {
  try {
    const res = await fetch(`${API_BASE}/api/bills/${billId}`);
    const data = await res.json();
    const { bill, items } = data;

    const paper = document.getElementById('receipt-paper-content');
    if (!paper) return;

    paper.innerHTML = `
      <div class="r-center" style="font-weight:700; font-size:1rem; letter-spacing:1px;">BILLFLOW STORE</div>
      <div class="r-center" style="font-size:0.75rem; color:#666;">High Street Avenue, Tech Hub</div>
      <div class="r-center" style="font-size:0.75rem; color:#666;">GSTIN: 29AAAAA0000A1Z5</div>
      <div class="r-divider"></div>
      <div class="r-row"><span>INVOICE #:</span><span style="font-weight:700">#${bill.id}</span></div>
      <div class="r-row"><span>DATE:</span><span>${bill.date}</span></div>
      <div class="r-row"><span>CUSTOMER:</span><span>${bill.customer || 'Walk-in'}</span></div>
      <div class="r-row"><span>PAYMENT:</span><span>${bill.payment_mode || 'Cash'}</span></div>
      <div class="r-divider"></div>
      <div style="font-weight:700; margin-bottom:6px;">ITEMS:</div>
      ${(items || []).map(it => `
        <div class="r-row">
          <span>${it.name} x ${it.qty}</span>
          <span>Rs. ${(it.price * it.qty).toFixed(2)}</span>
        </div>
      `).join('')}
      <div class="r-divider"></div>
      <div class="r-row"><span>Subtotal:</span><span>Rs. ${bill.subtotal.toFixed(2)}</span></div>
      ${bill.discount > 0 ? `<div class="r-row"><span>Discount:</span><span>-Rs. ${bill.discount.toFixed(2)}</span></div>` : ''}
      <div class="r-row"><span>GST (18%):</span><span>Rs. ${bill.tax.toFixed(2)}</span></div>
      <div class="r-divider"></div>
      <div class="r-row" style="font-weight:700; font-size:0.95rem;">
        <span>TOTAL:</span><span>Rs. ${bill.total.toFixed(2)}</span>
      </div>
      <div class="r-divider"></div>
      <div class="r-center" style="font-size:0.72rem; margin-top:8px;">THANK YOU FOR YOUR BUSINESS</div>
    `;

    openModal('receipt-modal');
  } catch (err) {
    alert('Failed to load receipt.');
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

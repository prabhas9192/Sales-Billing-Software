/**
 * BillFlow Next-Gen POS & Sales Dashboard App
 * Pure Modern Vanilla JS - Lightning Fast & Reactive
 */

const API_BASE = window.location.origin;

// State Management
const state = {
  activeView: 'overview',
  theme: localStorage.getItem('billflow_theme') || 'zinc-dark',
  products: [],
  categories: [],
  customers: [],
  posFilteredProducts: [],
  selectedCategory: 'all',
  posSearchTerm: '',
  cart: [],
  appliedCoupon: null,
  selectedCustomer: null,
  paymentMode: 'Cash',
  cashTendered: 0,
  charts: {}
};

// Formatting helpers
function formatINR(val) {
  const num = Number(val) || 0;
  return '₹' + num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return isNaN(d) ? dateStr : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

// ---------------- Initialization ---------------- //

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  setupNavigation();
  setupModals();
  setupPOSHandlers();

  // Load initial view
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
      // Re-render charts with updated theme colors if on analytics or overview
      if (state.activeView === 'overview') loadOverview();
      if (state.activeView === 'analytics') loadAnalytics();
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
    products: 'Inventory & Catalog Studio',
    customers: 'Customer CRM & Loyalty',
    analytics: 'Financial Analytics & Insights'
  };
  const titleEl = document.getElementById('current-page-title');
  if (titleEl) titleEl.innerText = titleMap[viewName] || 'Dashboard';

  // Trigger data loader
  if (viewName === 'overview') loadOverview();
  else if (viewName === 'pos') loadPOS();
  else if (viewName === 'products') loadProducts();
  else if (viewName === 'customers') loadCustomers();
  else if (viewName === 'analytics') loadAnalytics();
}

// ---------------- View 1: Overview ---------------- //

async function loadOverview() {
  try {
    const res = await fetch(`${API_BASE}/api/overview`);
    const data = await res.json();

    document.getElementById('kpi-revenue').innerText = formatINR(data.total_revenue);
    document.getElementById('kpi-bills').innerText = data.total_bills;
    document.getElementById('kpi-aov').innerText = formatINR(data.avg_order_value);
    document.getElementById('kpi-stock').innerText = `${data.low_stock_count} Items`;

    // Render Recent Bills
    const billsBody = document.getElementById('recent-bills-tbody');
    if (billsBody) {
      billsBody.innerHTML = (data.recent_bills || []).map(b => `
        <tr>
          <td><span style="font-weight:600; color:var(--accent)">#${b.id}</span></td>
          <td>${formatDate(b.date)}</td>
          <td>${b.customer || 'Walk-in'}</td>
          <td><span class="status-badge ${b.payment_mode ? b.payment_mode.toLowerCase() : 'cash'}">${b.payment_mode || 'Cash'}</span></td>
          <td style="font-weight:600">${formatINR(b.total)}</td>
          <td>
            <button class="quick-btn" style="padding:4px 10px; font-size:0.75rem;" onclick="viewReceipt(${b.id})">
              Receipt
            </button>
          </td>
        </tr>
      `).join('');
    }

    // Render Top Selling Products
    const topProdList = document.getElementById('top-products-list');
    if (topProdList) {
      const maxUnits = Math.max(...(data.top_products || []).map(p => p.units_sold), 1);
      topProdList.innerHTML = (data.top_products || []).map(p => {
        const pct = Math.round((p.units_sold / maxUnits) * 100);
        return `
          <div style="margin-bottom: 14px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px; font-size:0.85rem;">
              <span style="font-weight:600">${p.name}</span>
              <span style="color:var(--text-dim); font-size:0.75rem;">${p.units_sold} sold (${formatINR(p.revenue)})</span>
            </div>
            <div style="height:6px; background:var(--bg-subtle); border-radius:3px; overflow:hidden;">
              <div style="width:${pct}%; height:100%; background:linear-gradient(90deg, var(--accent), #3b82f6); border-radius:3px;"></div>
            </div>
          </div>
        `;
      }).join('');
    }

    // Load Chart
    loadRevenueChart();
  } catch (err) {
    console.error('Failed to load overview:', err);
  }
}

async function loadRevenueChart() {
  try {
    const res = await fetch(`${API_BASE}/api/chart-data?days=30`);
    const data = await res.json();

    const ctx = document.getElementById('revenueChart');
    if (!ctx) return;

    if (state.charts.revenue) {
      state.charts.revenue.destroy();
    }

    const isLight = state.theme === 'zinc-light';
    const gridColor = isLight ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.08)';
    const textColor = isLight ? '#64748b' : '#a1a1aa';

    state.charts.revenue = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.labels.map(l => l.slice(5)), // MM-DD
        datasets: [{
          label: 'Daily Revenue (₹)',
          data: data.revenues,
          borderColor: '#10b981',
          backgroundColor: 'rgba(16, 185, 129, 0.12)',
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` Revenue: ₹${ctx.parsed.y.toLocaleString('en-IN')}`
            }
          }
        },
        scales: {
          x: {
            grid: { color: gridColor },
            ticks: { color: textColor, font: { size: 10 } }
          },
          y: {
            grid: { color: gridColor },
            ticks: {
              color: textColor,
              font: { size: 10 },
              callback: (v) => '₹' + (v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v)
            }
          }
        }
      }
    });
  } catch (err) {
    console.error('Chart error:', err);
  }
}

// ---------------- View 2: POS Terminal ---------------- //

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
    container.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding:40px; color:var(--text-dim);">No matching products found.</div>`;
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
        <span class="prod-stock ${p.quantity < 10 ? 'text-amber-500' : ''}">${p.quantity} in stock</span>
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
    if (existing.qty < prod.quantity) {
      existing.qty += 1;
    } else {
      alert(`Cannot add more than available stock (${prod.quantity})!`);
      return;
    }
  } else {
    state.cart.push({
      id: prod.id,
      name: prod.name,
      price: prod.price,
      max_stock: prod.quantity,
      qty: 1
    });
  }
  renderCart();
}

function updateCartQty(productId, delta) {
  const item = state.cart.find(it => it.id === productId);
  if (!item) return;

  item.qty += delta;
  if (item.qty <= 0) {
    state.cart = state.cart.filter(it => it.id !== productId);
  } else if (item.qty > item.max_stock) {
    item.qty = item.max_stock;
    alert(`Only ${item.max_stock} units available in stock.`);
  }
  renderCart();
}

function renderCart() {
  const list = document.getElementById('cart-items-list');
  const countEl = document.getElementById('cart-count-badge');
  const checkoutBtn = document.getElementById('checkout-action-btn');

  const totalItems = state.cart.reduce((sum, it) => sum + it.qty, 0);
  if (countEl) countEl.innerText = `${totalItems} items`;

  if (state.cart.length === 0) {
    if (list) list.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-dim); font-size:0.85rem;">Cart is empty. Click any product to add.</div>`;
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
          <div class="cart-item-unit">${formatINR(it.price)} × ${it.qty}</div>
        </div>
        <div class="cart-qty-ctrl">
          <button class="qty-btn" onclick="updateCartQty(${it.id}, -1)">-</button>
          <span style="font-weight:600; font-size:0.85rem; width:18px; text-align:center;">${it.qty}</span>
          <button class="qty-btn" onclick="updateCartQty(${it.id}, 1)">+</button>
        </div>
        <div class="cart-item-total">${formatINR(it.price * it.qty)}</div>
      </div>
    `).join('');
  }

  // Calculations
  const subtotal = state.cart.reduce((sum, it) => sum + (it.price * it.qty), 0);
  let discount = 0;
  if (state.appliedCoupon) {
    discount = state.appliedCoupon.discount || 0;
  }
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

  // Coupon apply button
  const couponBtn = document.getElementById('apply-coupon-btn');
  if (couponBtn) {
    couponBtn.addEventListener('click', async () => {
      const codeInput = document.getElementById('pos-coupon-input');
      const code = (codeInput?.value || '').trim();
      if (!code) return;

      const subtotal = state.currentSubtotal || 0;
      try {
        const res = await fetch(`${API_BASE}/api/coupons/validate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code, subtotal })
        });
        const data = await res.json();
        if (data.valid) {
          state.appliedCoupon = data;
          alert(`Coupon '${data.code}' applied! Saved ${formatINR(data.discount)}`);
          renderCart();
        } else {
          alert(data.message || 'Invalid coupon');
        }
      } catch (err) {
        alert('Failed to validate coupon');
      }
    });
  }

  // Checkout button
  const checkoutBtn = document.getElementById('checkout-action-btn');
  if (checkoutBtn) {
    checkoutBtn.addEventListener('click', () => {
      openCheckoutModal();
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
  document.getElementById('qr-details-group').style.display = (mode === 'UPI') ? 'block' : 'none';
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
      // Reset cart
      state.cart = [];
      state.appliedCoupon = null;
      renderCart();
      // Show receipt
      viewReceipt(result.bill_id);
      // Reload products in background
      loadPOS();
    } else {
      alert(result.error || 'Checkout failed');
    }
  } catch (err) {
    alert('Failed to process checkout: ' + err.message);
  }
}

// ---------------- View 3: Products ---------------- //

async function loadProducts() {
  try {
    const res = await fetch(`${API_BASE}/api/products`);
    const data = await res.json();
    const tbody = document.getElementById('products-tbody');
    if (!tbody) return;

    tbody.innerHTML = (data.products || []).map(p => {
      let badgeClass = 'stock-ok';
      let badgeText = 'In Stock';
      if (p.quantity === 0) {
        badgeClass = 'stock-empty';
        badgeText = 'Out of Stock';
      } else if (p.quantity < 15) {
        badgeClass = 'stock-low';
        badgeText = `Low (${p.quantity})`;
      }

      return `
        <tr>
          <td><span style="font-weight:600; color:var(--text-dim)">#${p.id}</span></td>
          <td style="font-weight:600">${p.name}</td>
          <td><span class="cat-chip" style="padding:2px 8px; font-size:0.7rem;">${p.category}</span></td>
          <td style="font-weight:700">${formatINR(p.price)}</td>
          <td><span class="status-badge ${badgeClass}">${badgeText}</span></td>
          <td>${p.hsn_code || '—'}</td>
          <td>
            <button class="quick-btn" style="padding:4px 8px; font-size:0.75rem;" onclick="quickEditStock(${p.id}, '${p.name}', ${p.price}, ${p.quantity})">
              Edit
            </button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to load products:', err);
  }
}

function quickEditStock(id, name, price, qty) {
  const newPrice = prompt(`Update Price for "${name}":`, price);
  if (newPrice === null) return;
  const newStock = prompt(`Update Stock Quantity for "${name}":`, qty);
  if (newStock === null) return;

  fetch(`${API_BASE}/api/products/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ price: parseFloat(newPrice), quantity: parseInt(newStock) })
  }).then(() => loadProducts());
}

async function submitNewProduct() {
  const name = document.getElementById('new-prod-name')?.value;
  const price = parseFloat(document.getElementById('new-prod-price')?.value || 0);
  const quantity = parseInt(document.getElementById('new-prod-stock')?.value || 0);
  const category = document.getElementById('new-prod-category')?.value;
  const hsn = document.getElementById('new-prod-hsn')?.value;

  if (!name || price <= 0) {
    alert('Please provide a valid product name and price.');
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/products`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, price, quantity, category, hsn_code: hsn })
    });
    const data = await res.json();
    if (data.id) {
      closeModal('add-product-modal');
      loadProducts();
      alert('Product created successfully!');
    }
  } catch (err) {
    alert('Failed to save product');
  }
}

// ---------------- View 4: Customers ---------------- //

async function loadCustomers() {
  try {
    const res = await fetch(`${API_BASE}/api/customers`);
    const customers = await res.json();
    const tbody = document.getElementById('customers-tbody');
    if (!tbody) return;

    tbody.innerHTML = (customers || []).map(c => `
      <tr>
        <td><span style="font-weight:600; color:var(--text-dim)">#${c.id}</span></td>
        <td style="font-weight:600">${c.name}</td>
        <td>${c.phone || '—'}</td>
        <td><span class="status-badge paid">${c.tag || 'Regular'}</span></td>
        <td style="font-weight:700">${formatINR(c.total_spent)}</td>
        <td>${c.visit_count} orders</td>
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

  if (!name) {
    alert('Customer name is required.');
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/customers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, phone, email, tag })
    });
    const data = await res.json();
    if (data.id) {
      closeModal('add-customer-modal');
      loadCustomers();
      alert('Customer added successfully!');
    }
  } catch (err) {
    alert('Failed to save customer');
  }
}

// ---------------- View 5: Analytics ---------------- //

async function loadAnalytics() {
  try {
    const res = await fetch(`${API_BASE}/api/analytics`);
    const data = await res.json();

    const isLight = state.theme === 'zinc-light';
    const textColor = isLight ? '#09090b' : '#fafafa';

    // 1. Category Chart
    const catCtx = document.getElementById('categoryChart');
    if (catCtx) {
      if (state.charts.category) state.charts.category.destroy();
      state.charts.category = new Chart(catCtx, {
        type: 'doughnut',
        data: {
          labels: (data.categories || []).map(c => c.category),
          datasets: [{
            data: (data.categories || []).map(c => c.revenue),
            backgroundColor: ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4'],
            borderWidth: 0
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { position: 'bottom', labels: { color: textColor, font: { size: 11 } } }
          }
        }
      });
    }

    // 2. Payment Modes Chart
    const payCtx = document.getElementById('paymentChart');
    if (payCtx) {
      if (state.charts.payment) state.charts.payment.destroy();
      state.charts.payment = new Chart(payCtx, {
        type: 'pie',
        data: {
          labels: (data.payment_modes || []).map(p => p.payment_mode || 'Cash'),
          datasets: [{
            data: (data.payment_modes || []).map(p => p.total),
            backgroundColor: ['#10b981', '#3b82f6', '#f59e0b', '#ef4444'],
            borderWidth: 0
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { position: 'bottom', labels: { color: textColor, font: { size: 11 } } }
          }
        }
      });
    }
  } catch (err) {
    console.error('Analytics load error:', err);
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

    paper.innerHTML = `
      <div class="r-center" style="font-weight:700; font-size:1rem; letter-spacing:1px;">BILLFLOW STORE</div>
      <div class="r-center" style="font-size:0.75rem; color:#666;">High Street Avenue, Tech Hub</div>
      <div class="r-center" style="font-size:0.75rem; color:#666;">GSTIN: 29AAAAA0000A1Z5</div>
      <div class="r-divider"></div>
      <div class="r-row"><span>INVOICE #:</span><span style="font-weight:700">#${bill.id}</span></div>
      <div class="r-row"><span>DATE:</span><span>${bill.date}</span></div>
      <div class="r-row"><span>CUSTOMER:</span><span>${bill.customer || 'Walk-in'}</span></div>
      <div class="r-row"><span>MODE:</span><span>${bill.payment_mode || 'Cash'}</span></div>
      <div class="r-divider"></div>
      <div style="font-weight:700; margin-bottom:6px;">ITEMS:</div>
      ${(items || []).map(it => `
        <div class="r-row">
          <span>${it.name} × ${it.qty}</span>
          <span>₹${(it.price * it.qty).toFixed(2)}</span>
        </div>
      `).join('')}
      <div class="r-divider"></div>
      <div class="r-row"><span>Subtotal:</span><span>₹${bill.subtotal.toFixed(2)}</span></div>
      ${bill.discount > 0 ? `<div class="r-row"><span>Discount:</span><span>-₹${bill.discount.toFixed(2)}</span></div>` : ''}
      <div class="r-row"><span>Tax (GST 18%):</span><span>₹${bill.tax.toFixed(2)}</span></div>
      <div class="r-divider"></div>
      <div class="r-row" style="font-weight:700; font-size:0.95rem;">
        <span>TOTAL:</span><span>₹${bill.total.toFixed(2)}</span>
      </div>
      <div class="r-divider"></div>
      <div class="r-center" style="font-size:0.72rem; margin-top:10px;">THANK YOU FOR YOUR VISIT!</div>
      <div class="r-center" style="font-size:0.68rem; color:#888;">Generated by BillFlow Next-Gen POS</div>
    `;

    openModal('receipt-modal');
  } catch (err) {
    alert('Failed to load receipt details.');
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
      if (e.target === modal) {
        modal.classList.remove('active');
      }
    });
  });
}

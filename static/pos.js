/**
 * pos.js — Main POS screen JavaScript.
 */

if (typeof CATEGORY_ICONS === 'undefined') {
    var CATEGORY_ICONS = { 'Бусад': '📦' };
}

if (typeof CATEGORY_COLORS === 'undefined') {
    var CATEGORY_COLORS = { 'Бусад': '#6B7280' };
}

if (typeof DISCOUNTS_ENABLED === 'undefined') {
    var DISCOUNTS_ENABLED = false;
}

var CONNECTION_ONLINE = true;

// Auto-detect low performance hardware
if (navigator.hardwareConcurrency <= 4 || location.search.includes('perf=low')) {
    document.documentElement.setAttribute('data-perf', 'low');
}

function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

function apiRequest(url, options) {
    options = options || {};
    var timeout = options.timeout || 15000;
    var retries = options.retries || 0;
    var maxRetries = options.maxRetries || 2;

    var controller = new AbortController();
    var timer = setTimeout(function() { controller.abort(); }, timeout);

    var headers = options.headers || {};
    var contentType = options.contentType;
    if (contentType) {
        headers['Content-Type'] = contentType;
    }

    // Auto-inject CSRF for mutating requests
    var method = (options.method || 'GET').toUpperCase();
    if (method !== 'GET') {
        var token = getCsrfToken();
        if (token) headers['X-CSRF-Token'] = token;
    }

    function doFetch(attempt) {
        return fetch(url, {
            method: method,
            headers: headers,
            body: options.body || undefined,
            signal: controller.signal
        })
        .then(function(response) {
            clearTimeout(timer);
            if (!response.ok) {
                var err = new Error('HTTP ' + response.status);
                err.status = response.status;
                err.response = response;
                throw err;
            }
            var ct = response.headers.get('content-type') || '';
            if (!ct.includes('application/json')) {
                var err = new Error('Non-JSON response: ' + ct);
                err.status = response.status;
                err.response = response;
                throw err;
            }
            return response.json();
        })
        .catch(function(err) {
            clearTimeout(timer);
            if (err.name === 'AbortError') {
                CONNECTION_ONLINE = false;
                updateConnectionStatus();
                var timeoutErr = new Error('Холболтын хугацаа хэтэрсэн');
                timeoutErr.code = 'TIMEOUT';
                throw timeoutErr;
            }
            if (err.status && err.status !== 0) {
                // Server responded with error status — don't retry
                throw err;
            }
            // Network error — retry if possible
            CONNECTION_ONLINE = false;
            updateConnectionStatus();
            if (attempt < maxRetries) {
                return new Promise(function(resolve) {
                    setTimeout(function() {
                        resolve(doFetch(attempt + 1));
                    }, Math.min(500 * Math.pow(2, attempt), 4000));
                });
            }
            throw err;
        });
    }

    return doFetch(0).then(function(data) {
        CONNECTION_ONLINE = true;
        updateConnectionStatus();
        return data;
    });
}

function updateConnectionStatus() {
    var el = document.getElementById('connectionStatus');
    if (!el) return;
    if (CONNECTION_ONLINE) {
        el.classList.remove('offline');
        el.textContent = '';
    } else {
        el.classList.add('offline');
        el.textContent = '⚠️ Холболтгүй';
    }
}

function getCategoryIcon(category) { return CATEGORY_ICONS[category] || CATEGORY_ICONS['Бусад']; }
function getCategoryColor(category) { return CATEGORY_COLORS[category] || CATEGORY_COLORS['Бусад']; }

let cart = [];
let currentPaymentType = 'cash';
let lastSaleId = null;
let lastTerminalResult = null;
let lastCustomerStateTime = 0;
let customerStateRetryTimer = null;
let qpayInvoiceId = null;
let qpayPollTimer = null;
let qpayPollCount = 0;

sessionStorage.removeItem('pos_cart');

function saveCart() {
    try { sessionStorage.setItem('pos_cart', JSON.stringify(cart)); } catch(e) {}
}
function clearSavedCart() {
    try { sessionStorage.removeItem('pos_cart'); } catch(e) {}
}

function formatCurrency(amount) {
    var n = Math.abs(Number(amount) || 0);
    var s = '' + n;
    var r = '';
    for (var i = s.length - 1, j = 0; i >= 0; i--, j++) {
        if (j > 0 && j % 3 === 0) r = ',' + r;
        r = s[i] + r;
    }
    return r + ' ₮';
}

function safeJson(response) {
    if (!response.ok) throw new Error('HTTP ' + response.status);
    var ct = response.headers.get('content-type') || '';
    if (!ct.includes('application/json')) throw new Error('Non-JSON response: ' + ct);
    return response.json();
}

function handleApiError(err) {
    if (err && err.code === 'TIMEOUT') {
        showNotification('Сервер хариу өгөхгүй байна', 'error');
    } else if (err && err.status === 403) {
        showNotification('Хандах эрхгүй байна', 'error');
    } else if (err && err.status === 404) {
        showNotification('Хүсэлт олдсонгүй', 'error');
    } else if (err && err.status && err.status >= 500) {
        showNotification('Серверийн алдаа (' + err.status + ')', 'error');
    } else {
        showNotification('Сүлжээний алдаа', 'error');
    }
}

function calculateVAT(total) {
    return Math.round(total / 11);
}

/* ─── SOUND ─── */

let audioCtx = null;

function playBeep() {
    try {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.frequency.value = 1200;
        osc.type = 'sine';
        gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.12);
        osc.start(audioCtx.currentTime);
        osc.stop(audioCtx.currentTime + 0.12);
    } catch(e) { /* audio not available */ }
}

function updateCustomerState(phase, extra) {
    phase = phase || 'idle';
    extra = extra || {};
    lastCustomerStateTime = Date.now();
    const state = {
        phase: phase,
        items: extra.items || cart.map(function(item) {
            return {
                name: item.product_name, quantity: item.quantity,
                unit_price: item.unit_price, subtotal: item.subtotal,
                category: item.category || 'Бусад', unit: item.unit || 'ш',
                image_url: item.image_url || ''
            };
        }),
        total: extra.total != null ? extra.total : getCartTotal(),
        payment_type: currentPaymentType,
        cash_given: extra.cash_given || 0,
        change_given: extra.change_given || 0,
        card_amount: extra.card_amount || 0,
        lottery: extra.lottery || '',
        qr_image: extra.qr_image || ''
    };
    _sendCustomerState(state);
}

function _sendCustomerState(state) {
    apiRequest('/api/customer-state', {
        method: 'POST',
        contentType: 'application/json',
        body: JSON.stringify(state),
        timeout: 5000,
        retries: 0,
        maxRetries: 1
    }).catch(function() {});
}

/* ─── CART OPERATIONS ─── */

var _debounceCartTimer = null;

function _flushCartPersist() {
    if (_debounceCartTimer) clearTimeout(_debounceCartTimer);
    _debounceCartTimer = null;
    saveCart();
    updateCustomerState(cart.length > 0 ? 'shopping' : 'idle');
}

function _scheduleCartPersist() {
    if (_debounceCartTimer) clearTimeout(_debounceCartTimer);
    _debounceCartTimer = setTimeout(function() {
        _debounceCartTimer = null;
        saveCart();
        updateCustomerState(cart.length > 0 ? 'shopping' : 'idle');
    }, 300);
}

function addToCart(product, qtyOverride) {
    var qty = qtyOverride || 1;
    let existing = null;
    for (let i = 0; i < cart.length; i++) {
        if (cart[i].product_id === product.id) { existing = cart[i]; break; }
    }

    if (existing) {
        existing.quantity += qty;
        existing.subtotal = existing.quantity * existing.unit_price;
    } else {
        cart.push({
            product_id: product.id,
            product_name: product.name,
            barcode: product.barcode,
            quantity: qty,
            unit_price: product.price,
            subtotal: product.price * qty,
            unit: product.unit || 'ш',
            discount_amount: 0,
            stock_qty: 9999,
            category: product.category || 'Бусад',
            image_url: product.image_url || ''
        });
    }

    _scheduleCartPersist();
    renderCart();
    animateCartCount();
}

function addAnonymousItem(price) {
    price = parseInt(price) || 0;
    if (price <= 0) return;
    var existing = null;
    for (var i = 0; i < cart.length; i++) {
        if (cart[i].product_id === -1 && cart[i].unit_price === price) {
            existing = cart[i];
            break;
        }
    }
    if (existing) {
        existing.quantity += 1;
        existing.subtotal = existing.quantity * existing.unit_price;
    } else {
        cart.push({
            product_id: -1,
            product_name: 'Бүртгэлгүй бараа',
            barcode: '',
            quantity: 1,
            unit_price: price,
            subtotal: price,
            unit: 'ш',
            discount_amount: 0,
            stock_qty: 9999,
            category: 'Бусад',
            image_url: ''
        });
    }
    saveCart();
    updateCustomerState('shopping');
    renderCart();
    animateCartCount();
}

function showAnonymousPricePrompt() {
    var existing = document.querySelector('.price-prompt-overlay');
    if (existing) return;
    var overlay = document.createElement('div');
    overlay.className = 'price-prompt-overlay';
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) closeAnonymousPricePrompt();
    });
    var box = document.createElement('div');
    box.className = 'price-prompt-box';
    box.innerHTML =
        '<div class="price-prompt-title">Бүртгэлгүй бараа</div>' +
        '<div class="price-prompt-sub">Дүнгээ оруулаад Enter дарна уу</div>' +
        '<input type="number" class="price-prompt-input" id="anonymousPriceInput" placeholder="₮" min="1" autofocus>' +
        '<div class="price-prompt-actions">' +
        '<button class="btn btn-primary" onclick="confirmAnonymousPrice()">✓ Батлах</button>' +
        '<button class="btn btn-secondary" onclick="closeAnonymousPricePrompt()">✕ Хаах</button></div>';
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    var input = document.getElementById('anonymousPriceInput');
    input.focus();
    input.addEventListener('keydown', function _ape(e) {
        if (e.key === 'Enter') { e.preventDefault(); confirmAnonymousPrice(); }
        if (e.key === 'Escape') { e.preventDefault(); closeAnonymousPricePrompt(); }
    });
}

function confirmAnonymousPrice() {
    var input = document.getElementById('anonymousPriceInput');
    var price = parseInt(input.value) || 0;
    if (price <= 0) { input.focus(); return; }
    closeAnonymousPricePrompt();
    addAnonymousItem(price);
}

function closeAnonymousPricePrompt() {
    var el = document.querySelector('.price-prompt-overlay');
    if (el) el.remove();
}

function needsQuantityPrompt(unit) {
    return unit === 'кг' || unit === 'л' || unit === 'хайрцаг';
}

function addToCartFromGrid(card) {
    if (card.classList.contains('product-card-disabled')) return;
    var unit = card.dataset.unit || 'ш';
    var product = {
        id: parseInt(card.dataset.id),
        barcode: card.dataset.barcode,
        name: card.dataset.name,
        price: parseInt(card.dataset.price),
        stock_qty: parseInt(card.dataset.stock),
        unit: unit,
        category: card.dataset.category || 'Бусад',
        image_url: card.dataset.imageUrl || ''
    };

    if (needsQuantityPrompt(unit)) {
        showQuantityPrompt(product);
    } else {
        addToCart(product, 1);
        animateCardAdd(card);
    }
}

function showQuantityPrompt(product) {
    var existing = document.querySelector('.quantity-prompt-overlay');
    if (existing) existing.remove();

    var overlay = document.createElement('div');
    overlay.className = 'quantity-prompt-overlay';

    var box = document.createElement('div');
    box.className = 'quantity-prompt-box';
    box.style.cssText = 'position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);';

    var unitLabel = product.unit === 'кг' ? 'г' : (product.unit === 'л' ? 'л' : product.unit);
    var unitPrice = product.price;

    var productData = encodeURIComponent(JSON.stringify(product));

    box.innerHTML =
        '<div style="font-weight:800; font-size:1.1rem; margin-bottom:4px; color:var(--text);">' + escapeHtml(product.name) + '</div>' +
        '<div style="color:var(--text-muted); font-size:0.85rem; margin-bottom:8px;">' + formatCurrency(unitPrice) + '/кг</div>' +
        '<div class="qty-presets" style="display:flex; gap:6px; margin-bottom:10px; flex-wrap:wrap;">' +
            '<button class="qty-preset" data-product="' + productData + '" data-qty="500">500</button>' +
            '<button class="qty-preset" data-product="' + productData + '" data-qty="1000">1000</button>' +
            '<button class="qty-preset" data-product="' + productData + '" data-qty="2000">2000</button>' +
            '<button class="qty-preset" data-product="' + productData + '" data-qty="5000">5000</button>' +
        '</div>' +
        '<div style="display:flex; gap:8px; align-items:center; margin-bottom:8px;">' +
            '<input type="number" id="qtyPromptInput" value="500" min="1" step="1" style="flex:1; padding:10px; border:2px solid var(--primary); border-radius:8px; font-size:1.1rem; font-weight:700; text-align:center; background:var(--surface); color:var(--text);">' +
            '<span style="font-weight:700; color:var(--text-secondary);">' + escapeHtml(unitLabel) + '</span>' +
        '</div>' +
        '<div id="qtyPromptPreview" style="text-align:center; padding:8px 12px; background:var(--primary-bg); border-radius:8px; font-weight:700; font-size:1rem; color:var(--primary-dark); margin-bottom:8px;">= ' + formatCurrency(unitPrice) + '/кг</div>' +
        '<div style="display:flex; gap:8px;">' +
            '<button class="btn btn-secondary btn-sm qty-prompt-cancel" style="flex:1;">Цуцлах</button>' +
            '<button class="btn btn-primary btn-sm qty-prompt-add" data-product="' + productData + '" style="flex:1;">+ Нэмэх</button>' +
        '</div>';

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) closeQuantityPrompt();
    });

    var presetBtns = box.querySelectorAll('.qty-preset');
    for (var i = 0; i < presetBtns.length; i++) {
        presetBtns[i].addEventListener('click', function() {
            try {
                var prod = JSON.parse(decodeURIComponent(this.getAttribute('data-product')));
                var qty = parseFloat(this.getAttribute('data-qty'));
                addToCartFromPrompt(prod, qty);
            } catch(ignore) {}
            closeQuantityPrompt();
        });
    }

    var cancelBtn = box.querySelector('.qty-prompt-cancel');
    if (cancelBtn) cancelBtn.addEventListener('click', closeQuantityPrompt);

    var addBtn = box.querySelector('.qty-prompt-add');
    if (addBtn) {
        addBtn.addEventListener('click', function() {
            try {
                var prod = JSON.parse(decodeURIComponent(this.getAttribute('data-product')));
                var v = parseFloat(document.getElementById('qtyPromptInput').value) || 1;
                addToCartFromPrompt(prod, v);
            } catch(ignore) {}
            closeQuantityPrompt();
        });
    }

    var input = document.getElementById('qtyPromptInput');
    var previewEl = document.getElementById('qtyPromptPreview');

    function updatePreview() {
        var v = parseFloat(input.value);
        if (!isNaN(v) && v > 0) {
            var qtyKg = product.unit === 'кг' ? v / 1000 : v;
            var total = Math.round(qtyKg * unitPrice);
            previewEl.textContent = v + ' ' + unitLabel + ' × ' + formatCurrency(unitPrice) + '/кг = ' + formatCurrency(total);
            previewEl.style.color = 'var(--primary-dark)';
        } else {
            previewEl.textContent = 'Тоо оруулна уу';
            previewEl.style.color = 'var(--text-muted)';
        }
    }

    input.addEventListener('input', updatePreview);
    input.focus();
    input.select();
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            var v = parseFloat(input.value) || 1;
            addToCartFromPrompt(product, v);
            closeQuantityPrompt();
        }
        if (e.key === 'Escape') { closeQuantityPrompt(); }
    });
    setTimeout(function() { input.focus(); input.select(); }, 80);
}

function closeQuantityPrompt() {
    var el = document.querySelector('.quantity-prompt-overlay');
    if (el) el.remove();
    refocusBarcode();
}

function addToCartFromPrompt(product, qty) {
    if (isNaN(qty) || qty <= 0) qty = 1;
    if (product.unit === 'кг') {
        qty = qty / 1000;
    }
    addToCart(product, parseFloat(qty));
}

function animateCardAdd(card) {
    card.classList.remove('added-to-cart');
    void card.offsetWidth;
    card.classList.add('added-to-cart');
    setTimeout(function() { card.classList.remove('added-to-cart'); }, 400);
}

function animateCartCount() {
    const badge = document.getElementById('cartCount');
    if (badge) {
        badge.classList.remove('bounce');
        void badge.offsetWidth;
        badge.classList.add('bounce');
        setTimeout(function() { badge.classList.remove('bounce'); }, 300);
    }
}

function removeFromCart(index) {
    var removedItem = cart[index];
    var items = document.querySelectorAll('.cart-item');
    if (items[index]) {
        items[index].style.transition = 'all 0.2s ease';
        items[index].style.opacity = '0';
        items[index].style.transform = 'translateX(30px)';
    }
    setTimeout(function() {
        cart.splice(index, 1);
        _scheduleCartPersist();
        renderCart();
        showUndoRemove(removedItem);
    }, 200);
}

var undoRemoveTimer = null;
function showUndoRemove(item) {
    if (undoRemoveTimer) clearTimeout(undoRemoveTimer);
    undoRemoveTimer = setTimeout(function() {
        var existing = document.querySelector('.undo-remove-toast');
        if (existing) existing.remove();
    }, 5000);
    var existing = document.querySelector('.undo-remove-toast');
    if (existing) existing.remove();
    var toast = document.createElement('div');
    toast.className = 'undo-remove-toast';
    var itemData = encodeURIComponent(JSON.stringify(item));
    toast.innerHTML = escapeHtml(item.product_name) + ' хасагдлаа <button data-item="' + itemData + '" class="undo-remove-btn" style="background:var(--primary); color:#fff; border:none; padding:6px 12px; border-radius:8px; font-weight:700; cursor:pointer; margin-left:6px;">↩ Буцаах</button>';
    setTimeout(function() {
        var btn = toast.querySelector('.undo-remove-btn');
        if (btn) {
            btn.addEventListener('click', function() {
                try { undoRemoveCart(JSON.parse(decodeURIComponent(this.getAttribute('data-item')))); } catch(e) {}
                var parent = this.parentElement;
                if (parent) parent.remove();
            });
        }
    }, 0);
    document.body.appendChild(toast);
}

function undoRemoveCart(item) {
    addToCart({
        id: item.product_id, barcode: item.barcode, name: item.product_name,
        price: item.unit_price, stock_qty: item.stock_qty, unit: item.unit,
        category: item.category
    });
    if (undoRemoveTimer) clearTimeout(undoRemoveTimer);
}

function startNewSale() {
    document.getElementById('saleCompleteModal').classList.remove('active');
    var container = document.querySelector('.confetti-container');
    if (container) container.remove();
    updateCustomerState('idle');
    refocusBarcode();
}

function updateQuantity(index, delta) {
    const item = cart[index];
    const newQty = item.quantity + delta;

    if (newQty <= 0) { removeFromCart(index); return; }

    item.quantity = newQty;
    item.subtotal = newQty * item.unit_price;
    _scheduleCartPersist();
    renderCart();
}

function clearCart() {
    if (cart.length === 0) return;
    showConfirm('Сагсыг цэвэрлэх үү?', '🗑 Цэвэрлэх', 'Цуцлах', function() {
        cart = [];
        clearSavedCart();
        if (_debounceCartTimer) clearTimeout(_debounceCartTimer);
        _debounceCartTimer = null;
        renderCart();
        updateCustomerState('idle');
        showNotification('Сагс цэвэрлэгдлээ', 'info');
    });
}

function getCartTotal() {
    let total = 0;
    for (let i = 0; i < cart.length; i++) {
        total += cart[i].subtotal;
        if (DISCOUNTS_ENABLED) {
            total -= (cart[i].discount_amount || 0);
        }
    }
    return total;
}

function cartToItems() {
    return cart.map(function(item) {
        var obj = {
            product_id: item.product_id === -1 ? null : item.product_id,
            product_name: item.product_name,
            barcode: item.barcode, quantity: item.quantity, unit_price: item.unit_price
        };
        if (DISCOUNTS_ENABLED) {
            obj.discount_amount = item.discount_amount || 0;
        }
        return obj;
    });
}

var _cartRenderedCount = 0;

function _buildOneCartItem(i, item) {
    var icon = getCategoryIcon(item.category);
    var color = getCategoryColor(item.category);
    var step = needsQuantityPrompt(item.unit) ? '0.01' : '1';
    var div = document.createElement('div');
    div.className = 'cart-item';
    div.setAttribute('data-cart-index', i);

    var discountHtml = '';
    if (DISCOUNTS_ENABLED) {
        discountHtml = '<div class="cart-item-discount"><label>Хямдрал: </label>' +
            '<input type="number" class="discount-input" value="' + (item.discount_amount || 0) + '" min="0" max="' + item.subtotal + '" onchange="onDiscountChange(' + i + ', this.value)" style="width:70px;"></div>';
    }

    div.innerHTML =
        '<div class="cart-item-icon" style="background:' + color + '15; color:' + color + ';">' + escapeHtml(icon) + '</div>' +
        '<div class="cart-item-info">' +
        '<div class="cart-item-name">' + escapeHtml(item.product_name) + '</div>' +
        '<div class="cart-item-detail"><div class="cart-item-qty">' +
        '<button class="qty-btn" onclick="updateQuantity(' + i + ', -1)" aria-label="Багасгах">−</button>' +
        '<input type="number" class="qty-input" value="' + item.quantity + '" min="0.01" step="' + step + '" onchange="onCartQtyChange(' + i + ', this.value)" onkeydown="onCartQtyKeyDown(event, ' + i + ', this)" aria-label="Тоо хэмжээ">' +
        '<button class="qty-btn" onclick="updateQuantity(' + i + ', 1)" aria-label="Нэмэх">+</button>' +
        '<span class="text-muted" style="margin-left:4px;">× ' + formatCurrency(item.unit_price) + '/' + escapeHtml(item.unit) + '</span>' +
        '</div>' + discountHtml + '</div></div>' +
        '<div class="cart-item-subtotal">' + formatCurrency(item.subtotal) + '</div>' +
        '<button class="cart-item-remove" onclick="removeFromCart(' + i + ')" aria-label="Устгах">✕</button>';
    return div;
}

function _updateOneCartItem(el, i, item) {
    var subtotalEl = el.querySelector('.cart-item-subtotal');
    if (subtotalEl) subtotalEl.textContent = formatCurrency(item.subtotal);
    var qtyInput = el.querySelector('.qty-input');
    if (qtyInput && document.activeElement !== qtyInput) {
        qtyInput.value = item.quantity;
    }
    var buttons = el.querySelectorAll('.qty-btn');
    if (buttons.length >= 2) {
        buttons[0].setAttribute('onclick', 'updateQuantity(' + i + ', -1)');
        buttons[1].setAttribute('onclick', 'updateQuantity(' + i + ', 1)');
    }
    if (qtyInput) {
        qtyInput.setAttribute('onchange', 'onCartQtyChange(' + i + ', this.value)');
        qtyInput.setAttribute('onkeydown', 'onCartQtyKeyDown(event, ' + i + ', this)');
    }
    var removeBtn = el.querySelector('.cart-item-remove');
    if (removeBtn) removeBtn.setAttribute('onclick', 'removeFromCart(' + i + ')');
    var discountInput = el.querySelector('.discount-input');
    if (discountInput) {
        discountInput.value = item.discount_amount || 0;
        discountInput.setAttribute('max', item.subtotal);
    }
}

function renderCart() {
    var itemsEl = document.getElementById('cartItems');
    var totalsEl = document.getElementById('cartTotals');
    var countEl = document.getElementById('cartCount');

    countEl.textContent = cart.length;

    if (cart.length === 0) {
        itemsEl.innerHTML = '<div class="cart-empty">Бараа сканнердах эсвэл<br>дарж сонгоно уу</div>';
        totalsEl.style.display = 'none';
        disableCheckoutButtons();
        _cartRenderedCount = 0;
        return;
    }

    totalsEl.style.display = 'block';

    var prevCount = _cartRenderedCount;
    var existingItems = itemsEl.querySelectorAll('.cart-item');
    var domCount = existingItems.length;

    if (domCount === 0 || prevCount === 0) {
        var frag = document.createDocumentFragment();
        for (var i = 0; i < cart.length; i++) {
            frag.appendChild(_buildOneCartItem(i, cart[i]));
        }
        itemsEl.innerHTML = '';
        itemsEl.appendChild(frag);
    } else if (cart.length > domCount) {
        for (var j = domCount; j < cart.length; j++) {
            itemsEl.appendChild(_buildOneCartItem(j, cart[j]));
        }
        var allItems = itemsEl.querySelectorAll('.cart-item');
        for (var k = 0; k < cart.length; k++) {
            _updateOneCartItem(allItems[k], k, cart[k]);
        }
    } else if (cart.length < domCount) {
        itemsEl.innerHTML = '';
        var frag2 = document.createDocumentFragment();
        for (var m = 0; m < cart.length; m++) {
            frag2.appendChild(_buildOneCartItem(m, cart[m]));
        }
        itemsEl.appendChild(frag2);
    } else {
        for (var n = 0; n < cart.length; n++) {
            _updateOneCartItem(existingItems[n], n, cart[n]);
        }
    }

    _cartRenderedCount = cart.length;

    var total = getCartTotal();
    document.getElementById('totalDisplay').textContent = formatCurrency(total);

    enableCheckoutButtons();
}

function onDiscountChange(index, val) {
    if (!DISCOUNTS_ENABLED) return;
    var item = cart[index];
    if (!item) return;
    var d = parseInt(val);
    if (isNaN(d) || d < 0) d = 0;
    if (d > item.subtotal) d = item.subtotal;
    item.discount_amount = d;
    renderCart();
}

function onCartQtyChange(index, val) {
    const item = cart[index];
    let qty = parseFloat(val);

    if (isNaN(qty) || qty <= 0) {
        removeFromCart(index);
        return;
    }

    qty = Math.round(qty * 100) / 100;

    item.quantity = qty;
    item.subtotal = qty * item.unit_price;
    _scheduleCartPersist();
    renderCart();
}

function onCartQtyKeyDown(event, index, input) {
    if (event.key === 'Enter') {
        event.preventDefault();
        input.blur();
    }
    if (event.key === 'Escape') {
        event.preventDefault();
        renderCart();
    }
}

function enableCheckoutButtons() {
    document.getElementById('btnPay').disabled = false;
    document.getElementById('btnHold').disabled = false;
}

function disableCheckoutButtons() {
    document.getElementById('btnPay').disabled = true;
    document.getElementById('btnHold').disabled = true;
}

function showPaymentSelector() {
    var sel = document.getElementById('paymentSelector');
    if (sel) sel.style.display = 'block';
}

function hidePaymentSelector() {
    var sel = document.getElementById('paymentSelector');
    if (sel) sel.style.display = 'none';
}

/* ─── BARCODE SCANNER ─── */

const barcodeInput = document.getElementById('barcodeInput');

var _barcodeBuffer = '';
var _barcodeTimer = null;
var _barcodeEnterHandler = null;

barcodeInput.addEventListener('input', function() {
    _barcodeBuffer = this.value;
    if (_barcodeTimer) clearTimeout(_barcodeTimer);
    if (_barcodeBuffer.length > 0) {
        _barcodeTimer = setTimeout(function() {
            var bc = _barcodeBuffer.trim();
            if (bc.length >= 5) {
                barcodeInput.value = '';
                _barcodeBuffer = '';
                lookupBarcode(bc);
            }
        }, 300);
    }
});

function refocusBarcode() {
    setTimeout(function() {
        const el = document.getElementById('barcodeInput');
        if (el && !isModalOpen()) { el.focus(); }
    }, 50);
}

function lookupBarcode(barcode) {
    apiRequest('/api/barcode', {
        method: 'POST',
        contentType: 'application/json',
        body: JSON.stringify({ barcode: barcode }),
        timeout: 8000
    })
    .then(function(data) {
        if (data.success && data.product) {
            playBeep();
            var product = data.product;
            if (needsQuantityPrompt(product.unit || 'ш')) {
                var fakeCard = {
                    dataset: {
                        id: product.id, barcode: product.barcode, name: product.name,
                        price: product.price, stock: product.stock_qty,
                        unit: product.unit || 'ш', category: product.category || 'Бусад',
                        imageUrl: product.image_url || ''
                    },
                    classList: { contains: function() { return false; } },
                    getBoundingClientRect: function() { return { top: 200, left: 300 }; }
                };
                showQuantityPrompt(product, fakeCard);
            } else {
                addToCart(product, 1);
            }
            showNotification(data.product.name + ' нэмэгдлээ', 'success');
        } else if (data.error === 'not_found') {
            openNotFoundModal(data.barcode);
        } else {
            showNotification(data.error || 'Алдаа гарлаа', 'error');
        }
        refocusBarcode();
    })
    .catch(function(err) {
        handleApiError(err);
        refocusBarcode();
    });
}

/* ─── SEARCH & FILTER ─── */

let currentCategory = '';
let searchDebounceTimer = null;
let productsTruncated = window.__POS_CONFIG__ && window.__POS_CONFIG__.products_truncated;

function renderSearchResults(products) {
    const grid = document.getElementById('productGrid');
    let html = '';
    if (products.length === 0) {
        html = '<div class="truncated-notice"><div class="truncated-text">Бараа олдсонгүй</div></div>';
    } else {
        products.forEach(function(p) {
            html += '<div class="product-card' + (!p.barcode && p.unit !== 'кг' ? ' no-barcode' : '') + '"'
                 + ' style="--cat-color: ' + (CATEGORY_COLORS[p.category] || '#6B7280') + '"'
                 + ' data-id="' + p.id + '"'
                 + ' data-barcode="' + (p.barcode || '') + '"'
                 + ' data-name="' + p.name.replace(/'/g, '\\x27') + '"'
                 + ' data-price="' + p.price + '"'
                 + ' data-stock="9999"'
                 + ' data-unit="' + (p.unit || 'ш') + '"'
                 + ' data-category="' + (p.category || '') + '"'
                 + ' data-image-url="' + (p.image_url || '') + '"'
                 + ' onclick="addToCartFromGrid(this)">'
                 + (p.image_url ? '<img src="' + p.image_url + '" alt="' + p.name.replace(/'/g, '\\x27') + '" loading="lazy" class="card-icon" style="width:3.2rem; height:3.2rem; object-fit:cover; border-radius:8px; display:block;">'
                              : '<div class="card-icon">' + (CATEGORY_ICONS[p.category] || '📦') + '</div>')
                 + '<div class="card-name">' + p.name + '</div>'
                 + '<div class="card-price">' + p.price.toLocaleString() + ' ₮</div>'
                 + '</div>';
        });
    }
    grid.innerHTML = html;
}

function filterProducts() {
    const query = document.getElementById('searchInput').value.toLowerCase();
    if (productsTruncated) {
        var params = '?q=' + encodeURIComponent(query);
        if (currentCategory) params += '&category=' + encodeURIComponent(currentCategory);
        apiRequest('/api/products/search' + params, { method: 'GET', timeout: 5000 })
            .then(function(data) {
                renderSearchResults(data.products || []);
            })
            .catch(function(err) {
                handleApiError(err);
            });
        return;
    }
    const cards = document.querySelectorAll('.product-card');
    cards.forEach(function(card) {
        const name = card.dataset.name.toLowerCase();
        const barcode = card.dataset.barcode.toLowerCase();
        const category = card.dataset.category;
        const matchSearch = !query || name.indexOf(query) !== -1 || barcode.indexOf(query) !== -1;
        const matchCat = !currentCategory || category === currentCategory;
        card.style.display = (matchSearch && matchCat) ? '' : 'none';
    });
}

function onSearchInput() {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(filterProducts, 150);
}

function filterByCategory(category, btn) {
    currentCategory = category;
    document.querySelectorAll('.category-btn').forEach(function(b) { b.classList.remove('active'); });
    btn.classList.add('active');
    filterProducts();
}

function scrollCategoryFilter(dir) {
    var container = document.getElementById('categoryFilter');
    if (!container) return;
    var scrollAmount = container.clientWidth * 0.6;
    var isLowPerf = document.documentElement.getAttribute('data-perf') === 'low';
    container.scrollBy({ left: dir * scrollAmount, behavior: isLowPerf ? 'auto' : 'smooth' });
}

function updateCategoryScrollButtons() {
    var container = document.getElementById('categoryFilter');
    var leftBtn = document.getElementById('catScrollLeft');
    var rightBtn = document.getElementById('catScrollRight');
    if (!container || !leftBtn || !rightBtn) return;
    leftBtn.style.display = container.scrollLeft > 5 ? '' : 'none';
    rightBtn.style.display = container.scrollLeft < container.scrollWidth - container.clientWidth - 5 ? '' : 'none';
}

document.addEventListener('DOMContentLoaded', function() {
    var container = document.getElementById('categoryFilter');
    if (container) {
        container.addEventListener('scroll', updateCategoryScrollButtons);
        setTimeout(updateCategoryScrollButtons, 100);
    }
});

/* ─── CHECKOUT ─── */

function openCheckout(paymentType) {
    if (cart.length === 0) return;
    hidePaymentSelector();
    currentPaymentType = paymentType;
    const total = getCartTotal();

    document.getElementById('checkoutTotal').textContent = formatCurrency(total);
    document.getElementById('checkoutModal').classList.add('active');
    updateCustomerState('paying');

    var modal = document.getElementById('checkoutModal');
    document.getElementById('cashSection').style.display = paymentType === 'cash' ? 'block' : 'none';
    document.getElementById('cardSection').style.display = paymentType === 'card' ? 'block' : 'none';
    document.getElementById('qrSection').style.display = paymentType === 'qr' ? 'block' : 'none';
    var splitEl = document.getElementById('splitSection');
    if (splitEl) splitEl.style.display = 'none';

    var titles = { cash: '💵 Бэлнээр төлөх', card: '💳 Картаар төлөх', split: '🔀 Холимог төлбөр', qr: '📱 QR төлбөр' };
    document.getElementById('checkoutTitle').textContent = titles[paymentType] || 'Төлбөр';

    if (paymentType === 'cash') {
        document.getElementById('cashGivenInput').value = '';
        document.getElementById('changeRow').style.display = 'none';
        setTimeout(function() { document.getElementById('cashGivenInput').focus(); }, 100);
    } else if (paymentType === 'card') {
        document.getElementById('cardAmountDisplay').textContent = formatCurrency(total);
    } else if (paymentType === 'qr') {
        document.getElementById('qrAmountDisplay').textContent = formatCurrency(total);
        document.getElementById('qrNoImage').style.display = 'block';
        document.getElementById('qrNoImage').textContent = '⏳ QPay нэхэмжлэх үүсгэж байна...';
        document.getElementById('qrPaymentStatus').style.display = 'none';
        document.getElementById('qpayTimer').style.display = 'none';
        qpayInvoiceId = null;
        qpayPollCount = 0;
        // Create QPay invoice
        createQPayInvoice(total);
    }
}

function calculateChange() {
    const total = getCartTotal();
    const given = parseInt(document.getElementById('cashGivenInput').value) || 0;
    const change = given - total;
    if (given > 0 && change >= 0) {
        document.getElementById('changeRow').style.display = 'flex';
        document.getElementById('changeDisplay').textContent = formatCurrency(change);
    } else {
        document.getElementById('changeRow').style.display = 'none';
    }
}

function setCashAmount(amount) {
    document.getElementById('cashGivenInput').value = amount;
    calculateChange();
}

function setExactAmount() {
    const total = getCartTotal();
    document.getElementById('cashGivenInput').value = total;
    calculateChange();
}

let _updatingSplit = false;

function onSplitCardChange() {
    if (_updatingSplit) return;
    _updatingSplit = true;
    try {
        const total = getCartTotal();
        let cardAmt = parseInt(document.getElementById('splitCardAmount').value) || 0;
        if (cardAmt < 0) { cardAmt = 0; document.getElementById('splitCardAmount').value = 0; }
        if (cardAmt > total) { cardAmt = total; document.getElementById('splitCardAmount').value = total; }

        const remaining = total - cardAmt;
        document.getElementById('splitCashAmount').value = remaining > 0 ? remaining : 0;
        updateSplitRemaining();

        if (cardAmt > 0) {
            document.getElementById('splitCardInstruction').style.display = 'block';
            document.getElementById('splitCardDisplay').textContent = formatCurrency(cardAmt);
        } else {
            document.getElementById('splitCardInstruction').style.display = 'none';
        }
    } finally {
        _updatingSplit = false;
    }
}

function onSplitCashChange() {
    if (_updatingSplit) return;
    _updatingSplit = true;
    try {
        const total = getCartTotal();
        let cashAmt = parseInt(document.getElementById('splitCashAmount').value) || 0;
        if (cashAmt < 0) { cashAmt = 0; document.getElementById('splitCashAmount').value = 0; }
        if (cashAmt > total) { cashAmt = total; document.getElementById('splitCashAmount').value = total; }

        const remaining = total - cashAmt;
        document.getElementById('splitCardAmount').value = remaining > 0 ? remaining : 0;
        updateSplitRemaining();

        const cardAmt = parseInt(document.getElementById('splitCardAmount').value) || 0;
        if (cardAmt > 0) {
            document.getElementById('splitCardInstruction').style.display = 'block';
            document.getElementById('splitCardDisplay').textContent = formatCurrency(cardAmt);
        } else {
            document.getElementById('splitCardInstruction').style.display = 'none';
        }
    } finally {
        _updatingSplit = false;
    }
}

function calculateSplit() {
    onSplitCardChange();
}

function updateSplitRemaining() {
    const total = getCartTotal();
    const cardAmt = parseInt(document.getElementById('splitCardAmount').value) || 0;
    const cashAmt = parseInt(document.getElementById('splitCashAmount').value) || 0;
    const remaining = total - cardAmt - cashAmt;
    const el = document.getElementById('splitRemaining');
    if (remaining > 0) {
        el.textContent = 'Үлдэгдэл: ' + formatCurrency(remaining);
        el.style.color = 'var(--warning)';
    } else if (remaining < 0) {
        el.textContent = 'Хэтэрсэн: ' + formatCurrency(Math.abs(remaining));
        el.style.color = 'var(--error)';
    } else {
        el.textContent = '✓ Бүрэн төлсөн';
        el.style.color = 'var(--primary)';
    }
}

/* ─── TERMINAL PAYMENT (Pax A930) ─── */

function terminalCheckout() {
    var btn = document.getElementById('btnSendTerminal');
    var statusEl = document.getElementById('terminalStatus');

    btn.disabled = true;
    btn.textContent = '⏳ Терминал руу илгээж байна...';
    statusEl.textContent = 'PAX холбогдож байна...';
    statusEl.style.color = 'var(--text-secondary)';
    document.getElementById('loadingOverlay').classList.add('active');

    var items = cartToItems();
    var body = {
        items: items,
        payment_type: 'card',
        customer_tin: document.getElementById('customerTinInput') ? document.getElementById('customerTinInput').value.trim() : '',
    };

    apiRequest('/api/terminal/checkout', {
        method: 'POST',
        contentType: 'application/json',
        body: JSON.stringify(body),
        timeout: 120000
    })
    .then(function(data) {
        document.getElementById('loadingOverlay').classList.remove('active');
        if (data.success) {
            statusEl.textContent = '✓ Төлбөр амжилттай';
            statusEl.style.color = 'var(--primary)';
            btn.textContent = '✅ Амжилттай';
            cart = [];
            clearSavedCart();
            closeCheckout();
            lastSaleId = data.sale.id;
            showSaleComplete(data.sale);
            renderCart();
            refreshProductGrid();
            refocusBarcode();
        } else {
            statusEl.textContent = '✕ ' + (data.error || 'PAX алдаа');
            statusEl.style.color = 'var(--danger)';
            btn.disabled = false;
            btn.textContent = '📟 Терминал руу илгээх';
            showNotification(data.error || 'Картын төлбөр амжилтгүй', 'error');
            refocusBarcode();
        }
    })
    .catch(function(err) {
        document.getElementById('loadingOverlay').classList.remove('active');
        statusEl.textContent = '✕ ' + (err.message || 'Сүлжээний алдаа');
        statusEl.style.color = 'var(--danger)';
        btn.disabled = false;
        btn.textContent = '📟 Терминал руу илгээх';
        handleApiError(err);
        refocusBarcode();
    });
}

function confirmSale() {
    const total = getCartTotal();
    let cashGiven = 0, cardAmount = 0, cashAmount = 0;

    if (currentPaymentType === 'cash') {
        cashGiven = parseInt(document.getElementById('cashGivenInput').value) || 0;
        if (cashGiven < total) {
            showNotification('Бэлэн мөнгө хүрэлцэхгүй байна!', 'error');
            return;
        }
    } else if (currentPaymentType === 'card') {
        terminalCheckout();
        return;
    } else if (currentPaymentType === 'qr') {
        cardAmount = total;
    }

    const items = cartToItems();

    var idempotencyKey = 'sale_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

    var confirmBtn = document.getElementById('confirmCheckout');
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.textContent = '⏳ Хийгдэж байна...';
    }
    document.getElementById('loadingOverlay').classList.add('active');

    var body = {
        items: items, payment_type: currentPaymentType,
        cash_given: cashGiven, card_amount: cardAmount, cash_amount: cashAmount,
        idempotency_key: idempotencyKey,
        customer_tin: document.getElementById('customerTinInput') ? document.getElementById('customerTinInput').value.trim() : '',
    };
    if (currentPaymentType === 'qr' && qpayInvoiceId) {
        body.qpay_invoice_id = qpayInvoiceId;
    }
    if (lastTerminalResult !== null && lastTerminalResult !== undefined) {
        body.terminal_payment = lastTerminalResult;
    }

    apiRequest('/api/checkout', {
        method: 'POST',
        contentType: 'application/json',
        body: JSON.stringify(body),
        timeout: 30000,
        maxRetries: 1
    })
    .then(function(data) {
        document.getElementById('loadingOverlay').classList.remove('active');
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = '✓ Баталгаажуулах';
        }

        if (data.success) {
            cart = [];
            clearSavedCart();
            closeCheckout();
            lastSaleId = data.sale.id;
            showSaleComplete(data.sale);
            renderCart();
            refreshProductGrid();
        } else {
            showNotification(data.error || 'Борлуулалт амжилтгүй', 'error');
        }
        refocusBarcode();
    })
    .catch(function(err) {
        document.getElementById('loadingOverlay').classList.remove('active');
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = '✓ Баталгаажуулах';
        }
        handleApiError(err);
        refocusBarcode();
    });
}

function refreshProductGrid() {
    // Stock tracking removed — no refresh needed.
}

/* ─── SALE COMPLETE ─── */

function showSaleComplete(sale) {
    let html = '';
    if (sale.items) {
        for (let i = 0; i < sale.items.length; i++) {
            const item = sale.items[i];
            html += '<div>' + escapeHtml(item.product_name) + '</div>';
            html += '<div class="receipt-row"><span>' + item.quantity + ' × ' + formatCurrency(item.unit_price) + '</span><span>' + formatCurrency(item.subtotal) + '</span></div>';
        }
    }
    html += '<div class="receipt-divider"></div>';
    html += '<div class="receipt-row"><span>Нийт:</span><span><strong>' + formatCurrency(sale.total) + '</strong></span></div>';
    html += '<div class="receipt-divider"></div>';

    var payTypes = { cash: 'Бэлэн', card: 'Карт', split: 'Холимог', qr: 'QR' };
    html += '<div class="receipt-row"><span>Төлбөр:</span><span>' + (payTypes[sale.payment_type] || '') + '</span></div>';
    if (sale.payment_type === 'cash') {
        html += '<div class="receipt-row"><span>Өгсөн:</span><span>' + formatCurrency(sale.cash_given) + '</span></div>';
        html += '<div class="receipt-row"><span>Буцаалт:</span><span>' + formatCurrency(sale.change_given) + '</span></div>';
    } else if (sale.payment_type === 'split') {
        html += '<div class="receipt-row"><span>Карт:</span><span>' + formatCurrency(sale.card_amount) + '</span></div>';
        html += '<div class="receipt-row"><span>Бэлэн:</span><span>' + formatCurrency(sale.cash_amount) + '</span></div>';
    }

    html += '<div class="receipt-divider"></div>';
    if (sale.terminal_txn_id) {
        html += '<div class="receipt-row text-muted" style="font-size:0.8rem;"><span>PAX гүйлгээ:</span><span>' + escapeHtml(sale.terminal_txn_id) + '</span></div>';
    }
    if (sale.ebarimt_status === 'sent') {
        html += '<div class="receipt-center text-success">✓ eBarimt илгээгдлээ</div>';
        if (sale.ebarimt_lottery) {
            html += '<div class="receipt-center" style="font-size:1.2rem; font-weight:700;">🎰 Сугалаа: ' + sale.ebarimt_lottery + '</div>';
        }
    } else if (sale.ebarimt_status === 'skipped') {
        html += '<div class="receipt-center text-muted">eBarimt: Тохиргоо хийгдээгүй</div>';
    } else {
        html += '<div class="receipt-center text-warning">eBarimt: Дахин оролдоно</div>';
    }

    html += '<div class="receipt-divider"></div>';
    html += '<div class="receipt-center">Баярлалаа! Дахин үйлчлүүлнэ үү.</div>';

    document.getElementById('receiptPreview').innerHTML = html;

    const printErrorDiv = document.getElementById('printErrorMessage');
    if (sale.print_status && !sale.print_status.success) {
        printErrorDiv.style.display = 'block';
    } else {
        printErrorDiv.style.display = 'none';
    }

    updateCustomerState('complete', {
        lottery: sale.ebarimt_lottery || '',
        cash_given: sale.cash_given || 0,
        change_given: sale.change_given || 0,
        card_amount: sale.card_amount || 0,
        items: [],
        total: sale.total || getCartTotal()
    });
    document.getElementById('saleCompleteModal').classList.add('active');
    showConfetti();
}

function closeSaleComplete() {
    document.getElementById('saleCompleteModal').classList.remove('active');
    const container = document.querySelector('.confetti-container');
    if (container) container.remove();
    updateCustomerState('idle');
    refocusBarcode();
}

function showConfetti() {
    if (document.documentElement.getAttribute('data-perf') === 'low') return;
    let container = document.querySelector('.confetti-container');
    if (container) container.remove();
    container = document.createElement('div');
    container.className = 'confetti-container';
    document.body.appendChild(container);
    const colors = ['#00ff88', '#ffcc00', '#3B82F6', '#EF4444', '#A855F7', '#22C55E', '#F59E0B', '#06B6D4'];
    for (let i = 0; i < 60; i++) {
        const piece = document.createElement('div');
        piece.className = 'confetti-piece';
        piece.style.left = (Math.random() * 100) + '%';
        piece.style.background = colors[Math.floor(Math.random() * colors.length)];
        piece.style.width = (6 + Math.random() * 8) + 'px';
        piece.style.height = (6 + Math.random() * 8) + 'px';
        piece.style.borderRadius = Math.random() > 0.5 ? '50%' : '2px';
        piece.style.animationDuration = (2 + Math.random() * 3) + 's';
        piece.style.animationDelay = (Math.random() * 1.5) + 's';
        container.appendChild(piece);
    }
    setTimeout(function() { if (container.parentNode) container.remove(); }, 5000);
}

function reprintReceipt() {
    if (!lastSaleId) return;
    apiRequest('/api/reprint/' + lastSaleId, { method: 'POST', timeout: 15000 })
        .then(function(data) {
            if (data.success) {
                document.getElementById('printErrorMessage').style.display = 'none';
                showNotification('Баримт хэвлэгдлээ!', 'success');
            } else {
                document.getElementById('printErrorMessage').style.display = 'block';
            }
        })
        .catch(function(err) { handleApiError(err); });
}

/* ─── BARCODE NOT FOUND ─── */

function openNotFoundModal(barcode) {
    document.getElementById('notFoundBarcode').textContent = barcode;
    document.getElementById('newProductBarcode').value = barcode;
    document.getElementById('newProductName').value = '';
    document.getElementById('newProductPrice').value = '';
    document.getElementById('newProductCategory').value = 'Бусад';
    document.getElementById('notFoundModal').classList.add('active');
    setTimeout(function() { document.getElementById('newProductName').focus(); }, 100);
}

function closeNotFound() {
    document.getElementById('notFoundModal').classList.remove('active');
    refocusBarcode();
}

/* ─── POS QUICK-CREATE CATEGORY ADD ─── */

function showPosCatInput() {
    var inputDiv = document.getElementById('newProductCategoryInput');
    inputDiv.style.display = 'flex';
    var input = document.getElementById('newProductCategoryInputText');
    input.value = '';
    input.focus();
    input.addEventListener('keydown', function handler(e) {
        if (e.key === 'Enter') { posAddCategory(); }
        if (e.key === 'Escape') { inputDiv.style.display = 'none'; input.removeEventListener('keydown', handler); }
    });
}

function posAddCategory() {
    var input = document.getElementById('newProductCategoryInputText');
    var name = input.value.trim();
    if (!name) return;

    var btn = document.querySelector('#newProductCategoryInput .btn-primary');
    btn.disabled = true;
    btn.textContent = '...';

    apiRequest('/api/category/add', {
        method: 'POST',
        contentType: 'application/json',
        body: JSON.stringify({ name: name }),
        timeout: 10000
    }).then(function(data) {
        if (data.success) {
            var select = document.getElementById('newProductCategory');
            var opt = document.createElement('option');
            opt.value = data.name;
            opt.textContent = data.name;
            select.appendChild(opt);
            select.value = data.name;
            document.getElementById('newProductCategoryInput').style.display = 'none';
        } else {
            showNotification(data.error || 'Ангилал үүсгэж чадсангүй', 'error');
        }
        btn.disabled = false;
        btn.textContent = '✓';
    }).catch(function(err) {
        showNotification('Сүлжээний алдаа', 'error');
          btn.disabled = false;
          btn.textContent = '✓';
      });
}

function createProductFromNotFound() {
    const barcode = document.getElementById('newProductBarcode').value;
    const name = document.getElementById('newProductName').value.trim();
    const price = parseInt(document.getElementById('newProductPrice').value) || 0;
    const category = document.getElementById('newProductCategory').value.trim() || 'Бусад';
    const unit = document.getElementById('newProductUnit').value;

    if (!name) { showNotification('Барааны нэр оруулна уу', 'error'); return; }
    if (price <= 0) { showNotification('Үнэ 0-ээс их байх ёстой', 'error'); return; }

    apiRequest('/api/product/create', {
        method: 'POST',
        contentType: 'application/json',
        body: JSON.stringify({ barcode: barcode, name: name, price: price, stock_qty: 9999, category: category, unit: unit }),
        timeout: 10000
    })
    .then(function(data) {
        if (data.success && data.product) {
            addToCart(data.product);
            showNotification(name + ' үүсгэгдэж, сагсанд нэмэгдлээ', 'success');
            closeNotFound();
            addProductToGrid(data.product);
        } else {
            showNotification(data.error || 'Бараа үүсгэхэд алдаа', 'error');
        }
    })
    .catch(function(err) { handleApiError(err); });
}

function addProductToGrid(product) {
    const grid = document.getElementById('productGrid');
    if (!grid) return;
    const icon = getCategoryIcon(product.category || 'Бусад');
    const color = getCategoryColor(product.category || 'Бусад');

    const card = document.createElement('div');
    card.className = 'product-card';
    card.dataset.id = product.id;
    card.dataset.barcode = product.barcode;
    card.dataset.name = product.name;
    card.dataset.price = product.price;
    card.dataset.stock = '9999';
    card.dataset.unit = product.unit || 'ш';
    card.dataset.category = product.category || 'Бусад';
    card.setAttribute('onclick', 'addToCartFromGrid(this)');
    card.style.setProperty('--cat-color', color);

    if (product.image_url) {
        card.innerHTML = '<img src="' + escapeHtml(product.image_url) + '" alt="' + escapeHtml(product.name) + '" loading="lazy" style="width:3.2rem; height:3.2rem; object-fit:cover; border-radius:8px; display:block; margin:0 auto 10px;">' +
            '<div class="card-name">' + escapeHtml(product.name) + '</div>' +
            '<div class="card-price">' + formatCurrency(product.price) + '</div>';
    } else {
        card.innerHTML = '<div class="card-icon">' + escapeHtml(icon) + '</div>' +
            '<div class="card-name">' + escapeHtml(product.name) + '</div>' +
            '<div class="card-price">' + formatCurrency(product.price) + '</div>';
    }

    grid.prepend(card);

    if (!product.barcode && product.unit !== 'кг') {
        card.classList.add('no-barcode');
    }
}

/* ─── KEYBOARD SHORTCUTS ─── */

let gridSelectedIndex = -1;

function getVisibleCards() {
    const all = document.querySelectorAll('#productGrid .product-card');
    const visible = [];
    for (let i = 0; i < all.length; i++) {
        if (all[i].style.display !== 'none') visible.push(all[i]);
    }
    return visible;
}

function selectGridCard(index) {
    const cards = getVisibleCards();
    cards.forEach(function(c) { c.classList.remove('grid-selected'); });
    gridSelectedIndex = index;
    if (index >= 0 && index < cards.length) {
        cards[index].classList.add('grid-selected');
        cards[index].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
}

function addSelectedToCart() {
    const cards = getVisibleCards();
    if (gridSelectedIndex >= 0 && gridSelectedIndex < cards.length) {
        addToCartFromGrid(cards[gridSelectedIndex]);
    }
}

function isSaleCompleteModalOpen() {
    return document.getElementById('saleCompleteModal').classList.contains('active');
}

document.addEventListener('keydown', function(e) {
    // Fast path: barcode scanner input — skip all checks
    if (e.target === barcodeInput) return;

    if (isSaleCompleteModalOpen()) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            startNewSale();
            return;
        }
        if (e.key === 'p' || e.key === 'P') {
            e.preventDefault();
            reprintReceipt();
            return;
        }
    }

    var targetTag = (e.target.tagName || '').toLowerCase();
    var isInput = (targetTag === 'input' || targetTag === 'textarea' || targetTag === 'select');
    if (e.key === 'F1') { e.preventDefault(); toggleHelp(); }
    if (e.key === 'F2') { e.preventDefault(); if (cart.length > 0) openCheckout('cash'); }
    if (e.key === 'F4') { e.preventDefault(); if (cart.length > 0) openCheckout('card'); }
    if (e.key === 'F5') { e.preventDefault(); if (cart.length > 0) openCheckout('qr'); }
    if (e.key === 'F6') { e.preventDefault(); showAnonymousPricePrompt(); }
    if (e.key === 'F3') { e.preventDefault(); if (cart.length > 0) holdOrder(); }
    if (e.key === 'Escape') {
        var ps = document.getElementById('paymentSelector');
        if (ps && ps.style.display === 'block') { hidePaymentSelector(); }
        else if (isModalOpen()) { closeAllModals(); }
        else if (cart.length > 0) { clearCart(); }
    }
    if (/^[0-6]$/.test(e.key) && isCheckoutModalOpen() && !isInput) {
        e.preventDefault();
        const quickAmounts = { '1': 1000, '2': 5000, '3': 10000, '4': 20000, '5': 50000, '6': 100000, '0': getCartTotal() };
        setCashAmount(quickAmounts[e.key]);
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault();
        const searchInput = document.getElementById('searchInput');
        if (searchInput) { searchInput.focus(); }
    }

    /* Arrow-key grid navigation (only when no modal is open) */
    if (!isModalOpen() && (e.key === 'ArrowRight' || e.key === 'ArrowLeft' || e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        e.preventDefault();
        const cards = getVisibleCards();
        if (cards.length === 0) return;
        if (gridSelectedIndex < 0 || gridSelectedIndex >= cards.length) {
            selectGridCard(0);
            return;
        }
        const grid = document.getElementById('productGrid');
        let cols = 1;
        if (cards[0]) { cols = Math.max(1, Math.floor(grid.offsetWidth / (cards[0].offsetWidth + 12))); }
        let idx = gridSelectedIndex;
        if (e.key === 'ArrowRight') { idx = Math.min(cards.length - 1, idx + 1); }
        else if (e.key === 'ArrowLeft') { idx = Math.max(0, idx - 1); }
        else if (e.key === 'ArrowDown') { idx = Math.min(cards.length - 1, idx + cols); }
        else if (e.key === 'ArrowUp') { idx = Math.max(0, idx - cols); }
        selectGridCard(idx);
    }
    if (!isModalOpen() && e.key === 'Enter' && gridSelectedIndex >= 0) {
        e.preventDefault();
        addSelectedToCart();
    }
});

document.addEventListener('click', function(e) {
    const tag = e.target.tagName.toLowerCase();
    if (tag === 'input' || tag === 'button' || tag === 'select' || tag === 'textarea') return;
    if (e.target.closest('.modal')) return;
    if (e.target.closest('.cart-item-qty')) return;
    if (e.target.closest('.payment-selector')) return;
    if (e.target.closest('.checkout-area')) return;
    hidePaymentSelector();
    refocusBarcode();
});

/* Click on a product card selects it */
document.addEventListener('click', function(e) {
    const card = e.target.closest('.product-card');
    if (card && !card.classList.contains('product-card-disabled')) {
        const cards = getVisibleCards();
        for (let i = 0; i < cards.length; i++) {
            if (cards[i] === card) { selectGridCard(i); break; }
        }
    }
});

/* ─── UTILITIES ─── */

function isModalOpen() { return document.querySelectorAll('.modal-overlay.active').length > 0; }
function isCheckoutModalOpen() { return document.getElementById('checkoutModal').classList.contains('active'); }

function closeAllModals() {
    document.querySelectorAll('.modal-overlay.active').forEach(function(m) { m.classList.remove('active'); });
    refocusBarcode();
}

function toggleHelp() {
    const el = document.getElementById('helpModal');
    if (el.classList.contains('active')) {
        el.classList.remove('active');
        refocusBarcode();
    } else {
        el.classList.add('active');
    }
}

function closeHelp() {
    document.getElementById('helpModal').classList.remove('active');
    refocusBarcode();
}

function escapeHtml(text) {
    var s = String(text);
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function showNotification(message, type) {
    type = type || 'info';
    let container = document.querySelector('.flash-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'flash-container';
        document.body.appendChild(container);
    }
    const flash = document.createElement('div');
    flash.className = 'flash flash-' + type;
    var closeBtn = '<button class="flash-close" onclick="this.parentElement.remove()">&times;</button>';
    flash.innerHTML = escapeHtml(message) + closeBtn;
    container.appendChild(flash);
    var isLowPerf = document.documentElement.getAttribute('data-perf') === 'low';
    var duration = isLowPerf ? 1500 : 3000;
    setTimeout(function() {
        if (isLowPerf) {
            flash.remove();
        } else {
            flash.style.opacity = '0';
            flash.style.transform = 'translateX(100%)';
            setTimeout(function() { flash.remove(); }, 500);
        }
    }, duration);
}

function showConfirm(message, confirmLabel, cancelLabel, onConfirm) {
    confirmLabel = confirmLabel || '✓ Тийм';
    cancelLabel = cancelLabel || '✕ Үгүй';
    var existing = document.querySelector('.confirm-overlay');
    if (existing) existing.remove();

    var overlay = document.createElement('div');
    overlay.className = 'confirm-overlay';

    var box = document.createElement('div');
    box.className = 'confirm-box';

    box.innerHTML =
        '<div style="font-size:1.1rem; font-weight:600; margin-bottom:20px; color:var(--text);">' + escapeHtml(message) + '</div>' +
        '<div style="display:flex; gap:10px;">' +
            '<button class="btn btn-secondary" style="flex:1; padding:12px;" id="confirmCancelBtn">' + escapeHtml(cancelLabel) + '</button>' +
            '<button class="btn btn-primary" style="flex:1; padding:12px;" id="confirmOkBtn">' + escapeHtml(confirmLabel) + '</button>' +
        '</div>';

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    var close = function() {
        document.removeEventListener('keydown', escHandler);
        overlay.remove();
    };

    document.getElementById('confirmOkBtn').addEventListener('click', function() {
        close();
        if (onConfirm) onConfirm();
    });
    document.getElementById('confirmCancelBtn').addEventListener('click', close);
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) close();
    });
    document.addEventListener('keydown', escHandler);
    function escHandler(e) {
        if (e.key === 'Escape') { close(); }
    }
    setTimeout(function() {
        var okBtn = document.getElementById('confirmOkBtn');
        if (okBtn) okBtn.focus();
    }, 50);
}

/* ─── HELD ORDERS (Suspend / Recall) ─── */

function holdOrder() {
    if (cart.length === 0) return;
    const label = 'Захиалга #' + new Date().toLocaleTimeString('mn-MN', {hour: '2-digit', minute: '2-digit'});
    apiRequest('/api/hold-order', {
        method: 'POST',
        contentType: 'application/json',
        body: JSON.stringify({
            label: label,
            items: cartToItems(),
            total: getCartTotal()
        }),
        timeout: 10000
    })
    .then(function(data) {
        if (data.success) {
            showNotification('Захиалга хүлээлгээлээ', 'success');
            cart = [];
            clearSavedCart();
            renderCart();
            updateCustomerState('idle');
            loadHeldOrdersCount();
            refocusBarcode();
        } else {
            showNotification(data.error || 'Алдаа гарлаа', 'error');
        }
    })
    .catch(function(err) { handleApiError(err); });
}

function showHeldOrders() {
    apiRequest('/api/held-orders', { timeout: 10000 })
        .then(function(data) {
            const modal = document.getElementById('heldOrdersModal');
            const list = document.getElementById('heldOrdersList');
            if (!data.orders || data.orders.length === 0) {
                list.innerHTML = '<p class="text-muted" style="text-align:center; padding:30px;">Хүлээлгэсэн захиалга байхгүй</p>';
            } else {
                let html = '';
                data.orders.forEach(function(order) {
                    html += '<div style="display:flex; justify-content:space-between; align-items:center; padding:14px; border:1px solid var(--border); border-radius:var(--radius); margin-bottom:10px;">';
                    html += '<div>';
                    html += '<div style="font-weight:700; font-size:1rem;">' + escapeHtml(order.label) + '</div>';
                    html += '<div class="text-muted" style="font-size:0.85rem;">' + order.items.length + ' бараа · ' + formatCurrency(order.total) + ' · ' + order.created_at + '</div>';
                    html += '</div>';
                    html += '<div style="display:flex; gap:8px;">';
                    html += '<button class="btn btn-primary" onclick="recallOrder(' + order.id + ')">🔄 Сэргээх</button>';
                    html += '<button class="btn btn-danger btn-sm" onclick="deleteHeldOrder(' + order.id + ')">✕</button>';
                    html += '</div>';
                    html += '</div>';
                });
                list.innerHTML = html;
            }
            modal.classList.add('active');
        })
        .catch(function(err) { handleApiError(err); });
}

function closeHeldOrders() {
    document.getElementById('heldOrdersModal').classList.remove('active');
    refocusBarcode();
}

function recallOrder(orderId) {
    apiRequest('/api/recall-order/' + orderId, { method: 'POST', timeout: 10000 })
        .then(function(data) {
            if (data.success && data.order) {
                cart = data.order.items.map(function(item) {
                    return {
                        product_id: item.product_id,
                        product_name: item.product_name,
                        barcode: item.barcode || '',
                        quantity: item.quantity,
                        unit_price: item.current_price || item.unit_price,
                        subtotal: (item.current_price || item.unit_price) * item.quantity,
                        unit: item.unit || 'ш',
                        category: item.category || 'Бусад',
                        stock_qty: item.stock_qty || 0
                    };
                });
                renderCart();
                updateCustomerState(cart.length > 0 ? 'shopping' : 'idle');
                closeHeldOrders();
                loadHeldOrdersCount();
                showNotification('Захиалга сэргээгдлээ', 'success');
                refocusBarcode();
            } else {
                showNotification(data.error || 'Сэргээхэд алдаа', 'error');
            }
        })
        .catch(function(err) { handleApiError(err); });
}

function deleteHeldOrder(orderId) {
    showConfirm('Энэ захиалгыг устгах уу?', '✕ Устгах', 'Цуцлах', function() {
        apiRequest('/api/delete-held-order/' + orderId, { method: 'POST', timeout: 10000 })
            .then(function(data) {
                if (data.success) {
                    showHeldOrders();
                    loadHeldOrdersCount();
                    showNotification('Захиалга устгагдлаа', 'info');
                } else {
                    showNotification(data.error || 'Устгахэд алдаа', 'error');
                }
            })
            .catch(function(err) { handleApiError(err); });
    });
}

function loadHeldOrdersCount() {
    apiRequest('/api/held-orders', { timeout: 8000, maxRetries: 0 })
        .then(function(data) {
            const count = (data.orders && data.orders.length) || 0;
            const badge = document.getElementById('heldOrdersCount');
            if (badge) {
                if (count > 0) {
                    badge.textContent = count;
                    badge.style.display = 'inline-flex';
                } else {
                    badge.style.display = 'none';
                }
            }
        })
        .catch(function() {});
}

function handleCheckoutEnter(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        const total = getCartTotal();
        if (currentPaymentType === 'cash') {
            const given = parseInt(document.getElementById('cashGivenInput').value) || 0;
            if (given < total) {
                showNotification('Бэлэн мөнгө хүрэлцэхгүй байна!', 'error');
                return;
            }
        }
        confirmSale();
    }
}

window.addEventListener('beforeunload', function() {
    saveCart();
});

window.addEventListener('load', function() {
    if (cart.length > 0) {
        renderCart();
        updateCustomerState('shopping');
    }
    refocusBarcode();
    loadHeldOrdersCount();

    const cashInput = document.getElementById('cashGivenInput');
    const tinInput = document.getElementById('customerTinInput');

    if (cashInput) cashInput.addEventListener('keydown', handleCheckoutEnter);
    if (tinInput) tinInput.addEventListener('keydown', handleCheckoutEnter);

    // Periodic connection check
    setInterval(function() {
        fetch('/api/health', { method: 'GET', cache: 'no-store' })
            .then(function(r) {
                CONNECTION_ONLINE = r.ok;
                updateConnectionStatus();
            })
            .catch(function() {
                CONNECTION_ONLINE = false;
                updateConnectionStatus();
            });
    }, 15000);
});

/* ─── QPay QR PAYMENT ─── */

function createQPayInvoice(total) {
    var items = cartToItems();
    if (!items.length) return;

    qpayPollCount = 0;
    var ccBtn = document.getElementById('confirmCheckout');
    if (ccBtn) ccBtn.disabled = true;
    document.getElementById('qrPaymentStatus').style.display = 'none';

    apiRequest('/api/qpay/invoice', {
        method: 'POST',
        contentType: 'application/json',
        body: JSON.stringify({ items: items, amount: total, description: 'POS борлуулалт' }),
        timeout: 15000
    })
    .then(function(data) {
        if (data.success) {
            qpayInvoiceId = data.invoice_id;
            document.getElementById('qrNoImage').textContent = '📱 QR код үйлчлүүлэгчийн дэлгэцэнд гарлаа';
            var statusEl = document.getElementById('qrPaymentStatus');
            statusEl.textContent = '📱 QR уншуулж байна...';
            statusEl.className = 'qr-status-pending';
            statusEl.style.display = 'block';
            var timerEl = document.getElementById('qpayTimer');
            timerEl.style.display = 'block';
            timerEl.textContent = 'Хүчингүй болох хугацаа: ' + (data.expires_at || '5 мин');
            startQPayPolling(data.invoice_id);
            updateCustomerState('paying', { qr_image: data.qr_image });
        } else {
            document.getElementById('qrNoImage').textContent = '✕ ' + (data.error || 'QPay алдаа');
            if (ccBtn) ccBtn.disabled = false;
        }
    })
    .catch(function(err) {
        document.getElementById('qrNoImage').textContent = '✕ QPay холбогдох боломжгүй';
        if (ccBtn) ccBtn.disabled = false;
    });
}

function startQPayPolling(invoiceId) {
    if (qpayPollTimer) clearTimeout(qpayPollTimer);
    var isMock = invoiceId && invoiceId.indexOf('MOCK') === 0;
    var checkUrl = isMock ? '/api/qpay/mock-check/' + invoiceId : '/api/qpay/status/' + invoiceId;

    function poll() {
        qpayPollCount++;
        apiRequest(checkUrl, { timeout: 10000 })
            .then(function(data) {
                if (data.success) {
                    if (data.payment_status === 'paid') {
                        handleQPayPaid(invoiceId, data.paid_amount);
                        return;
                    }
                    var statusEl = document.getElementById('qrPaymentStatus');
                    var elapsed = qpayPollCount * 3;
                    var dots = '.'.repeat((qpayPollCount % 3) + 1);
                    if (elapsed > 60) {
                        statusEl.textContent = '⏳ ' + Math.floor(elapsed / 60) + ' мин хүлээлээ' + dots;
                    } else {
                        statusEl.textContent = '📱 QR уншуулж байна' + dots;
                    }
                }
                var delay = qpayPollCount > 40 ? 5000 : 3000;
                qpayPollTimer = setTimeout(poll, delay);
            })
            .catch(function(err) {
                var statusEl = document.getElementById('qrPaymentStatus');
                if (statusEl) {
                    statusEl.textContent = '✕ Холболтын алдаа. Дахин оролдож байна...';
                    statusEl.className = 'qr-status-error';
                }
                if (qpayPollCount > 10) {
                    var confirmBtn_ = document.getElementById('confirmCheckout');
                    if (confirmBtn_) confirmBtn_.disabled = false;
                    if (statusEl) {
                        statusEl.textContent = '✕ QPay холбогдох боломжгүй. Дахин оролдоно уу.';
                    }
                    return;
                }
                qpayPollTimer = setTimeout(poll, 5000);
            });
    }
    qpayPollTimer = setTimeout(poll, 3000);
}

function stopQPayPolling() {
    if (qpayPollTimer) {
        clearTimeout(qpayPollTimer);
        qpayPollTimer = null;
    }
}

function handleQPayPaid(invoiceId, paidAmount) {
    stopQPayPolling();
    var total = getCartTotal();
    var statusEl = document.getElementById('qrPaymentStatus');
    statusEl.textContent = '✅ Төлбөр баталгаажлаа! ' + formatCurrency(paidAmount || total);
    statusEl.className = 'qr-status-paid';
    var confirmBtn_ = document.getElementById('confirmCheckout');
    if (confirmBtn_) confirmBtn_.disabled = false;
    // Auto-confirm after short delay
    setTimeout(function() {
        confirmSale();
    }, 500);
}

function closeCheckout() {
    stopQPayPolling();
    var modal = document.getElementById('checkoutModal');
    modal.classList.remove('active');
    updateCustomerState(cart.length > 0 ? 'shopping' : 'idle');
    refocusBarcode();
}

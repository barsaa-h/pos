/**
 * pos.js — Main POS screen JavaScript.
 */

if (typeof CATEGORY_ICONS === 'undefined') {
    var CATEGORY_ICONS = {
        'Сүүн бүтээгдэхүүн': '🥛', 'Талх нарийн боов': '🍞', 'Өндөг': '🥚',
        'Будаа': '🍚', 'Гоймон': '🍜', 'Тос': '🛢️', 'Чихэр': '🍬',
        'Давс амтлагч': '🧂', 'Жимс': '🍎', 'Ус ундаа': '🥤', 'Бусад': '📦'
    };
}

if (typeof CATEGORY_COLORS === 'undefined') {
    var CATEGORY_COLORS = {
        'Сүүн бүтээгдэхүүн': '#3B82F6', 'Талх нарийн боов': '#F59E0B', 'Өндөг': '#EAB308',
        'Будаа': '#22C55E', 'Гоймон': '#EF4444', 'Тос': '#A855F7', 'Чихэр': '#06B6D4',
        'Давс амтлагч': '#78716C', 'Жимс': '#84CC16', 'Ус ундаа': '#0EA5E9', 'Бусад': '#6B7280'
    };
}

function getCategoryIcon(category) { return CATEGORY_ICONS[category] || CATEGORY_ICONS['Бусад']; }
function getCategoryColor(category) { return CATEGORY_COLORS[category] || CATEGORY_COLORS['Бусад']; }

let cart = [];
let currentPaymentType = 'cash';
let lastSaleId = null;
let lastCustomerStateTime = 0;
let customerStateRetryTimer = null;

function formatCurrency(amount) {
    return Number(amount).toLocaleString('mn-MN') + ' ₮';
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
        items: cart.map(function(item) {
            return {
                name: item.product_name, quantity: item.quantity,
                unit_price: item.unit_price, subtotal: item.subtotal,
                category: item.category || 'Бусад', unit: item.unit || 'ш',
                image_url: item.image_url || ''
            };
        }),
        total: getCartTotal(),
        payment_type: currentPaymentType,
        cash_given: extra.cash_given || 0,
        change_given: extra.change_given || 0,
        card_amount: extra.card_amount || 0,
        lottery: extra.lottery || ''
    };
    _sendCustomerState(state);
}

function _sendCustomerState(state, retries) {
    retries = retries || 0;
    fetch('/api/customer-state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(state)
    }).then(function(r) {
        if (!r.ok && retries < 2) {
            setTimeout(function() { _sendCustomerState(state, retries + 1); }, 300);
        }
    }).catch(function() {
        if (retries < 2) {
            setTimeout(function() { _sendCustomerState(state, retries + 1); }, 300);
        }
    });
}

/* ─── CART OPERATIONS ─── */

function addToCart(product, qtyOverride) {
    var qty = qtyOverride || 1;
    let existing = null;
    for (let i = 0; i < cart.length; i++) {
        if (cart[i].product_id === product.id) { existing = cart[i]; break; }
    }

    if (existing) {
        if (existing.quantity + qty > product.stock_qty) {
            showNotification('Нөөц хүрэлцэхгүй байна: ' + product.name, 'warning');
            return;
        }
        existing.quantity += qty;
        existing.subtotal = existing.quantity * existing.unit_price;
    } else {
        if (product.stock_qty < qty) {
            showNotification('Нөөц хүрэлцэхгүй байна: ' + product.name, 'error');
            return;
        }
        cart.push({
            product_id: product.id,
            product_name: product.name,
            barcode: product.barcode,
            quantity: qty,
            unit_price: product.price,
            subtotal: product.price * qty,
            unit: product.unit || 'ш',
            stock_qty: product.stock_qty,
            category: product.category || 'Бусад',
            image_url: product.image_url || ''
        });
    }

    updateCustomerState(cart.length > 0 ? 'shopping' : 'idle');
    renderCart();
    animateCartCount();
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
        showQuantityPrompt(product, card);
    } else {
        addToCart(product, 1);
        animateCardAdd(card);
    }
}

function showQuantityPrompt(product, card) {
    var existing = document.querySelector('.quantity-prompt-overlay');
    if (existing) existing.remove();

    var overlay = document.createElement('div');
    overlay.className = 'quantity-prompt-overlay';
    overlay.style.cssText = 'position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.5); z-index:550; display:flex; align-items:center; justify-content:center;';

    var rect = card.getBoundingClientRect();
    var box = document.createElement('div');
    box.style.cssText = 'background:var(--surface); border-radius:16px; padding:24px; min-width:280px; box-shadow:0 20px 40px rgba(0,0,0,0.3); animation:modalIn 0.2s cubic-bezier(0.34,1.56,0.64,1); position:fixed; top:' + Math.min(rect.top, window.innerHeight-280) + 'px; left:' + Math.max(10, rect.left - 40) + 'px;';

    var unitLabel = product.unit === 'кг' ? 'кг' : (product.unit === 'л' ? 'л' : product.unit);
    box.innerHTML =
        '<div style="font-weight:800; font-size:1.1rem; margin-bottom:4px; color:var(--text);">' + escapeHtml(product.name) + '</div>' +
        '<div style="color:var(--text-muted); font-size:0.85rem; margin-bottom:14px;">' + formatCurrency(product.price) + '/' + unitLabel + '</div>' +
        '<div style="display:flex; gap:6px; margin-bottom:10px; flex-wrap:wrap;">' +
            '<button class="qty-preset" onclick="addToCartFromPrompt(' + JSON.stringify(product).replace(/"/g, '&quot;') + ', 0.5); closeQuantityPrompt();" style="padding:8px 14px; border:2px solid var(--border); border-radius:8px; background:var(--surface); font-weight:700; cursor:pointer;">0.5</button>' +
            '<button class="qty-preset" onclick="addToCartFromPrompt(' + JSON.stringify(product).replace(/"/g, '&quot;') + ', 1); closeQuantityPrompt();" style="padding:8px 14px; border:2px solid var(--border); border-radius:8px; background:var(--surface); font-weight:700; cursor:pointer;">1</button>' +
            '<button class="qty-preset" onclick="addToCartFromPrompt(' + JSON.stringify(product).replace(/"/g, '&quot;') + ', 2); closeQuantityPrompt();" style="padding:8px 14px; border:2px solid var(--border); border-radius:8px; background:var(--surface); font-weight:700; cursor:pointer;">2</button>' +
            '<button class="qty-preset" onclick="addToCartFromPrompt(' + JSON.stringify(product).replace(/"/g, '&quot;') + ', 5); closeQuantityPrompt();" style="padding:8px 14px; border:2px solid var(--border); border-radius:8px; background:var(--surface); font-weight:700; cursor:pointer;">5</button>' +
        '</div>' +
        '<div style="display:flex; gap:8px; align-items:center;">' +
            '<input type="number" id="qtyPromptInput" value="1" min="0.01" step="0.01" style="flex:1; padding:10px; border:2px solid var(--primary); border-radius:8px; font-size:1.1rem; font-weight:700; text-align:center; background:var(--surface); color:var(--text);" autofocus>' +
            '<span style="font-weight:700; color:var(--text-secondary);">' + unitLabel + '</span>' +
        '</div>' +
        '<div style="display:flex; gap:8px; margin-top:12px;">' +
            '<button class="btn btn-secondary btn-sm" style="flex:1;" onclick="closeQuantityPrompt()">Цуцлах</button>' +
            '<button class="btn btn-primary btn-sm" style="flex:1;" onclick="var v=parseFloat(document.getElementById(\'qtyPromptInput\').value)||1; addToCartFromPrompt(' + JSON.stringify(product).replace(/"/g, '&quot;') + ', v); closeQuantityPrompt();">+ Нэмэх</button>' +
        '</div>';

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) closeQuantityPrompt();
    });

    var input = document.getElementById('qtyPromptInput');
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            var v = parseFloat(input.value) || 1;
            addToCartFromPrompt(product, v);
            closeQuantityPrompt();
        }
        if (e.key === 'Escape') { closeQuantityPrompt(); }
    });
    setTimeout(function() { input.focus(); input.select(); }, 50);
}

function closeQuantityPrompt() {
    var el = document.querySelector('.quantity-prompt-overlay');
    if (el) el.remove();
    refocusBarcode();
}

function addToCartFromPrompt(product, qty) {
    if (isNaN(qty) || qty <= 0) qty = 1;
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
    toast.style.cssText = 'position:fixed; bottom:100px; right:20px; background:#1E293B; color:#fff; padding:12px 20px; border-radius:12px; font-weight:600; z-index:700; box-shadow:0 10px 25px rgba(0,0,0,0.2); display:flex; align-items:center; gap:10px; animation:flashIn 0.3s cubic-bezier(0.34,1.56,0.64,1);';
    toast.innerHTML = escapeHtml(item.product_name) + ' хасагдлаа <button onclick="undoRemoveCart(' + JSON.stringify(item) + '); this.parentElement.remove();" style="background:var(--primary); color:#fff; border:none; padding:6px 12px; border-radius:8px; font-weight:700; cursor:pointer; margin-left:6px;">↩ Буцаах</button>';
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
    if (newQty > item.stock_qty) {
        showNotification('Нөөц хүрэлцэхгүй байна', 'warning');
        return;
    }

    item.quantity = newQty;
    item.subtotal = newQty * item.unit_price;
    renderCart();
}

function clearCart() {
    if (cart.length === 0) return;
    if (confirm('Сагсыг цэвэрлэх үү?')) {
        cart = [];
        renderCart();
    }
}

function getCartTotal() {
    let total = 0;
    for (let i = 0; i < cart.length; i++) { total += cart[i].subtotal; }
    return total;
}

function renderCart() {
    const itemsEl = document.getElementById('cartItems');
    const emptyEl = document.getElementById('cartEmpty');
    const totalsEl = document.getElementById('cartTotals');
    const countEl = document.getElementById('cartCount');

    countEl.textContent = cart.length;

    if (cart.length === 0) {
        itemsEl.innerHTML = '';
        itemsEl.appendChild(emptyEl);
        emptyEl.style.display = 'block';
        totalsEl.style.display = 'none';
        disableCheckoutButtons();
        return;
    }

    emptyEl.style.display = 'none';
    totalsEl.style.display = 'block';

    let html = '';
    for (let i = 0; i < cart.length; i++) {
        const item = cart[i];
        const icon = getCategoryIcon(item.category);
        const color = getCategoryColor(item.category);
        const nearStock = item.quantity >= item.stock_qty;
        const stockWarning = nearStock ? ' <span style="color:var(--warning); font-size:0.75rem; font-weight:700;">(Макс)</span>' : '';

        html += '<div class="cart-item">';
        html += '  <div class="cart-item-icon" style="background:' + color + '15; color:' + color + ';">' + escapeHtml(icon) + '</div>';
        html += '  <div class="cart-item-info">';
        html += '    <div class="cart-item-name">' + escapeHtml(item.product_name) + stockWarning + '</div>';
        html += '    <div class="cart-item-detail">';
        html += '      <div class="cart-item-qty">';
        html += '        <button class="qty-btn" onclick="updateQuantity(' + i + ', -1)">−</button>';
        html += '        <span class="qty-value">' + item.quantity + '</span>';
        html += '        <button class="qty-btn" onclick="updateQuantity(' + i + ', 1)">+</button>';
        html += '        <span class="text-muted" style="margin-left:4px;">× ' + formatCurrency(item.unit_price) + '/' + escapeHtml(item.unit) + '</span>';
        html += '      </div>';
        html += '    </div>';
        html += '  </div>';
        html += '  <div class="cart-item-subtotal">' + formatCurrency(item.subtotal) + '</div>';
        html += '  <button class="cart-item-remove" onclick="removeFromCart(' + i + ')">✕</button>';
        html += '</div>';
    }
    itemsEl.innerHTML = html;

    const total = getCartTotal();
    const vat = calculateVAT(total);
    document.getElementById('subtotalDisplay').textContent = formatCurrency(total);
    document.getElementById('vatDisplay').textContent = formatCurrency(vat);
    document.getElementById('totalDisplay').textContent = formatCurrency(total);

    enableCheckoutButtons();
}

function enableCheckoutButtons() {
    document.getElementById('btnCash').disabled = false;
    document.getElementById('btnCard').disabled = false;
    document.getElementById('btnSplit').disabled = false;
    document.getElementById('btnQr').disabled = false;
    document.getElementById('btnHold').disabled = false;
}

function disableCheckoutButtons() {
    document.getElementById('btnCash').disabled = true;
    document.getElementById('btnCard').disabled = true;
    document.getElementById('btnSplit').disabled = true;
    document.getElementById('btnQr').disabled = true;
    document.getElementById('btnHold').disabled = true;
}

/* ─── BARCODE SCANNER ─── */

const barcodeInput = document.getElementById('barcodeInput');

barcodeInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        const barcode = this.value.trim();
        if (barcode.length > 0) {
            lookupBarcode(barcode);
            this.value = '';
        }
    }
});

function refocusBarcode() {
    setTimeout(function() {
        const el = document.getElementById('barcodeInput');
        if (el && !isModalOpen()) { el.focus(); }
    }, 50);
}

function lookupBarcode(barcode) {
    fetch('/api/barcode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ barcode: barcode })
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (data.success && data.product) {
            playBeep();
            var product = data.product;
            if (needsQuantityPrompt(product.unit || 'ш')) {
                var card = { classList: { contains: function() { return false; } } };
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
            var cards = document.querySelectorAll('.product-card');
            cards.forEach(function(card) {
                if (card.dataset.barcode === barcode) { animateCardAdd(card); }
            });
        } else if (data.error === 'not_found') {
            openNotFoundModal(data.barcode);
        } else {
            showNotification(data.error || 'Алдаа гарлаа', 'error');
        }
        refocusBarcode();
    })
    .catch(function() {
        showNotification('Сүлжээний алдаа', 'error');
        refocusBarcode();
    });
}

/* ─── SEARCH & FILTER ─── */

let currentCategory = '';
let searchDebounceTimer = null;

function filterProducts() {
    const query = document.getElementById('searchInput').value.toLowerCase();
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

/* ─── CHECKOUT ─── */

function openCheckout(paymentType) {
    if (cart.length === 0) return;
    currentPaymentType = paymentType;
    const total = getCartTotal();

    document.getElementById('checkoutTotal').textContent = formatCurrency(total);
    document.getElementById('checkoutModal').classList.add('active');
    updateCustomerState('paying');

    document.getElementById('cashSection').style.display = paymentType === 'cash' ? 'block' : 'none';
    document.getElementById('cardSection').style.display = paymentType === 'card' ? 'block' : 'none';
    document.getElementById('splitSection').style.display = paymentType === 'split' ? 'block' : 'none';
    document.getElementById('qrSection').style.display = paymentType === 'qr' ? 'block' : 'none';

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
        // Load QR image from settings if available
        var qrImg = document.getElementById('qrCodeImage');
        var qrUrl = (typeof QR_PAYMENT_IMAGE !== 'undefined' ? QR_PAYMENT_IMAGE : '');
        if (qrUrl) {
            qrImg.src = qrUrl;
            qrImg.style.display = 'block';
            document.getElementById('qrNoImage').style.display = 'none';
        } else {
            qrImg.style.display = 'none';
            document.getElementById('qrNoImage').style.display = 'block';
        }
    } else if (paymentType === 'split') {
        document.getElementById('splitCardAmount').value = '';
        document.getElementById('splitCashAmount').value = '';
        document.getElementById('splitCardInstruction').style.display = 'none';
        updateSplitRemaining();
    }
}

function closeCheckout() {
    document.getElementById('checkoutModal').classList.remove('active');
    updateCustomerState(cart.length > 0 ? 'shopping' : 'idle');
    refocusBarcode();
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

function calculateSplit() {
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
        cardAmount = total;
    } else if (currentPaymentType === 'qr') {
        cardAmount = total;
    } else if (currentPaymentType === 'split') {
        cardAmount = parseInt(document.getElementById('splitCardAmount').value) || 0;
        cashAmount = parseInt(document.getElementById('splitCashAmount').value) || 0;
        if (cardAmount + cashAmount < total) {
            showNotification('Нийт дүн хүрэлцэхгүй байна!', 'error');
            return;
        }
    }

    const items = cart.map(function(item) {
        return {
            product_id: item.product_id, product_name: item.product_name,
            barcode: item.barcode, quantity: item.quantity, unit_price: item.unit_price
        };
    });

    var idempotencyKey = 'sale_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

    var confirmBtn = document.getElementById('confirmCheckout');
    confirmBtn.disabled = true;
    confirmBtn.textContent = '⏳ Хийгдэж байна...';
    document.getElementById('loadingOverlay').classList.add('active');

    fetch('/api/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            items: items, payment_type: currentPaymentType,
            cash_given: cashGiven, card_amount: cardAmount, cash_amount: cashAmount,
            idempotency_key: idempotencyKey
        })
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        document.getElementById('loadingOverlay').classList.remove('active');
        confirmBtn.disabled = false;
        confirmBtn.textContent = '✓ Баталгаажуулах';

        if (data.success) {
            closeCheckout();
            lastSaleId = data.sale.id;
            showSaleComplete(data.sale);
            cart = [];
            renderCart();
            refreshProductGrid();
        } else {
            showNotification(data.error || 'Борлуулалт амжилтгүй', 'error');
        }
        refocusBarcode();
    })
    .catch(function() {
        document.getElementById('loadingOverlay').classList.remove('active');
        confirmBtn.disabled = false;
        confirmBtn.textContent = '✓ Баталгаажуулах';
        showNotification('Сүлжээний алдаа. Дахин оролдоно уу.', 'error');
        refocusBarcode();
    });
}

function refreshProductGrid() {
    fetch('/api/products/search?q=')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.products) return;
            const grid = document.getElementById('productGrid');
            const cards = grid.querySelectorAll('.product-card');
            cards.forEach(function(card) {
                const id = parseInt(card.dataset.id);
                let product = null;
                for (let i = 0; i < data.products.length; i++) {
                    if (data.products[i].id === id) { product = data.products[i]; break; }
                }
                if (product) {
                    card.dataset.stock = product.stock_qty;
                    const stockEl = card.querySelector('.card-stock');
                    if (stockEl) {
                        let html = product.stock_qty + ' ' + (product.unit || 'ш');
                        if (product.stock_qty === 0) {
                            html += '<br><span class="low-stock-badge out-of-stock">✕ Дууссан</span>';
                            card.classList.add('product-card-disabled');
                            card.removeAttribute('onclick');
                        } else {
                            card.classList.remove('product-card-disabled');
                            card.setAttribute('onclick', 'addToCartFromGrid(this)');
                        }
                        stockEl.innerHTML = html;
                    }
                    const barFill = card.querySelector('.stock-bar-fill');
                    if (barFill && data.max_stock && data.max_stock > 0) {
                        const pct = Math.round(product.stock_qty / data.max_stock * 100);
                        barFill.style.width = pct + '%';
                    }
                }
            });
        })
        .catch(function() {});
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
        card_amount: sale.card_amount || 0
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
    fetch('/api/reprint/' + lastSaleId, { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success) {
                document.getElementById('printErrorMessage').style.display = 'none';
                showNotification('Баримт хэвлэгдлээ!', 'success');
            } else {
                document.getElementById('printErrorMessage').style.display = 'block';
            }
        })
        .catch(function() { showNotification('Сүлжээний алдаа', 'error'); });
}

/* ─── BARCODE NOT FOUND ─── */

function openNotFoundModal(barcode) {
    document.getElementById('notFoundBarcode').textContent = barcode;
    document.getElementById('newProductBarcode').value = barcode;
    document.getElementById('newProductName').value = '';
    document.getElementById('newProductPrice').value = '';
    document.getElementById('newProductStock').value = '10';
    document.getElementById('newProductCategory').value = 'Бусад';
    document.getElementById('notFoundModal').classList.add('active');
    setTimeout(function() { document.getElementById('newProductName').focus(); }, 100);
}

function closeNotFound() {
    document.getElementById('notFoundModal').classList.remove('active');
    refocusBarcode();
}

function createProductFromNotFound() {
    const barcode = document.getElementById('newProductBarcode').value;
    const name = document.getElementById('newProductName').value.trim();
    const price = parseInt(document.getElementById('newProductPrice').value) || 0;
    const stock = parseInt(document.getElementById('newProductStock').value) || 0;
    const category = document.getElementById('newProductCategory').value.trim() || 'Бусад';
    const unit = document.getElementById('newProductUnit').value;

    if (!name) { showNotification('Барааны нэр оруулна уу', 'error'); return; }
    if (price <= 0) { showNotification('Үнэ 0-ээс их байх ёстой', 'error'); return; }

    fetch('/api/product/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ barcode: barcode, name: name, price: price, stock_qty: stock, category: category, unit: unit })
    })
    .then(function(response) { return response.json(); })
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
    .catch(function() { showNotification('Сүлжээний алдаа', 'error'); });
}

function addProductToGrid(product) {
    const grid = document.getElementById('productGrid');
    if (!grid) return;
    const icon = getCategoryIcon(product.category || 'Бусад');
    const color = getCategoryColor(product.category || 'Бусад');
    const maxStock = parseInt(grid.dataset.maxStock) || 1;
    const stockPercent = maxStock > 0 ? Math.round(product.stock_qty / maxStock * 100) : 0;

    const card = document.createElement('div');
    card.className = 'product-card';
    card.dataset.id = product.id;
    card.dataset.barcode = product.barcode;
    card.dataset.name = product.name;
    card.dataset.price = product.price;
    card.dataset.stock = product.stock_qty;
    card.dataset.unit = product.unit || 'ш';
    card.dataset.category = product.category || 'Бусад';
    card.setAttribute('onclick', 'addToCartFromGrid(this)');
    card.style.setProperty('--cat-color', color);

    if (product.image_url) {
        card.innerHTML = '<img src="' + escapeHtml(product.image_url) + '" alt="' + escapeHtml(product.name) + '" style="width:3.2rem; height:3.2rem; object-fit:cover; border-radius:8px; display:block; margin:0 auto 10px;">' +
            '<div class="card-name">' + escapeHtml(product.name) + '</div>' +
            '<div class="card-price">' + formatCurrency(product.price) + '</div>' +
            '<div class="card-stock">' + (product.stock_qty || 0) + ' ' + escapeHtml(product.unit || 'ш') + '</div>' +
            '<div class="stock-bar"><div class="stock-bar-fill" style="width:' + stockPercent + '%;background:' + color + ';"></div></div>';
    } else {
        card.innerHTML = '<div class="card-icon">' + escapeHtml(icon) + '</div>' +
            '<div class="card-name">' + escapeHtml(product.name) + '</div>' +
            '<div class="card-price">' + formatCurrency(product.price) + '</div>' +
            '<div class="card-stock">' + (product.stock_qty || 0) + ' ' + escapeHtml(product.unit || 'ш') + '</div>' +
            '<div class="stock-bar"><div class="stock-bar-fill" style="width:' + stockPercent + '%;background:' + color + ';"></div></div>';
    }

    grid.prepend(card);
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

document.addEventListener('keydown', function(e) {
    var targetTag = (e.target.tagName || '').toLowerCase();
    var isInput = (targetTag === 'input' || targetTag === 'textarea' || targetTag === 'select');
    if (e.key === 'F1') { e.preventDefault(); toggleHelp(); }
    if (e.key === 'F2') { e.preventDefault(); if (cart.length > 0) openCheckout('cash'); }
    if (e.key === 'F4') { e.preventDefault(); if (cart.length > 0) openCheckout('card'); }
    if (e.key === 'F5') { e.preventDefault(); if (cart.length > 0) openCheckout('qr'); }
    if (e.key === 'F3') { e.preventDefault(); if (cart.length > 0) holdOrder(); }
    if (e.key === 'Escape') {
        if (isModalOpen()) { closeAllModals(); }
        else if (cart.length > 0) { clearCart(); }
    }
    if (e.key === 'F5') { e.preventDefault(); }
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
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
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
    flash.innerHTML = message + '<button class="flash-close" onclick="this.parentElement.remove()">&times;</button>';
    container.appendChild(flash);
    setTimeout(function() {
        flash.style.opacity = '0';
        flash.style.transform = 'translateX(100%)';
        setTimeout(function() { flash.remove(); }, 500);
    }, 3000);
}

/* ─── HELD ORDERS (Suspend / Recall) ─── */

function holdOrder() {
    if (cart.length === 0) return;
    const label = 'Захиалга #' + new Date().toLocaleTimeString('mn-MN', {hour: '2-digit', minute: '2-digit'});
    fetch('/api/hold-order', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            label: label,
            items: cart.map(function(item) {
                return {
                    product_id: item.product_id,
                    product_name: item.product_name,
                    barcode: item.barcode,
                    quantity: item.quantity,
                    unit_price: item.unit_price,
                    subtotal: item.subtotal,
                    unit: item.unit,
                    category: item.category || 'Бусад'
                };
            }),
            total: getCartTotal()
        })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            showNotification('Захиалга хүлээлгэлээ', 'success');
            cart = [];
            renderCart();
            updateCustomerState('idle');
            loadHeldOrdersCount();
            refocusBarcode();
        } else {
            showNotification(data.error || 'Алдаа гарлаа', 'error');
        }
    })
    .catch(function() { showNotification('Сүлжээний алдаа', 'error'); });
}

function showHeldOrders() {
    fetch('/api/held-orders')
        .then(function(r) { return r.json(); })
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
        .catch(function() { showNotification('Сүлжээний алдаа', 'error'); });
}

function closeHeldOrders() {
    document.getElementById('heldOrdersModal').classList.remove('active');
    refocusBarcode();
}

function recallOrder(orderId) {
    fetch('/api/recall-order/' + orderId, { method: 'POST' })
        .then(function(r) { return r.json(); })
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
        .catch(function() { showNotification('Сүлжээний алдаа', 'error'); });
}

function deleteHeldOrder(orderId) {
    if (!confirm('Энэ захиалгыг устгах уу?')) return;
    fetch('/api/delete-held-order/' + orderId, { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success) {
                showHeldOrders();
                loadHeldOrdersCount();
            } else {
                showNotification(data.error || 'Устгахэд алдаа', 'error');
            }
        })
        .catch(function() { showNotification('Сүлжээний алдаа', 'error'); });
}

function loadHeldOrdersCount() {
    fetch('/api/held-orders')
        .then(function(r) { return r.json(); })
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

window.addEventListener('load', function() { refocusBarcode(); loadHeldOrdersCount(); });

/**
 * customer.js — Customer-facing display with SSE + polling fallback.
 */
(function() {
    var lastStateJSON = '';
    var idleTimeoutSeconds = (typeof IDLE_TIMEOUT_SECONDS !== 'undefined' ? IDLE_TIMEOUT_SECONDS : 10);
    var idleMessage = (typeof IDLE_MESSAGE !== 'undefined' ? IDLE_MESSAGE : 'Тавтай морилно уу');
    var idleTimer = null;
    var sseRetries = 0;
    var eventSource = null;

    var CATEGORY_ICONS = {
        'Сүүн бүтээгдэхүүн': '🥛', 'Талх нарийн боов': '🍞', 'Өндөг': '🥚',
        'Будаа': '🍚', 'Гоймон': '🍜', 'Тос': '🛢️', 'Чихэр': '🍬',
        'Давс амтлагч': '🧂', 'Жимс': '🍎', 'Ус ундаа': '🥤', 'Бусад': '📦'
    };

    function getCategoryIcon(cat) { return CATEGORY_ICONS[cat] || CATEGORY_ICONS['Бусад']; }
    function formatCurrency(n) { return Number(n).toLocaleString('mn-MN') + ' ₮'; }
    function escapeHtml(t) { var d = document.createElement('div'); d.appendChild(document.createTextNode(t)); return d.innerHTML; }

    function updateClock() {
        var el = document.getElementById('customerClock');
        if (el) { el.textContent = new Date().toLocaleTimeString('mn-MN', { hour: '2-digit', minute: '2-digit', hour12: false }); }
    }
    setInterval(updateClock, 1000);
    updateClock();

    function handleState(state) {
        var s = JSON.stringify(state);
        if (s !== lastStateJSON) { lastStateJSON = s; renderState(state); }
    }

    function resetIdleTimer() {
        if (idleTimer) clearTimeout(idleTimer);
        idleTimer = setTimeout(function() {
            fetch('/api/customer-state', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phase: 'idle', items: [], total: 0 })
            }).catch(function() {});
        }, idleTimeoutSeconds * 1000);
    }

    function renderState(state) {
        var views = document.querySelectorAll('.view');
        for (var i = 0; i < views.length; i++) views[i].classList.remove('active');
        var phase = state.phase || 'idle';
        var items = state.items || [];
        var total = state.total || 0;

        if (phase === 'idle' || items.length === 0) {
            var h1 = document.querySelector('#idleView h1');
            if (h1) h1.textContent = idleMessage;
            document.getElementById('idleView').classList.add('active');
        } else if (phase === 'shopping') {
            renderShopping(items, total);
            document.getElementById('shoppingView').classList.add('active');
            resetIdleTimer();
        } else if (phase === 'paying') {
            var icon = document.getElementById('payingIcon');
            var pt = state.payment_type || '';
            if (icon) {
                if (pt === 'qr') icon.textContent = '📱';
                else if (pt === 'card') icon.textContent = '💳';
                else icon.textContent = '💵';
            }
            document.getElementById('payingTotal').textContent = formatCurrency(total);
            document.getElementById('payingView').classList.add('active');
        } else if (phase === 'complete') {
            var change = state.change_given || 0;
            var cardAmount = state.card_amount || 0;
            var pt = state.payment_type || '';
            var changeInfo = document.getElementById('changeInfo');
            var txt = '';
            if (pt === 'cash' && change > 0) {
                txt = '💵 БУЦААЛТ: <span style="color:#ffcc00;">' + formatCurrency(change) + '</span>';
            } else if (pt === 'card') {
                txt = '💳 КАРТААР ТӨЛЛӨӨ';
            } else if (pt === 'qr') {
                txt = '📱 QR ТӨЛБӨР АМЖИЛТТАЙ';
            } else if (pt === 'split' && cardAmount > 0) {
                txt = '💳 Карт: ' + formatCurrency(cardAmount) + ' &nbsp;💵 Бэлэн: ' + formatCurrency(total - cardAmount);
            } else {
                txt = '✅ ТӨЛБӨР АМЖИЛТТАЙ';
            }
            changeInfo.innerHTML = txt;

            var lottery = state.lottery || '';
            var lotteryEl = document.getElementById('lotteryInfo');
            if (lottery) { lotteryEl.innerHTML = '🎰 СУГАЛАА: ' + lottery; lotteryEl.style.display = 'block'; }
            else { lotteryEl.style.display = 'none'; }
            document.getElementById('completeView').classList.add('active');
            resetIdleTimer();
        }
    }

    function renderShopping(items, total) {
        var container = document.getElementById('itemList');
        var isCompact = items.length > 5;

        if (isCompact) {
            container.classList.add('compact');
        } else {
            container.classList.remove('compact');
        }

        var html = '';
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            var icon = getCategoryIcon(item.category);
            if (isCompact) {
                html += '<div class="item-card item-compact">';
                if (item.image_url) {
                    html += '<img src="' + escapeHtml(item.image_url) + '" class="item-img" alt="">';
                } else {
                    html += '<span class="item-icon-compact">' + icon + '</span>';
                }
                html += '<div class="item-info">';
                html += '<div class="item-name-compact">' + escapeHtml(item.name) + '</div>';
                html += '<div class="item-qty-compact">' + item.quantity + ' ' + escapeHtml(item.unit || 'ш') + ' × ' + formatCurrency(item.unit_price) + '</div>';
                html += '</div>';
                html += '<div class="item-price-compact">' + formatCurrency(item.subtotal) + '</div>';
                html += '</div>';
            } else {
                html += '<div class="item-card">';
                if (item.image_url) {
                    html += '<img src="' + escapeHtml(item.image_url) + '" class="item-img-full" alt="">';
                } else {
                    html += '<div class="item-icon">' + icon + '</div>';
                }
                html += '<div class="item-info">';
                html += '<div class="item-name">' + escapeHtml(item.name) + '</div>';
                html += '<div class="item-qty">' + item.quantity + ' ' + escapeHtml(item.unit || 'ш') + ' × ' + formatCurrency(item.unit_price) + '</div>';
                html += '</div>';
                html += '<div class="item-price">' + formatCurrency(item.subtotal) + '</div>';
                html += '</div>';
            }
        }
        container.innerHTML = html;
        document.getElementById('totalAmount').textContent = formatCurrency(total);
        var countBadge = document.getElementById('itemCountBadge');
        if (countBadge) countBadge.textContent = items.length + ' бараа';
    }

    // ── SSE with reconnect ──
    function connectSSE() {
        if (typeof EventSource === 'undefined') { startPolling(); return; }
        if (eventSource) { eventSource.close(); }
        eventSource = new EventSource('/api/customer-stream');
        eventSource.onmessage = function(e) {
            sseRetries = 0;
            try { handleState(JSON.parse(e.data)); } catch(ex) {}
        };
        eventSource.onerror = function() {
            eventSource.close();
            var delay = Math.min(1000 * Math.pow(2, sseRetries), 8000);
            sseRetries++;
            if (sseRetries >= 3) { startPolling(); }
            else { setTimeout(connectSSE, delay); }
        };
    }

    function startPolling() {
        if (pollInterval) return;
        pollOnce();
        pollInterval = setInterval(pollOnce, 500);
    }
    var pollInterval = null;
    function pollOnce() {
        fetch('/api/customer-state')
            .then(function(r) { return r.json(); })
            .then(function(s) { handleState(s); })
            .catch(function() {});
    }

    connectSSE();
})();
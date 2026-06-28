(function() {
    var lastStateJSON = '';
    var idleMessage = (typeof IDLE_MESSAGE !== 'undefined' ? IDLE_MESSAGE : 'Тавтай морилно уу');

    if (navigator.hardwareConcurrency <= 4) {
        document.documentElement.setAttribute('data-perf', 'low');
    }

    var CATEGORY_ICONS = {
        'Сүүн бүтээгдэхүүн': '🥛', 'Талх нарийн боов': '🍞', 'Өндөг': '🥚',
        'Будаа': '🍚', 'Гоймон': '🍜', 'Тос': '🛢️', 'Чихэр': '🍬',
        'Давс амтлагч': '🧂', 'Жимс': '🍎', 'Ус ундаа': '🥤', 'Бусад': '📦'
    };

    function getCategoryIcon(cat) { return CATEGORY_ICONS[cat] || CATEGORY_ICONS['Бусад']; }
    function formatCurrency(n) {
        var s = '' + (Math.abs(Number(n) || 0));
        var r = '';
        for (var i = s.length - 1, j = 0; i >= 0; i--, j++) {
            if (j > 0 && j % 3 === 0) r = ',' + r;
            r = s[i] + r;
        }
        return r + ' ₮';
    }
    function escapeHtml(t) { var d = document.createElement('div'); d.appendChild(document.createTextNode(t)); return d.innerHTML; }

    function updateClock() {
        var el = document.getElementById('customerClock');
        if (el) { el.textContent = new Date().toLocaleTimeString('mn-MN', { hour: '2-digit', minute: '2-digit', hour12: false }); }
    }
    updateClock();
    setInterval(updateClock, 1000);

    function handleState(state) {
        var s = JSON.stringify(state);
        if (s !== lastStateJSON) { lastStateJSON = s; renderState(state); }
    }

    function hideAllViews() {
        var views = document.querySelectorAll('.view');
        for (var i = 0; i < views.length; i++) views[i].classList.remove('active');
    }

    function renderState(state) {
        hideAllViews();

        var phase = state.phase || 'idle';
        var items = state.items || [];
        var total = state.total || 0;

        if (phase === 'idle') {
            var h1 = document.querySelector('#idleView h1');
            if (h1) h1.textContent = idleMessage;
            document.getElementById('idleView').classList.add('active');
            return;
        }

        switch (phase) {
            case 'shopping':
                renderShopping(items, total);
                document.getElementById('shoppingView').classList.add('active');
                break;

            case 'paying':
                if (state.payment_type === 'qr' && state.qr_image) {
                    document.getElementById('qrViewAmount').textContent = formatCurrency(total);
                    document.getElementById('qrViewImage').src = 'data:image/png;base64,' + state.qr_image;
                    document.getElementById('qrView').classList.add('active');
                } else {
                    var h1 = document.querySelector('#idleView h1');
                    if (h1) h1.textContent = 'Төлбөр хүлээж байна...';
                    document.getElementById('idleView').classList.add('active');
                }
                break;

            case 'complete':
                var h1 = document.querySelector('#idleView h1');
                if (h1) h1.textContent = idleMessage;
                document.getElementById('idleView').classList.add('active');
                break;
        }
    }

    function renderShopping(items, total) {
        var container = document.getElementById('itemList');
        var html = '';
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            var icon = getCategoryIcon(item.category);
            html += '<div class="item-card">';
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
        }
        container.innerHTML = html;
        var rowCount = Math.ceil(items.length / 2);
        if (rowCount > 0 && rowCount <= 12) {
            container.style.gridTemplateRows = 'repeat(' + rowCount + ', 1fr)';
        } else {
            container.style.gridTemplateRows = 'auto';
        }
        document.getElementById('totalAmount').textContent = formatCurrency(total);
        var badge = document.getElementById('itemCountBadge');
        if (badge) badge.textContent = items.length + ' бараа';
    }

    function poll() {
        fetch('/api/customer-state', { cache: 'no-store' })
            .then(function(r) { return r.json(); })
            .then(function(s) { handleState(s); })
            .catch(function() {});
    }

    poll();
    var pollInterval = (navigator.hardwareConcurrency <= 4) ? 2000 : 500;
    setInterval(poll, pollInterval);
})();

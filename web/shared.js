/* ===== Gailery shared JS — theme toggle + mobile nav + header ===== */

var _isLightTheme = false;

// Читаем сохранённую тему сразу, но не применяем до рендера шапки
var _savedTheme = localStorage.getItem('gallery-theme');
if (_savedTheme === 'light') {
    _isLightTheme = true;
}

var _NAV_ITEMS = [
    { href: '/gallery',  ico: '\u25A0', label: 'Галерея' },
    { href: '/albums',   ico: '\u25A0', label: 'Альбомы' },
    { href: '/catalog',  ico: '\u25B6', label: 'Каталог' },
    { href: '/map',      ico: '\u25C9', label: 'Карта' },
    { href: '/persons',  ico: '\u25C6', label: 'Персоны' },
    { href: '/admin',    ico: '\u2699', label: 'Управление' },
];

function _activeNavPath() {
    var p = window.location.pathname;
    for (var i = 0; i < _NAV_ITEMS.length; i++) {
        if (p === _NAV_ITEMS[i].href || p.indexOf(_NAV_ITEMS[i].href + '/') === 0) return _NAV_ITEMS[i].href;
    }
    if (p === '/' || p === '/gallery') return '/gallery';
    return null;
}

function renderHeader(pageTitle, headerInner) {
    var active = _activeNavPath();
    var navHtml = '';
    for (var i = 0; i < _NAV_ITEMS.length; i++) {
        var cls = _NAV_ITEMS[i].href === active ? ' class="active"' : '';
        navHtml += '<a href="' + _NAV_ITEMS[i].href + '"' + cls + '>' + _NAV_ITEMS[i].label + '</a>';
    }
    var mmNavHtml = '';
    for (var j = 0; j < _NAV_ITEMS.length; j++) {
        var mcls = _NAV_ITEMS[j].href === active ? ' class="mm-a active"' : ' class="mm-a"';
        mmNavHtml += '<a href="' + _NAV_ITEMS[j].href + '"' + mcls + '><span class="mm-ico">' + _NAV_ITEMS[j].ico + '</span><span class="mm-lbl">' + _NAV_ITEMS[j].label + '</span></a>';
    }
    var html = '<div class="header-sticky" id="headerSticky">' +
        '<h1>' +
        '<a href="/gallery" class="logo-link"><img class="logo" src="/logo-dark.png" data-light="/logo-light.png" data-dark="/logo-dark.png" alt="Gailery"></a><span>' + (pageTitle || '') + '</span>' +
        '<button class="hamburger" onclick="toggleMobileNav()" aria-label="Меню">&#9776;</button>' +
        '<div class="nav">' + navHtml + '</div>' +
        '<button class="theme-toggle" onclick="toggleTheme()" title="Дневная тема">\u2600\uFE0F</button>' +
        '</h1>' +
        (headerInner || '') +
        '</div>' +
        '<div class="mm-overlay" id="mmOverlay"></div>' +
        '<div class="mm-edge" id="mmEdge"></div>' +
        '<div class="mm-panel" id="mmPanel">' +
        '<div class="mm-head"><img src="/logo-dark.png" data-light="/logo-light.png" data-dark="/logo-dark.png" alt=""><span>Gailery</span><button class="mm-x" onclick="closeMobileNav()">&times;</button></div>' +
        '<div class="mm-nav">' + mmNavHtml + '</div>' +
        '<div class="mm-foot"><button class="mm-theme" onclick="toggleTheme();updateMmTheme()"><span class="mm-theme-ico" id="mmThemeIco">\u2600\uFE0F</span><span id="mmThemeLbl">Дневная тема</span></button></div>' +
        '</div>';
    document.write(html);
    // Применить тему после рендера — document.write пересоздаёт DOM
    if (_isLightTheme) {
        document.body.classList.add('light-theme');
    }
    updateThemeIcon();
}

function toggleTheme() {
    _isLightTheme = !_isLightTheme;
    document.body.classList.toggle('light-theme', _isLightTheme);
    localStorage.setItem('gallery-theme', _isLightTheme ? 'light' : 'dark');
    updateThemeIcon();
}

function updateThemeIcon() {
    var btn = document.querySelector('.header-sticky .theme-toggle');
    if (btn) {
        btn.innerHTML = _isLightTheme ? '🌙' : '☀️';
        btn.title = _isLightTheme ? 'Тёмная тема' : 'Дневная тема';
    }
    var logo = document.querySelector('.header-sticky h1 .logo');
    if (logo) {
        logo.src = _isLightTheme ? logo.dataset.light : logo.dataset.dark;
    }
}

function openMobileNav() {
    var p = document.getElementById('mmPanel');
    p.classList.remove('dragging');
    p.style.transform = '';
    p.classList.add('open');
    document.getElementById('mmOverlay').classList.add('open');
    var header = document.getElementById('headerSticky');
    if (header) {
        document.documentElement.classList.add('scroll-lock');
        header.style.transform = 'translateY(0)';
    } else {
        document.body.style.overflow = 'hidden';
    }
    updateMmTheme();
}

function closeMobileNav() {
    var p = document.getElementById('mmPanel');
    p.classList.remove('dragging');
    p.style.transform = '';
    p.classList.remove('open');
    document.getElementById('mmOverlay').classList.remove('open');
    var header = document.getElementById('headerSticky');
    if (header) {
        document.documentElement.classList.remove('scroll-lock');
        header.style.transform = 'translateY(0)';
    } else {
        document.body.style.overflow = '';
    }
}

function toggleMobileNav() {
    var p = document.getElementById('mmPanel');
    if (p.classList.contains('open')) closeMobileNav(); else openMobileNav();
}

function updateMmTheme() {
    var ico = document.getElementById('mmThemeIco');
    var lbl = document.getElementById('mmThemeLbl');
    if (ico) ico.innerHTML = _isLightTheme ? '🌙' : '☀️';
    if (lbl) lbl.textContent = _isLightTheme ? 'Тёмная тема' : 'Дневная тема';
    var mmLogo = document.querySelector('.mm-head img');
    if (mmLogo) mmLogo.src = _isLightTheme ? mmLogo.dataset.light : mmLogo.dataset.dark;
}

var _mmOverlay = document.getElementById('mmOverlay');
if (_mmOverlay) _mmOverlay.addEventListener('click', closeMobileNav);

(function() {
    var panel = document.getElementById('mmPanel');
    var edge = document.getElementById('mmEdge');
    var startX = 0, startY = 0, curX = 0, isEdgeSwipe = false, isPanelSwipe = false, panelOpen = false;
    var W = 280;

    function onOpen() { panelOpen = true; }
    function onClose() { panelOpen = false; }

    var origOpen = openMobileNav;
    openMobileNav = function() { origOpen(); onOpen(); };
    var origClose = closeMobileNav;
    closeMobileNav = function() { origClose(); onClose(); };

    document.addEventListener('touchstart', function(e) {
        var t = e.touches[0];
        startX = t.clientX;
        startY = t.clientY;
        curX = startX;
        isEdgeSwipe = false;
        isPanelSwipe = false;

        if (!panelOpen && startX >= window.innerWidth - 30) {
            isEdgeSwipe = true;
            panel.classList.add('dragging');
        }
        if (panelOpen && panel.contains(e.target)) {
            isPanelSwipe = true;
            panel.classList.add('dragging');
        }
    }, { passive: true });

    document.addEventListener('touchmove', function(e) {
        if (!isEdgeSwipe && !isPanelSwipe) return;
        var t = e.touches[0];
        curX = t.clientX;
        var dx = curX - startX;
        var dy = t.clientY - startY;
        if (Math.abs(dy) > Math.abs(dx) * 1.5) { isEdgeSwipe = false; isPanelSwipe = false; panel.classList.remove('dragging'); panel.style.transform = ''; return; }

        if (isEdgeSwipe) {
            var tx = Math.max(0, -dx);
            if (tx > 0) {
                panel.classList.add('open');
                document.getElementById('mmOverlay').classList.add('open');
                var pct = Math.min(1, tx / W);
                panel.style.transform = 'translateX(' + (100 - pct * 100) + '%)';
                document.getElementById('mmOverlay').style.opacity = pct * 0.5;
            }
        }
        if (isPanelSwipe) {
            let tx = Math.min(0, -dx);
            let pct = Math.min(1, Math.abs(tx) / W);
            panel.style.transform = 'translateX(' + (-pct * 100) + '%)';
            document.getElementById('mmOverlay').style.opacity = (1 - pct) * 0.5;
        }
    }, { passive: true });

    document.addEventListener('touchend', function(e) {
        if (!isEdgeSwipe && !isPanelSwipe) return;
        panel.classList.remove('dragging');
        panel.style.transform = '';
        var overlay = document.getElementById('mmOverlay');
        overlay.style.opacity = '';

        var dx = curX - startX;
        if (isEdgeSwipe) {
            if (dx < -60) { openMobileNav(); }
            else { panel.classList.remove('open'); overlay.classList.remove('open'); }
        }
        if (isPanelSwipe) {
            if (dx > 60) { closeMobileNav(); }
            else { panel.classList.add('open'); }
        }
        isEdgeSwipe = false;
        isPanelSwipe = false;
    }, { passive: true });
})();

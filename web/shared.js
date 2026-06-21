/* ===== Gailery shared JS — theme toggle + mobile nav ===== */

var _isLightTheme = false;

function toggleTheme() {
    _isLightTheme = !_isLightTheme;
    document.body.classList.toggle('light-theme', _isLightTheme);
    localStorage.setItem('gallery-theme', _isLightTheme ? 'light' : 'dark');
    updateThemeIcon();
}

function updateThemeIcon() {
    var btn = document.querySelector('.theme-toggle');
    if (btn) {
        btn.innerHTML = _isLightTheme ? '🌙' : '☀️';
        btn.title = _isLightTheme ? 'Тёмная тема' : 'Дневная тема';
    }
    var logo = document.querySelector('h1 .logo');
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

document.getElementById('mmOverlay').addEventListener('click', closeMobileNav);

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
            var tx = Math.min(0, -dx);
            var pct = Math.min(1, Math.abs(tx) / W);
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

var _savedTheme = localStorage.getItem('gallery-theme');
if (_savedTheme === 'light') {
    _isLightTheme = true;
    document.body.classList.add('light-theme');
    updateThemeIcon();
}

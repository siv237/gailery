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

/* ===== Modal zoom/pan/touch — shared across gallery, photos, catalog ===== */

function applyModalTransform() {
    var rot = (typeof _mRot !== 'undefined') ? 'rotate(' + _mRot + 'deg) ' : '';
    document.getElementById('modalImgWrap').style.transform = rot + 'translate(' + _mPx + 'px,' + _mPy + 'px) scale(' + _mZoom + ')';
    var boxes = document.querySelectorAll('.face-box');
    for (var i = 0; i < boxes.length; i++) {
        boxes[i].style.borderWidth = (2 / _mZoom) + 'px';
        var lbl = boxes[i].querySelector('.face-box-label');
        if (lbl) lbl.style.fontSize = (13 / _mZoom) + 'px';
    }
    if (typeof _positionModalControls === 'function') _positionModalControls();
}

function initModalZoom() {
    var modal = document.getElementById('photoModal');
    if (!modal || !document.getElementById('modalImgWrap')) return;

    modal.addEventListener('click', function(e) {
        if (e.target === this) closePhotoModal();
    });

    modal.addEventListener('wheel', function(e) {
        e.preventDefault();
        var rect = document.getElementById('modalImgWrap').getBoundingClientRect();
        var cx = e.clientX - rect.left - rect.width / 2 - _mPx;
        var cy = e.clientY - rect.top - rect.height / 2 - _mPy;
        var oldZ = _mZoom;
        var delta = e.deltaY > 0 ? 0.8 : 1.25;
        _mZoom = Math.max(1, Math.min(20, _mZoom * delta));
        var ratio = _mZoom / oldZ;
        _mPx -= cx * (ratio - 1);
        _mPy -= cy * (ratio - 1);
        if (_mZoom <= 1) { _mPx = 0; _mPy = 0; }
        applyModalTransform();
    });

    document.getElementById('modalImgWrap').addEventListener('mousedown', function(e) {
        if (_mZoom > 1) {
            e.preventDefault();
            _mDrag = true;
            _mDX = e.clientX - _mPx;
            _mDY = e.clientY - _mPy;
            e.currentTarget.style.cursor = 'grabbing';
        }
    });

    document.addEventListener('mousemove', function(e) {
        if (_mDrag) { _mPx = e.clientX - _mDX; _mPy = e.clientY - _mDY; applyModalTransform(); }
    });

    document.addEventListener('mouseup', function() {
        if (_mDrag) { _mDrag = false; document.getElementById('modalImgWrap').style.cursor = 'grab'; }
    });

    document.addEventListener('fullscreenchange', function() {
        if (!document.fullscreenElement) document.getElementById('photoModal').classList.remove('fs');
        if (typeof _positionModalControls === 'function') setTimeout(_positionModalControls, 100);
    });

    var sx = 0, sy = 0, st = 0;
    var pinchStartDist = 0, pinchStartZoom = 1;
    var panStartX = 0, panStartY = 0, isPanning = false;

    modal.addEventListener('touchstart', function(e) {
        if (e.touches.length === 2) {
            pinchStartDist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
            pinchStartZoom = _mZoom;
            return;
        }
        if (e.touches.length === 1) {
            sx = e.touches[0].clientX; sy = e.touches[0].clientY; st = Date.now();
            if (_mZoom > 1) {
                isPanning = true;
                panStartX = e.touches[0].clientX - _mPx;
                panStartY = e.touches[0].clientY - _mPy;
            }
        }
    }, { passive: true });

    modal.addEventListener('touchmove', function(e) {
        if (e.touches.length === 2 && pinchStartDist > 0) {
            var dist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
            var scale = dist / pinchStartDist;
            _mZoom = Math.max(1, Math.min(20, pinchStartZoom * scale));
            if (_mZoom <= 1) { _mPx = 0; _mPy = 0; }
            applyModalTransform();
            return;
        }
        if (isPanning && e.touches.length === 1) {
            _mPx = e.touches[0].clientX - panStartX;
            _mPy = e.touches[0].clientY - panStartY;
            applyModalTransform();
        }
    }, { passive: true });

    modal.addEventListener('touchend', function(e) {
        isPanning = false;
        pinchStartDist = 0;
        if (e.touches.length > 0) return;
        if (_mZoom > 1) return;
        var dx = e.changedTouches[0].clientX - sx;
        var dy = e.changedTouches[0].clientY - sy;
        var dt = Date.now() - st;
        if (dt < 500 && Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) {
            if (dx < 0) modalNav(1);
            else modalNav(-1);
        }
    }, { passive: true });
}

initModalZoom();

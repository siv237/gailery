/* ===== Gailery Viewer — независимый модальный просмотрщик фото/видео/FLIR =====
   Подключается на любой странице: gallery, map, и др.
   Инъектит свой HTML, управляет своим состоянием.

   API:
     Viewer.open(photos, idx)       — открыть по массиву фото (галерея)
     Viewer.openSingle(photoData)   — открыть одно фото (карта, standalone)
     Viewer.close()                 — закрыть

   Хуки (опционально, для интеграции с хост-страницей):
     ViewerHooks.onNavBoundary(dir, cb)  — ленивая загрузка (галерея)
     ViewerHooks.onDelete(photoId)       — удаление с обновом карточек
     ViewerHooks.onUndelete(photoId)     — восстановление
     ViewerHooks.onGoToGps(lat, lon)     — переход к GPS
     ViewerHooks.onClearGps(photoId)     — очистка GPS
     ViewerHooks.onAddGps(photoId)       — добавление GPS
     ViewerHooks.onFaceClick(pid, fid)   — клик по лицу
     ViewerHooks.onClose()               — после закрытия
     ViewerHooks.syncTimeline(photo)     — синхронизация timeline
     ViewerHooks.scrollCardIntoView(pid) — скролл к карточке
===== */

var Viewer = {
    photos: [],
    idx: 0,
    standalone: false,
    modalOpen: false,
};

var ViewerHooks = ViewerHooks || {};

// ─── State ───
var _mZoom = 1, _mPx = 0, _mPy = 0, _mDrag = false, _mDX = 0, _mDY = 0;
var _mDate = '', _mPhotoId = '', _mRot = 0, _mIdx = -1, _mCoverMode = false;
var _ssDir = 0, _ssTimer = null;
var _imgCache = {};
var _mFlirMode = null;
var _flirVisImg = new Image();
var _flirThImg = new Image();
var _flirOX = 219, _flirOY = 141, _flirScale = 1.5;
var _flirDrag = false, _flirDX = 0, _flirDY = 0, _flirStartX = 0, _flirStartY = 0;
var _flirScaleCorner = null, _flirProbes = [], _flirToken = 0;
var _topbarHideTimer = null;

// ─── HTML injection ───
var _viewerHTML = `
<div class="modal-bg" id="photoModal">
    <div class="modal-nav modal-prev" onclick="modalNav(-1)">&#8249;</div>
    <div class="modal-nav modal-next" onclick="modalNav(1)">&#8250;</div>
    <div class="modal-content" id="modalContent">
        <div class="modal-img-wrap" id="modalImgWrap" style="cursor:grab">
            <img id="photoModalImg" src="" onclick="event.stopPropagation()">
            <canvas id="photoModalCanvas" style="display:none;max-width:100%;max-height:100%;object-fit:contain" onclick="event.stopPropagation()"></canvas>
            <video id="photoModalVideo" src="" controls preload="metadata" onclick="event.stopPropagation()" style="display:none"></video>
            <div class="face-overlays" id="faceOverlays"></div>
        </div>
    </div>
    <div class="modal-btns" id="modalBtns">
        <div class="modal-rot modal-rot-l" onclick="rotatePhoto(-90)" title="Повернуть влево">&#8634;</div>
        <div class="modal-rot modal-rot-r" onclick="rotatePhoto(90)" title="Повернуть вправо">&#8635;</div>
        <div class="modal-fit" onclick="smartFit()" title="Растянуть"><div class="fit-icon" id="fitIcon"><i class="tl"></i><i class="tr"></i><i class="bl"></i><i class="br"></i></div></div>
        <div class="modal-fs" onclick="toggleFullscreen()">&#x26F6;</div>
        <div class="modal-close" onclick="closePhotoModal()">&times;</div>
    </div>
    <div class="modal-topbar" id="modalTopbar">
        <span id="modalDate"></span>
        <span class="sep">|</span>
        <span id="modalFlirBar" style="display:none">
            <button class="flir-mbtn active" onclick="setModalFlir('thermal')" title="Тепловизор">&#127777;</button>
            <button class="flir-mbtn" onclick="setModalFlir('visual')" title="Видимый свет">&#128247;</button>
            <button class="flir-mbtn" onclick="setModalFlir('overlay')" title="Наложение">&#128270;</button>
            <span class="sep" style="margin:0 2px">|</span>
            <span id="flirOverlayControls" style="display:none;font-size:11px;gap:6px;align-items:center">
                A <input type="range" id="flirA" min="0.1" max="0.9" step="0.05" value="0.50" style="width:50px;vertical-align:middle" oninput="drawFlirOverlay()">
                <span id="flirAv" style="color:#0f0;width:30px;display:inline-block;text-align:right">0.50</span>
            </span>
        </span>
        <button class="modal-del" id="modalDelBtn" onclick="markDeleted(_mIdx >= 0 ? Viewer.photos[_mIdx] && Viewer.photos[_mIdx].photo_id : '')" title="Удалить">&#128465;</button>
        <span class="sep">|</span>
        <span id="modalLoc"></span>
        <span class="sep">|</span>
        <button class="ss-dir" onclick="slideshowToggle(-1)" title="Автопрокрутка назад">&#9664;</button>
        <button class="ss-stop" onclick="slideshowStop()" title="Стоп">&#9632;</button>
        <button class="ss-dir" onclick="slideshowToggle(1)" title="Автопрокрутка вперёд">&#9654;</button>
    </div>
</div>
<div class="vid-modal-bg" id="vidModal">
    <div class="vid-modal-close" onclick="closeVideoModal()">×</div>
    <div class="vid-modal-bar" id="vidModalBar"></div>
    <video id="vidModalPlayer" src="" controls preload="metadata" onclick="event.stopPropagation()"></video>
</div>
`;

(function() {
    var div = document.createElement('div');
    div.innerHTML = _viewerHTML;
    while (div.firstChild) document.body.appendChild(div.firstChild);
})();

// ─── Helpers ───
function _vEsc(s) {
    if (typeof esc === 'function') return esc(s);
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function _vAPI() {
    return (typeof API !== 'undefined') ? API : '/api';
}

function _vVideoSrc(p) {
    if (typeof videoSrc === 'function') return videoSrc(p);
    if (p.media_type === 'video' && p.needs_stream)
        return _vAPI() + '/photos/video_stream?path=' + encodeURIComponent(p.photo_id);
    return p.photo_id ? (_vAPI() + '/photos/?path=' + encodeURIComponent(p.photo_id)) : '';
}

function _vIsMobile() {
    return window.innerWidth <= 768;
}

function formatDate(ds) {
    if (!ds) return '';
    var p = ds.substring(0, 19).replace('T', ' ');
    return p.replace(/^(\d{4})[:\-](\d{2})[:\-](\d{2})/, function(m, y, mo, d) { return d + '.' + mo + '.' + y; });
}

// ─── Public API ───
Viewer.open = function(photos, idx) {
    Viewer.photos = photos;
    Viewer.standalone = false;
    openViewer(idx);
};

Viewer.openSingle = function(photoData) {
    Viewer.photos = [photoData];
    Viewer.standalone = true;
    openViewer(0);
};

Viewer.close = function() {
    closePhotoModal();
};

// ─── Core: open/close ───
function openViewer(idx) {
    if (idx < 0 || idx >= Viewer.photos.length) return;
    Viewer.modalOpen = true;
    if (typeof closeDetail === 'function') closeDetail();
    _mIdx = idx;
    var p = Viewer.photos[idx];
    _mDate = p.date || '';
    _mPhotoId = p.photo_id || '';
    var url = _vVideoSrc(p);
    var img = document.getElementById('photoModalImg');
    var vid = document.getElementById('photoModalVideo');
    var wrap = document.getElementById('modalImgWrap');
    var isVideo = p.media_type === 'video';

    vid.onended = null;
    document.getElementById('photoModalCanvas').style.display = 'none';
    document.getElementById('flirOverlayControls').style.display = 'none';
    _mFlirMode = null;
    _flirVisImg.src = '';
    _flirThImg.src = '';
    _flirDrag = false;
    _flirProbes = [];

    if (isVideo) {
        img.style.display = 'none';
        vid.style.display = 'block';
        vid.src = url;
        img.src = '';
        img.classList.remove('cover');
        vid.classList.toggle('cover', _mCoverMode);
        wrap.classList.toggle('cover-wrap', _mCoverMode);
        if (_mCoverMode && p.faces && p.faces.length) {
            var natW = p.img_width || vid.videoWidth || 1;
            var natH = p.img_height || vid.videoHeight || 1;
            var fx1 = Infinity, fy1 = Infinity, fx2 = 0, fy2 = 0;
            for (var i = 0; i < p.faces.length; i++) {
                var f = p.faces[i];
                if (f.bbox_x1 == null) continue;
                fx1 = Math.min(fx1, f.bbox_x1); fy1 = Math.min(fy1, f.bbox_y1);
                fx2 = Math.max(fx2, f.bbox_x2); fy2 = Math.max(fy2, f.bbox_y2);
            }
            if (fx1 < Infinity) {
                vid.style.objectPosition = ((fx1+fx2)/2/natW*100).toFixed(1)+'% '+((fy1+fy2)/2/natH*100).toFixed(1)+'%';
            }
        } else { vid.style.objectPosition = ''; }
    } else {
        vid.style.display = 'none'; vid.src = '';
        img.style.display = 'block'; img.src = url;
        img.classList.remove('cover'); vid.classList.remove('cover');
        wrap.classList.remove('cover-wrap'); img.style.objectPosition = '';
    }

    wrap.style.transform = _mRot ? 'rotate(' + _mRot + 'deg)' : '';
    _mZoom = 1; _mPx = 0; _mPy = 0; _mRot = 0;
    wrap.style.transform = '';
    if (p.edits && p.edits.length) {
        var re = p.edits.find(function(e){return e.action==='rotate'});
        if (re && re.params && re.params.angle) {
            _mRot = re.params.angle;
            wrap.style.transform = 'rotate(' + _mRot + 'deg)';
        }
    }
    var txt = formatDate(p.date);
    if (p.is_raw) txt += '<span class="modal-raw">RAW</span>';
    if (p.camera_make || p.camera_model) txt += '<span class="modal-cam">' + _vEsc((p.camera_make||'')+' '+(p.camera_model||'')) + '</span>';
    document.getElementById('modalDate').innerHTML = txt;
    var flirBar = document.getElementById('modalFlirBar');
    if (p.is_flir) {
        flirBar.style.display = '';
        _mFlirMode = 'thermal';
        var flirBtns = flirBar.querySelectorAll('.flir-mbtn');
        for (var fi = 0; fi < flirBtns.length; fi++) flirBtns[fi].classList.remove('active');
        if (flirBtns[0]) flirBtns[0].classList.add('active');
    } else { flirBar.style.display = 'none'; }
    updateModalGps(p);
    var delBtn = document.getElementById('modalDelBtn');
    if (p.deleted) {
        delBtn.innerHTML = '&#8634;'; delBtn.title = 'Восстановить';
        delBtn.onclick = function() { _vUndelete(p.photo_id); updateModalDel(p); };
    } else {
        delBtn.innerHTML = '&#128465;'; delBtn.title = 'Удалить';
        delBtn.onclick = function() { _vDelete(p.photo_id); };
    }
    var modal = document.getElementById('photoModal');
    modal.classList.add('show');
    var isMobile = _vIsMobile();
    var keepFs = modal.classList.contains('fs') || !!document.fullscreenElement;
    if (isMobile || keepFs) modal.classList.add('fs');
    else modal.classList.remove('fs');

    var overlays = document.getElementById('faceOverlays');
    if (isVideo) { _clearFaceBoxes(); overlays.style.display = 'none'; }
    else { overlays.style.display = 'block'; _drawFaceBoxes(p, img); }

    // FLIR canvas drag/scale/probe
    var cvs = document.getElementById('photoModalCanvas');
    cvs.onmousedown = function(e) {
        if (_mFlirMode !== 'overlay') return;
        var r = cvs.getBoundingClientRect();
        var px = (e.clientX - r.left) * (cvs.width / r.width);
        var py = (e.clientY - r.top) * (cvs.height / r.height);
        var tw = _flirThImg.naturalWidth || 640, th = _flirThImg.naturalHeight || 480;
        var sw = Math.round(tw * _flirScale), sh = Math.round(th * _flirScale);
        var hit = 15;
        var corners = [{cx:_flirOX,cy:_flirOY,corner:'tl'},{cx:_flirOX+sw,cy:_flirOY,corner:'tr'},{cx:_flirOX,cy:_flirOY+sh,corner:'bl'},{cx:_flirOX+sw,cy:_flirOY+sh,corner:'br'}];
        _flirScaleCorner = null;
        for (var i = 0; i < corners.length; i++) {
            if (Math.abs(px - corners[i].cx) < hit && Math.abs(py - corners[i].cy) < hit) { _flirScaleCorner = corners[i].corner; break; }
        }
        _flirDrag = true; _flirDX = e.clientX; _flirDY = e.clientY;
        _flirStartX = e.clientX; _flirStartY = e.clientY;
        cvs.style.cursor = _flirScaleCorner ? 'nwse-resize' : 'grabbing';
    };
    cvs.onmouseup = function(e) {
        if (_mFlirMode !== 'overlay') return;
        var dist = Math.abs(e.clientX - _flirStartX) + Math.abs(e.clientY - _flirStartY);
        if (dist < 5 && !_flirScaleCorner) _flirProbeClick(e);
    };

    _cacheImg(idx + 1); _cacheImg(idx - 1); _cacheImg(idx + 2);
    window.onmousemove = _flirOnMove;
    window.onmouseup = _flirOnUp;

    if (isVideo) {
        vid.play().catch(function(){});
        if (_ssDir !== 0) {
            clearInterval(_ssTimer); _ssTimer = null;
            vid.onended = function() { if (_ssDir !== 0) slideshowAdvance(); };
        }
        if (_mCoverMode) _updateFitIcon(p, true);
        function onVidMeta() { requestAnimationFrame(_positionModalControls); vid.removeEventListener('loadedmetadata', onVidMeta); }
        if (vid.readyState >= 1) requestAnimationFrame(_positionModalControls);
        else vid.addEventListener('loadedmetadata', onVidMeta);
        setTimeout(_positionModalControls, 200);
    } else if (isMobile || _mCoverMode) {
        function onImgReady() { if (img.complete && img.naturalWidth) { smartFit(); img.removeEventListener('load', onImgReady); } }
        if (img.complete && img.naturalWidth) smartFit();
        else img.addEventListener('load', onImgReady);
    } else {
        function onImgPos() { requestAnimationFrame(_positionModalControls); img.removeEventListener('load', onImgPos); }
        if (img.complete && img.naturalWidth) requestAnimationFrame(_positionModalControls);
        else img.addEventListener('load', onImgPos);
    }
    if (ViewerHooks.syncTimeline) ViewerHooks.syncTimeline(p);
    if (ViewerHooks.scrollCardIntoView && p.photo_id) ViewerHooks.scrollCardIntoView(p.photo_id);
}

function closePhotoModal() {
    document.getElementById('photoModal').classList.remove('show');
    var img = document.getElementById('photoModalImg');
    var vid = document.getElementById('photoModalVideo');
    img.src = ''; img.classList.remove('cover'); img.style.display = 'block';
    vid.pause(); vid.removeAttribute('src'); vid.onended = null;
    vid.classList.remove('cover'); vid.style.display = 'none';
    _mCoverMode = false; _mDate = ''; _mPhotoId = ''; Viewer.modalOpen = false;
    _clearFaceBoxes();
    document.getElementById('photoModal').classList.remove('fs');
    if (_ssTimer) { clearInterval(_ssTimer); _ssTimer = null; _ssDir = 0; }
    document.getElementById('modalTopbar').classList.remove('playing');
    window.onmousemove = null; window.onmouseup = null;
    _flirDrag = false; _flirScaleCorner = null;
    _flirOX = 219; _flirOY = 141; _flirScale = 1.5; _flirProbes = [];
    document.getElementById('flirOverlayControls').style.display = 'none';
    var cvs = document.getElementById('photoModalCanvas');
    if (cvs) { cvs.style.display = 'none'; cvs.onmousedown = null; }
    _flirVisImg.src = ''; _flirThImg.src = '';
    if (ViewerHooks.onClose) ViewerHooks.onClose();
}

// ─── Navigation ───
function modalNav(dir) {
    var newIdx = _mIdx + dir;
    if (newIdx < 0) {
        if (ViewerHooks.onNavBoundary && dir < 0) {
            ViewerHooks.onNavBoundary(-1, function(extra) {
                if (extra > 0) { _mIdx += extra; newIdx = _mIdx + dir; if (newIdx >= 0) { _mIdx = newIdx; openViewer(newIdx); } }
            });
        } else if (Viewer.standalone) { _vNavStandalone(dir); }
        return;
    }
    if (newIdx >= Viewer.photos.length) {
        if (ViewerHooks.onNavBoundary && dir > 0) {
            ViewerHooks.onNavBoundary(1, function(extra) {
                if (extra > 0 && newIdx < Viewer.photos.length) { _mIdx = newIdx; openViewer(newIdx); }
            });
        } else if (Viewer.standalone) { _vNavStandalone(dir); }
        return;
    }
    _mIdx = newIdx;
    openViewer(newIdx);
}

function _vNavStandalone(dir) {
    var d = dir > 0 ? 'next' : 'prev';
    fetch(_vAPI() + '/photos/neighbor?date=' + encodeURIComponent(_mDate) + '&dir=' + d)
        .then(function(r) { return r.json(); })
        .then(function(p) {
            if (p && p.photo_id) {
                if (dir > 0) { Viewer.photos.push(p); _mIdx = Viewer.photos.length - 1; }
                else { Viewer.photos.unshift(p); _mIdx = 0; }
                openViewer(_mIdx);
            }
        });
}

// ─── Zoom/Pan ───
function applyModalTransform() {
    var rot = _mRot ? 'rotate(' + _mRot + 'deg) ' : '';
    var wrap = document.getElementById('modalImgWrap');
    if (wrap) wrap.style.transform = rot + 'translate(' + _mPx + 'px,' + _mPy + 'px) scale(' + _mZoom + ')';
    var boxes = document.querySelectorAll('.face-box');
    for (var i = 0; i < boxes.length; i++) {
        boxes[i].style.borderWidth = (2 / _mZoom) + 'px';
        var lbl = boxes[i].querySelector('.face-box-label');
        if (lbl) lbl.style.fontSize = (13 / _mZoom) + 'px';
    }
    _positionModalControls();
}

function _cacheImg(idx) {
    if (idx < 0 || idx >= Viewer.photos.length) return;
    var p = Viewer.photos[idx];
    if (p.media_type === 'video') return;
    var url = p.photo_id ? (_vAPI() + '/photos/?path=' + encodeURIComponent(p.photo_id)) : '';
    if (url && !_imgCache[url]) { var img = new Image(); img.src = url; _imgCache[url] = img; }
}

// ─── Rotate ───
function rotatePhoto(deg) {
    var p = Viewer.photos[_mIdx];
    if (!p) return;
    _mRot = _mRot + deg;
    var wrap = document.getElementById('modalImgWrap');
    if (wrap) {
        var zoomT = _mZoom !== 1 ? ' scale(' + _mZoom + ')' : '';
        var panT = (_mPx || _mPy) ? ' translate(' + _mPx + 'px,' + _mPy + 'px)' : '';
        wrap.style.transform = 'rotate(' + _mRot + 'deg)' + zoomT + panT;
    }
    var saveAngle = ((_mRot % 360) + 360) % 360;
    if (p.content_hash) {
        fetch(_vAPI() + '/photos/edits/' + encodeURIComponent(p.content_hash), {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: 'rotate', params: {angle: saveAngle}, replace: true})
        }).then(function(){
            if (typeof currentPhotos !== 'undefined') {
                for (var i = 0; i < currentPhotos.length; i++) {
                    if (currentPhotos[i].content_hash === p.content_hash) {
                        currentPhotos[i].edits = [{action:'rotate',params:{angle:saveAngle},edit_id:0,action_order:0,enabled:1}];
                    }
                }
            }
        });
    }
    setTimeout(_positionModalControls, 50);
}

// ─── Smart fit ───
function smartFit() {
    var img = document.getElementById('photoModalImg');
    var vid = document.getElementById('photoModalVideo');
    var wrap = document.getElementById('modalImgWrap');
    var p = Viewer.photos[_mIdx];
    if (!p) return;
    var isVideo = p.media_type === 'video';
    var el = isVideo ? vid : img;
    if (!el) return;
    if (el.classList.contains('cover')) {
        el.classList.remove('cover'); wrap.classList.remove('cover-wrap');
        el.style.objectPosition = ''; wrap.style.transform = '';
        wrap.style.transformOrigin = 'center center';
        _mZoom = 1; _mPx = 0; _mPy = 0; _mCoverMode = false;
        _updateFitIcon(p, false);
        if (!isVideo) _drawFaceBoxes(p, img);
        requestAnimationFrame(_positionModalControls);
        return;
    }
    el.classList.add('cover'); wrap.classList.add('cover-wrap'); _mCoverMode = true;
    var natW = (isVideo ? (vid.videoWidth || p.img_width) : (img.naturalWidth || p.img_width)) || 1;
    var natH = (isVideo ? (vid.videoHeight || p.img_height) : (img.naturalHeight || p.img_height)) || 1;
    var faceCenterX = natW / 2, faceCenterY = natH / 2;
    var faces = p.faces || [];
    if (faces.length > 0) {
        var fx1 = Infinity, fy1 = Infinity, fx2 = 0, fy2 = 0;
        for (var i = 0; i < faces.length; i++) {
            var f = faces[i]; if (f.bbox_x1 == null) continue;
            fx1 = Math.min(fx1, f.bbox_x1); fy1 = Math.min(fy1, f.bbox_y1);
            fx2 = Math.max(fx2, f.bbox_x2); fy2 = Math.max(fy2, f.bbox_y2);
        }
        if (fx1 < Infinity) { faceCenterX = (fx1 + fx2) / 2; faceCenterY = (fy1 + fy2) / 2; }
    }
    el.style.objectPosition = (faceCenterX/natW*100).toFixed(1)+'% '+(faceCenterY/natH*100).toFixed(1)+'%';
    wrap.style.transform = _mRot ? 'rotate(' + _mRot + 'deg)' : '';
    _mZoom = 1; _mPx = 0; _mPy = 0;
    _updateFitIcon(p, true);
    if (!isVideo) _drawFaceBoxesCover(p, img);
    requestAnimationFrame(_positionModalControls);
}

// ─── Fit icon ───
function _updateFitIcon(p, isCover) {
    var icon = document.getElementById('fitIcon');
    var btn = document.querySelector('.modal-fit');
    if (!icon) return;
    var maxW = 18, maxH = 14, w, h;
    if (isCover) {
        var isFs = document.getElementById('photoModal').classList.contains('fs');
        var vvH = window.visualViewport ? window.visualViewport.height : window.innerHeight;
        var ratio = isFs ? (window.innerWidth / vvH) : (window.innerWidth * 0.95 / (vvH * 0.95));
        w = maxW; h = Math.max(4, Math.round(maxW / ratio));
        icon.classList.add('outer'); if (btn) btn.title = 'Сжать';
    } else {
        var pw = p.img_width || 4, ph = p.img_height || 3, ratio = pw / ph;
        if (ratio >= 1) { w = maxW; h = Math.max(4, Math.round(maxW / ratio)); }
        else { h = maxH; w = Math.max(4, Math.round(h * ratio)); }
        icon.classList.remove('outer'); if (btn) btn.title = 'Растянуть';
    }
    icon.style.width = w + 'px'; icon.style.height = h + 'px';
}

// ─── Position controls ───
function _positionModalControls() {
    var img = document.getElementById('photoModalImg');
    var vid = document.getElementById('photoModalVideo');
    var btns = document.getElementById('modalBtns');
    var bar = document.getElementById('modalTopbar');
    var modal = document.getElementById('photoModal');
    if (!btns || !bar || !modal || !modal.classList.contains('show')) return;
    var isVideo = vid && vid.style.display !== 'none';
    var el = isVideo ? vid : img;
    if (!el || !el.offsetWidth) return;
    var rect = el.getBoundingClientRect();
    var vpW = window.innerWidth, vpH = window.innerHeight, pad = 10;
    var rightEdge = Math.min(rect.right, vpW) - pad;
    var topEdge = Math.max(rect.top, 0) + pad;
    if (rightEdge < pad + 150) rightEdge = pad + 150;
    if (topEdge > vpH - 40) topEdge = vpH - 40;
    btns.style.top = topEdge + 'px'; btns.style.right = (vpW - rightEdge) + 'px'; btns.style.left = 'auto';
    var bottomEdge = Math.min(rect.bottom, vpH);
    var leftEdge = Math.max(rect.left, pad);
    var barHeight = bar.offsetHeight || 30;
    var isFs = modal.classList.contains('fs');
    var barTop = bottomEdge + 4;
    if (isFs && isVideo) barTop = bottomEdge - barHeight - 44;
    if (barTop + barHeight > vpH - pad) barTop = bottomEdge - barHeight;
    if (barTop < pad) barTop = pad;
    if (_mZoom > 1) { bar.style.top = barTop+'px'; bar.style.left = leftEdge+'px'; bar.style.width = 'auto'; bar.classList.add('zoomed'); }
    else { var barWidth = Math.min(rect.width, vpW - 2*pad); bar.style.top = barTop+'px'; bar.style.left = leftEdge+'px'; bar.style.width = barWidth+'px'; bar.classList.remove('zoomed'); }
    bar.style.transform = '';
}

// ─── Topbar auto-hide ───
function _scheduleTopbarHide() {
    var bar = document.getElementById('modalTopbar');
    var fs = document.querySelector('.modal-fs'), cl = document.querySelector('.modal-close'), ft = document.querySelector('.modal-fit');
    if (bar) bar.classList.remove('hidden');
    if (fs) fs.classList.remove('hidden');
    if (cl) cl.classList.remove('hidden');
    if (ft) ft.classList.remove('hidden');
    clearTimeout(_topbarHideTimer);
    var modal = document.getElementById('photoModal');
    if (modal && modal.classList.contains('fs')) {
        _topbarHideTimer = setTimeout(function() {
            if (bar) bar.classList.add('hidden');
            if (fs) fs.classList.add('hidden');
            if (cl) cl.classList.add('hidden');
            if (ft) ft.classList.add('hidden');
        }, 3000);
    }
}

// ─── Fullscreen ───
function toggleFullscreen() {
    var el = document.getElementById('photoModal');
    if (el.classList.contains('fs')) {
        el.classList.remove('fs');
        if (document.exitFullscreen) document.exitFullscreen();
        var bar = document.getElementById('modalTopbar');
        var fs = document.querySelector('.modal-fs'), cl = document.querySelector('.modal-close'), ft = document.querySelector('.modal-fit');
        if (bar) bar.classList.remove('hidden');
        if (fs) fs.classList.remove('hidden');
        if (cl) cl.classList.remove('hidden');
        if (ft) ft.classList.remove('hidden');
        clearTimeout(_topbarHideTimer);
    } else {
        el.classList.add('fs');
        var fsEl = document.documentElement;
        if (fsEl.requestFullscreen) fsEl.requestFullscreen();
        else if (fsEl.webkitRequestFullscreen) fsEl.webkitRequestFullscreen();
        _scheduleTopbarHide();
    }
    setTimeout(_positionModalControls, 100);
}

// ─── Face boxes ───
function _drawFaceBoxes(p, img) {
    var ov = document.getElementById('faceOverlays');
    ov.innerHTML = '';
    var faces = p.faces || [];
    if (!faces.length) return;
    function doDraw() {
        if (img.classList.contains('cover')) { _drawFaceBoxesCover(p, img); return; }
        var dispW = img.clientWidth, dispH = img.clientHeight;
        if (!dispW || !dispH) return;
        var natW = img.naturalWidth || p.img_width || 1, natH = img.naturalHeight || p.img_height || 1;
        var scaleX = dispW / natW, scaleY = dispH / natH, html = '';
        for (var i = 0; i < faces.length; i++) {
            var f = faces[i]; if (f.bbox_x1 == null) continue;
            var x1 = f.bbox_x1*scaleX, y1 = f.bbox_y1*scaleY, x2 = f.bbox_x2*scaleX, y2 = f.bbox_y2*scaleY;
            var name = f.display_name || f.name || '';
            html += '<div class="face-box" style="left:'+x1+'px;top:'+y1+'px;width:'+(x2-x1)+'px;height:'+(y2-y1)+'px"';
            if (f.persona_id) html += ' onclick="event.stopPropagation();_vFaceClick(\''+_vEsc(f.persona_id)+'\',\''+_vEsc(f.face_id)+'\')"';
            html += '>'; if (name) html += '<div class="face-box-label">'+_vEsc(name)+'</div>'; html += '</div>';
        }
        ov.innerHTML = html;
        if (_mZoom > 1) applyModalTransform();
    }
    if (img.complete && img.naturalWidth) doDraw();
    else img.addEventListener('load', doDraw, {once: true});
}

function _clearFaceBoxes() { document.getElementById('faceOverlays').innerHTML = ''; }

function _drawFaceBoxesCover(p, img) {
    var ov = document.getElementById('faceOverlays'); ov.innerHTML = '';
    var faces = p.faces || []; if (!faces.length) return;
    var dispW = img.clientWidth, dispH = img.clientHeight; if (!dispW || !dispH) return;
    var natW = img.naturalWidth || p.img_width || 1, natH = img.naturalHeight || p.img_height || 1;
    var scale = Math.max(dispW/natW, dispH/natH);
    var renderedW = natW*scale, renderedH = natH*scale;
    var offX = (dispW-renderedW)/2, offY = (dispH-renderedH)/2;
    var pos = img.style.objectPosition || '50% 50%';
    var posParts = pos.split(/\s+/), pxPct = parseFloat(posParts[0])/100, pyPct = parseFloat(posParts[1])/100;
    if (renderedW > dispW) offX = -(renderedW-dispW)*pxPct;
    if (renderedH > dispH) offY = -(renderedH-dispH)*pyPct;
    var html = '';
    for (var i = 0; i < faces.length; i++) {
        var f = faces[i]; if (f.bbox_x1 == null) continue;
        var x1 = offX+f.bbox_x1*scale, y1 = offY+f.bbox_y1*scale, x2 = offX+f.bbox_x2*scale, y2 = offY+f.bbox_y2*scale;
        if (x2<0||y2<0||x1>dispW||y1>dispH) continue;
        x1 = Math.max(0,x1); y1 = Math.max(0,y1); x2 = Math.min(dispW,x2); y2 = Math.min(dispH,y2);
        var name = f.display_name || f.name || '';
        html += '<div class="face-box" style="left:'+x1+'px;top:'+y1+'px;width:'+(x2-x1)+'px;height:'+(y2-y1)+'px"';
        if (f.persona_id) html += ' onclick="event.stopPropagation();_vFaceClick(\''+_vEsc(f.persona_id)+'\',\''+_vEsc(f.face_id)+'\')"';
        html += '>'; if (name) html += '<div class="face-box-label">'+_vEsc(name)+'</div>'; html += '</div>';
    }
    ov.innerHTML = html;
}

function _vFaceClick(personaId, faceId) {
    if (ViewerHooks.onFaceClick) ViewerHooks.onFaceClick(personaId, faceId);
}

// ─── GPS in modal ───
function updateModalGps(p) {
    var locEl = document.getElementById('modalLoc');
    var sepEl = locEl ? locEl.previousElementSibling : null;
    if (!p) return;
    if (p.gps_lat && p.gps_lon) {
        var html = '';
        if (p.manual_gps) {
            html += '<span class="modal-gps-manual">ручная</span>';
            html += '<span class="modal-gps" onclick="_vGoToGps('+p.gps_lat+','+p.gps_lon+')">GPS</span>';
            html += '<span class="modal-clear-gps" onclick="_vClearGps(\''+_vEsc(p.photo_id)+'\')">✕</span>';
        } else {
            html += '<span class="modal-gps" onclick="_vGoToGps('+p.gps_lat+','+p.gps_lon+')">GPS</span>';
        }
        locEl.innerHTML = html; locEl.style.display = '';
        if (sepEl) sepEl.style.display = '';
    } else {
        if (p.photo_id) {
            locEl.innerHTML = '<span class="modal-add-gps" onclick="_vAddGps(\''+_vEsc(p.photo_id)+'\')">📍 Карта</span>';
            locEl.style.display = ''; if (sepEl) sepEl.style.display = '';
        } else { locEl.innerHTML = ''; locEl.style.display = 'none'; if (sepEl) sepEl.style.display = 'none'; }
    }
}

function _vGoToGps(lat, lon) {
    if (ViewerHooks.onGoToGps) ViewerHooks.onGoToGps(lat, lon);
    else { closePhotoModal(); window.open('/map', '_blank'); }
}
function _vClearGps(photoId) {
    if (ViewerHooks.onClearGps) ViewerHooks.onClearGps(photoId);
    else { fetch(_vAPI()+'/photos/clear_gps', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({photo_id:photoId})}); }
}
function _vAddGps(photoId) {
    if (ViewerHooks.onAddGps) ViewerHooks.onAddGps(photoId);
}

// ─── Delete/undelete ───
function _vDelete(photoId) {
    if (ViewerHooks.onDelete) ViewerHooks.onDelete(photoId);
    else {
        fetch(_vAPI()+'/photos/mark_deleted', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({photo_id:photoId})})
            .then(function(r){return r.json();}).then(function(d){ if (d.success) updateModalDel({deleted:true,photo_id:photoId}); });
    }
}
function _vUndelete(photoId) {
    if (ViewerHooks.onUndelete) ViewerHooks.onUndelete(photoId);
    else {
        fetch(_vAPI()+'/photos/undelete', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({photo_id:photoId})})
            .then(function(r){return r.json();}).then(function(d){ if (d.success) updateModalDel({deleted:false,photo_id:photoId}); });
    }
}
function updateModalDel(p) {
    var delBtn = document.getElementById('modalDelBtn');
    if (!delBtn) return;
    if (p.deleted) {
        delBtn.innerHTML = '&#8634;'; delBtn.title = 'Восстановить';
        delBtn.onclick = function() { _vUndelete(p.photo_id); updateModalDel(p); };
    } else {
        delBtn.innerHTML = '&#128465;'; delBtn.title = 'Удалить';
        delBtn.onclick = function() { _vDelete(p.photo_id); };
    }
}

// ─── FLIR ───
function setModalFlir(mode) {
    _mFlirMode = mode;
    var p = Viewer.photos[_mIdx];
    if (!p || !p.is_flir) return;
    var pid = encodeURIComponent(p.photo_id);
    var img = document.getElementById('photoModalImg');
    var cvs = document.getElementById('photoModalCanvas');
    var flirCtrl = document.getElementById('flirOverlayControls');
    if (!img || !cvs) return;
    if (mode === 'overlay') {
        img.style.display = 'none'; cvs.style.display = 'block'; flirCtrl.style.display = 'inline-flex';
        _flirToken++; var tok = _flirToken;
        _flirVisImg.onload = function() { if (tok !== _flirToken) return; if (_flirThImg.complete && _flirThImg.naturalWidth > 0) drawFlirOverlay(); else _flirThImg.onload = function() { if (tok === _flirToken) drawFlirOverlay(); }; };
        var ts = Date.now();
        _flirVisImg.src = _vAPI()+'/photos/flir_visual?path='+pid+'&_t='+ts;
        _flirThImg.src = _vAPI()+'/photos/flir_raw_palette?path='+pid+'&_t='+ts;
    } else {
        img.style.display = 'block'; cvs.style.display = 'none'; flirCtrl.style.display = 'none'; _flirToken++;
        if (mode === 'thermal') img.src = _vAPI()+'/photos/?path='+pid;
        else if (mode === 'visual') img.src = _vAPI()+'/photos/flir_visual?path='+pid;
    }
    var flirBar = document.getElementById('modalFlirBar');
    var btns = flirBar.querySelectorAll('.flir-mbtn');
    for (var i = 0; i < btns.length; i++) btns[i].classList.remove('active');
    if (mode === 'thermal') btns[0].classList.add('active');
    else if (mode === 'visual') btns[1].classList.add('active');
    else btns[2].classList.add('active');
}

function drawFlirOverlay() {
    var cvs = document.getElementById('photoModalCanvas');
    if (!cvs || !_flirVisImg.complete || !_flirThImg.complete) return;
    var alpha = parseFloat(document.getElementById('flirA').value) || 0.5;
    document.getElementById('flirAv').textContent = alpha.toFixed(2);
    var vw = _flirVisImg.naturalWidth || 1440, vh = _flirVisImg.naturalHeight || 1080;
    var tw = _flirThImg.naturalWidth || 640, th = _flirThImg.naturalHeight || 480;
    cvs.width = vw; cvs.height = vh;
    var ctx = cvs.getContext('2d');
    ctx.clearRect(0, 0, vw, vh);
    ctx.drawImage(_flirVisImg, 0, 0, vw, vh);
    var sw = Math.round(tw * _flirScale), sh = Math.round(th * _flirScale);
    ctx.globalAlpha = alpha;
    ctx.drawImage(_flirThImg, _flirOX, _flirOY, sw, sh);
    ctx.globalAlpha = 1.0;
    ctx.strokeStyle = '#0f0'; ctx.lineWidth = 1;
    ctx.strokeRect(_flirOX, _flirOY, sw, sh);
    var hs = 6; ctx.fillStyle = '#0f0';
    [[_flirOX,_flirOY],[_flirOX+sw,_flirOY],[_flirOX,_flirOY+sh],[_flirOX+sw,_flirOY+sh]].forEach(function(p) { ctx.fillRect(p[0]-hs/2, p[1]-hs/2, hs, hs); });
    cvs.style.width = '100%'; cvs.style.height = '100%';
    ctx.font = '12px monospace'; ctx.lineWidth = 2;
    for (var i = 0; i < _flirProbes.length; i++) {
        var pr = _flirProbes[i];
        var px = _flirOX + pr.tx * _flirScale, py = _flirOY + pr.ty * _flirScale;
        ctx.fillStyle = '#ff0'; ctx.beginPath(); ctx.arc(px, py, 4, 0, 2*Math.PI); ctx.fill();
        var txt = pr.temp + '\u00B0C';
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 3; ctx.strokeText(txt, px + 8, py + 4);
        ctx.fillStyle = '#000'; ctx.lineWidth = 1; ctx.fillText(txt, px + 8, py + 4);
    }
}

function _flirOnMove(e) {
    if (!_flirDrag) return;
    var cvs = document.getElementById('photoModalCanvas');
    if (!cvs || _mFlirMode !== 'overlay') return;
    var r = cvs.getBoundingClientRect();
    var px = (e.clientX - r.left) * (cvs.width / r.width), py = (e.clientY - r.top) * (cvs.height / r.height);
    var tw = _flirThImg.naturalWidth || 640, th = _flirThImg.naturalHeight || 480;
    if (_flirScaleCorner) {
        var oppX, oppY;
        switch (_flirScaleCorner) {
            case 'tl': oppX=_flirOX+Math.round(tw*_flirScale); oppY=_flirOY+Math.round(th*_flirScale); break;
            case 'tr': oppX=_flirOX; oppY=_flirOY+Math.round(th*_flirScale); break;
            case 'bl': oppX=_flirOX+Math.round(tw*_flirScale); oppY=_flirOY; break;
            case 'br': oppX=_flirOX; oppY=_flirOY; break;
        }
        var newDist = Math.sqrt((px-oppX)*(px-oppX)+(py-oppY)*(py-oppY));
        _flirScale = Math.max(0.3, Math.min(5.0, newDist / Math.sqrt(tw*tw+th*th)));
        switch (_flirScaleCorner) {
            case 'tl': _flirOX=oppX-Math.round(tw*_flirScale); _flirOY=oppY-Math.round(th*_flirScale); break;
            case 'tr': _flirOY=oppY-Math.round(th*_flirScale); break;
            case 'bl': _flirOX=oppX-Math.round(tw*_flirScale); break;
        }
    } else {
        var dx = (e.clientX - _flirDX) * (cvs.width / r.width), dy = (e.clientY - _flirDY) * (cvs.height / r.height);
        _flirOX += Math.round(dx); _flirOY += Math.round(dy);
    }
    _flirDX = e.clientX; _flirDY = e.clientY;
    drawFlirOverlay();
}
function _flirOnUp() {
    _flirDrag = false; _flirScaleCorner = null;
    var cvs = document.getElementById('photoModalCanvas');
    if (cvs) cvs.style.cursor = 'grab';
}
function _flirProbeClick(e) {
    var cvs = document.getElementById('photoModalCanvas');
    if (!cvs || _mFlirMode !== 'overlay') return;
    var r = cvs.getBoundingClientRect();
    var px = (e.clientX - r.left) * (cvs.width / r.width), py = (e.clientY - r.top) * (cvs.height / r.height);
    var tw = _flirThImg.naturalWidth || 640, th = _flirThImg.naturalHeight || 480;
    var tx = (px - _flirOX) / _flirScale, ty = (py - _flirOY) / _flirScale;
    if (tx < 0 || ty < 0 || tx >= tw || ty >= th) return;
    var p = Viewer.photos[_mIdx]; if (!p) return;
    var pid = encodeURIComponent(p.photo_id);
    var xhr = new XMLHttpRequest();
    xhr.open('GET', _vAPI()+'/photos/flir_temperature?path='+pid+'&x='+Math.round(tx)+'&y='+Math.round(ty), true);
    xhr.onload = function() {
        if (xhr.status === 200) {
            var data = JSON.parse(xhr.responseText);
            _flirProbes.push({tx: Math.round(tx), ty: Math.round(ty), temp: data.temp_c});
            drawFlirOverlay();
        }
    };
    xhr.send();
}

// ─── Slideshow ───
function slideshowToggle(dir) {
    _ssDir = dir;
    clearInterval(_ssTimer); _ssTimer = null;
    document.getElementById('modalTopbar').classList.add('playing');
    _clearFaceBoxes();
    var p = Viewer.photos[_mIdx];
    var vid = document.getElementById('photoModalVideo');
    if (p && p.media_type === 'video' && vid) {
        vid.onended = function() { if (_ssDir !== 0) slideshowAdvance(); };
        if (vid.paused) vid.play().catch(function(){});
    } else { _ssTimer = setInterval(function() { slideshowAdvance(); }, 5000); }
    if (ViewerHooks.syncTimeline) ViewerHooks.syncTimeline(p);
}
function _slideshowOpen(newIdx) {
    if (newIdx < 0 || newIdx >= Viewer.photos.length) return;
    openViewer(newIdx); _clearFaceBoxes();
    _cacheImg(newIdx + _ssDir); _cacheImg(newIdx + _ssDir * 2);
    if (ViewerHooks.syncTimeline) ViewerHooks.syncTimeline(Viewer.photos[newIdx]);
    var p = Viewer.photos[newIdx];
    clearInterval(_ssTimer); _ssTimer = null;
    if (p && p.media_type !== 'video') _ssTimer = setInterval(function() { slideshowAdvance(); }, 5000);
}
function slideshowAdvance() {
    if (_ssDir === 0) return;
    var newIdx = _mIdx + _ssDir;
    if (newIdx < 0) {
        if (ViewerHooks.onNavBoundary && _ssDir < 0) {
            ViewerHooks.onNavBoundary(-1, function(extra) {
                if (_ssDir !== 0 && extra > 0) { _mIdx += extra; newIdx = _mIdx + _ssDir; if (newIdx >= 0) _slideshowOpen(newIdx); }
            });
        } else { slideshowStop(); } return;
    }
    if (newIdx >= Viewer.photos.length) {
        if (ViewerHooks.onNavBoundary && _ssDir > 0) {
            ViewerHooks.onNavBoundary(1, function(extra) {
                if (_ssDir !== 0 && extra > 0 && newIdx < Viewer.photos.length) _slideshowOpen(newIdx);
            });
        } else { slideshowStop(); } return;
    }
    _slideshowOpen(newIdx);
}
function slideshowStop() {
    _ssDir = 0; clearInterval(_ssTimer); _ssTimer = null;
    document.getElementById('modalTopbar').classList.remove('playing');
    var p = Viewer.photos[_mIdx];
    var vid = document.getElementById('photoModalVideo');
    if (vid) vid.onended = null;
    if (p && p.media_type !== 'video') { var img = document.getElementById('photoModalImg'); if (img) _drawFaceBoxes(p, img); }
}

// ─── Full video modal ───
function closeVideoModal() {
    document.getElementById('vidModal').classList.remove('show');
    var vp = document.getElementById('vidModalPlayer');
    vp.pause(); vp.removeAttribute('src');
}
function openFullPhoto(url) {
    var idx = Viewer.photos.findIndex(function(p) { return _vVideoSrc(p) === url || (_vAPI() + '/photos/?path=' + encodeURIComponent(p.photo_id)) === url; });
    if (idx >= 0) openViewer(idx);
}

// ─── Zoom/pan/touch init ───
(function() {
    var modal = document.getElementById('photoModal');
    if (!modal) return;
    modal.addEventListener('click', function(e) { if (e.target === this) closePhotoModal(); });
    modal.addEventListener('wheel', function(e) {
        e.preventDefault();
        var wrap = document.getElementById('modalImgWrap');
        if (!wrap) return;
        var rect = wrap.getBoundingClientRect();
        var cx = e.clientX - rect.left - rect.width / 2 - _mPx;
        var cy = e.clientY - rect.top - rect.height / 2 - _mPy;
        var oldZ = _mZoom;
        _mZoom = Math.max(1, Math.min(20, _mZoom * (e.deltaY > 0 ? 0.8 : 1.25)));
        var ratio = _mZoom / oldZ;
        _mPx -= cx * (ratio - 1); _mPy -= cy * (ratio - 1);
        if (_mZoom <= 1) { _mPx = 0; _mPy = 0; }
        applyModalTransform();
    }, { passive: false });
    var wrap = document.getElementById('modalImgWrap');
    if (wrap) wrap.addEventListener('mousedown', function(e) {
        if (_mZoom > 1) { e.preventDefault(); _mDrag = true; _mDX = e.clientX - _mPx; _mDY = e.clientY - _mPy; e.currentTarget.style.cursor = 'grabbing'; }
    });
    document.addEventListener('mousemove', function(e) { if (_mDrag) { _mPx = e.clientX - _mDX; _mPy = e.clientY - _mDY; applyModalTransform(); } });
    document.addEventListener('mouseup', function() { if (_mDrag) { _mDrag = false; var w = document.getElementById('modalImgWrap'); if (w) w.style.cursor = 'grab'; } });
    document.addEventListener('fullscreenchange', function() {
        if (!document.fullscreenElement) document.getElementById('photoModal').classList.remove('fs');
        setTimeout(_positionModalControls, 100);
    });
    // Touch
    var sx = 0, sy = 0, st = 0, pinchStartDist = 0, pinchStartZoom = 1, panStartX = 0, panStartY = 0, isPanning = false;
    modal.addEventListener('touchstart', function(e) {
        if (e.touches.length === 2) { pinchStartDist = Math.hypot(e.touches[0].clientX-e.touches[1].clientX, e.touches[0].clientY-e.touches[1].clientY); pinchStartZoom = _mZoom; return; }
        if (e.touches.length === 1) { sx=e.touches[0].clientX; sy=e.touches[0].clientY; st=Date.now(); if (_mZoom>1) { isPanning=true; panStartX=e.touches[0].clientX-_mPx; panStartY=e.touches[0].clientY-_mPy; } }
    }, { passive: true });
    modal.addEventListener('touchmove', function(e) {
        if (e.touches.length === 2 && pinchStartDist > 0) { var dist = Math.hypot(e.touches[0].clientX-e.touches[1].clientX, e.touches[0].clientY-e.touches[1].clientY); _mZoom = Math.max(1, Math.min(20, pinchStartZoom * dist / pinchStartDist)); if (_mZoom <= 1) { _mPx = 0; _mPy = 0; } applyModalTransform(); return; }
        if (isPanning && e.touches.length === 1) { _mPx = e.touches[0].clientX - panStartX; _mPy = e.touches[0].clientY - panStartY; applyModalTransform(); }
    }, { passive: true });
    modal.addEventListener('touchend', function(e) {
        isPanning = false; pinchStartDist = 0;
        if (e.touches.length > 0) return;
        if (_mZoom > 1) return;
        var dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy, dt = Date.now() - st;
        if (dt < 500 && Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) { if (dx < 0) modalNav(1); else modalNav(-1); }
    }, { passive: true });
    // Keyboard
    document.addEventListener('keydown', function(e) {
        if (!Viewer.modalOpen) return;
        if (e.key === 'ArrowLeft') modalNav(-1);
        else if (e.key === 'ArrowRight') modalNav(1);
        else if (e.key === 'Escape') closePhotoModal();
    });
})();

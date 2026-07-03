/* gallery-common.js — общие функции карточек фото для gallery и albums.
   Загружается ДО gallery.js / albums.js.
   Зависит от: viewer.js (Viewer, formatDate), shared.js (esc если есть)
   Опциональные зависимости (есть только в gallery):
     isSemanticMode, goToTimelineFromCard, searchInput
*/
/* global API, Viewer, closeDetail, currentPhotos, openDetail, openFaceModal, markDeleted, videoSrc, esc, formatDate, isSemanticMode, goToTimelineFromCard */

function _isMobile() { return window.innerWidth <= 768; }

// ─── Detail panel: swipe-to-close on mobile (инициализация после загрузки) ───
document.addEventListener('DOMContentLoaded', function() {
    if (typeof openDetail !== 'function') return;
    var dpHandleAdded = false;
    var _origOpenDetail = openDetail;
    openDetail = function(idx) {
        _origOpenDetail(idx);
        if (!dpHandleAdded && _isMobile()) {
            var dp = document.getElementById('detailPanel');
            if (dp && !dp.querySelector('.dp-handle')) {
                var handle = document.createElement('div');
                handle.className = 'dp-handle';
                dp.insertBefore(handle, dp.firstChild);
                dpHandleAdded = true;
            }
        }
    };
    var dp = document.getElementById('detailPanel');
    if (!dp) return;
    var dpStartY = 0, dpCurY = 0, dpDragging = false;
    dp.addEventListener('touchstart', function(e) {
        var t = e.touches[0];
        var handle = dp.querySelector('.dp-handle');
        if (!handle) return;
        var rect = handle.getBoundingClientRect();
        if (t.clientY >= rect.top - 15 && t.clientY <= rect.bottom + 25) {
            dpDragging = true;
            dpStartY = t.clientY;
            dp.style.transition = 'none';
        }
    }, { passive: true });
    dp.addEventListener('touchmove', function(e) {
        if (!dpDragging) return;
        var dy = e.touches[0].clientY - dpStartY;
        if (dy > 0) {
            dpCurY = dy;
            dp.style.transform = 'translateY(' + dy + 'px)';
        }
    }, { passive: true });
    dp.addEventListener('touchend', function() {
        if (!dpDragging) return;
        dpDragging = false;
        dp.style.transition = '';
        dp.style.transform = '';
        if (dpCurY > 80) closeDetail();
        dpCurY = 0;
    }, { passive: true });
});

if (typeof esc !== 'function') {
    function esc(s) {
        if (!s) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
}

var _videoPreviewTimer = null;
var _videoPreviewEl = null;
var _faceLazyObs = null;
var _faceLoadEnabled = false;

function startVideoPreview(card, idx) {
    clearTimeout(_videoPreviewTimer);
    _videoPreviewTimer = setTimeout(function() {
        var p = currentPhotos[idx];
        if (!p || p.media_type !== 'video') return;
        var url = (typeof videoSrc === 'function') ? videoSrc(p) : (API + '/photos/?path=' + encodeURIComponent(p.photo_id));
        if (!url) return;
        var v = document.createElement('video');
        v.className = 'card-preview-video';
        v.muted = true;
        v.loop = true;
        v.playsInline = true;
        v.preload = 'auto';
        v.src = url;
        v.play().catch(function(){});
        card.appendChild(v);
        _videoPreviewEl = v;
    }, 400);
}

function stopVideoPreview(card) {
    clearTimeout(_videoPreviewTimer);
    if (_videoPreviewEl) {
        _videoPreviewEl.pause();
        _videoPreviewEl.removeAttribute('src');
        _videoPreviewEl.load();
        if (_videoPreviewEl.parentNode) _videoPreviewEl.parentNode.removeChild(_videoPreviewEl);
        _videoPreviewEl = null;
    }
}

function playVideoCard(idx) {
    var p = currentPhotos[idx];
    if (!p) return;
    var url = (typeof videoSrc === 'function') ? videoSrc(p) : (API + '/photos/?path=' + encodeURIComponent(p.photo_id));
    var bar = document.getElementById('vidModalBar');
    var txt = (typeof formatDate === 'function') ? formatDate(p.date) : (p.date || '');
    if (p.camera_make || p.camera_model) txt += ' <span style="color:#6e7681">&bull;</span> ' + esc((p.camera_make || '') + ' ' + (p.camera_model || ''));
    if (bar) bar.innerHTML = txt;
    var old = document.getElementById('vidModalPlayer');
    if (old) old.outerHTML = '<video id="vidModalPlayer" src="' + url + '" controls preload="metadata" onclick="event.stopPropagation()"></video>';
    var vm = document.getElementById('vidModal');
    if (vm) vm.classList.add('show');
    setTimeout(function(){
        var v = document.getElementById('vidModalPlayer');
        if (v) v.play();
    }, 200);
}

function _observeThumbs() {
    if (!_faceLoadEnabled) return;
    if (!_faceLazyObs) {
        _faceLazyObs = new IntersectionObserver(function(entries) {
            for (var i = 0; i < entries.length; i++) {
                if (entries[i].isIntersecting) {
                    var img = entries[i].target;
                    var ds = img.getAttribute('data-src');
                    if (ds) { img.setAttribute('src', ds); img.removeAttribute('data-src'); }
                    _faceLazyObs.unobserve(img);
                }
            }
        }, { rootMargin: '0px' });
    }
    var faces = document.querySelectorAll('.lazy-face[data-src]');
    for (var i = 0; i < faces.length; i++) _faceLazyObs.observe(faces[i]);
}

function buildCardHtml(p, idx) {
    var thumbBase = p.photo_id ? (API + '/photos/thumbnail?path=' + encodeURIComponent(p.photo_id)) : '';
    var desc = p.description || '';
    var shortDesc = desc.length > 80 ? desc.substring(0, 80) + '...' : desc;
    var dateStr = '';
    if (p.date) {
        var dp = p.date.substring(0, 10).split('-');
        if (dp.length === 3) dateStr = dp[2] + '.' + dp[1] + '.' + dp[0];
        else dateStr = p.date.substring(0, 10);
    }
    var facesHtml = '';
    if (p.personas && p.personas.length > 0) {
        var sorted = p.personas.slice().sort(function(a,b){ return (b.total_face_count||0) - (a.total_face_count||0); });
        facesHtml = '<div class="faces">';
        for (var j = 0; j < sorted.length && j < 7; j++) {
            var per = sorted[j];
            var fid = (per.face_ids && per.face_ids.length > 0) ? per.face_ids[0] : '';
            var hasName = per.display_name ? true : false;
            var cls = hasName ? 'face-thumb named' : 'face-thumb';
            if (fid) facesHtml += '<img class="' + cls + ' lazy-face" data-src="' + API + '/photos/face/' + fid + '?margin=0.5" title="' + esc(per.display_name || per.name) + '" onclick="event.stopPropagation();openFaceModal(\'' + esc(per.persona_id) + '\',\'' + fid + '\')">';
        }
        facesHtml += '</div>';
    }
    var _semMode = (typeof isSemanticMode !== 'undefined') ? isSemanticMode : false;
    var hasRel = _semMode && p.score !== undefined && p.score !== null;
    var hasFaces = p.personas && p.personas.length > 0;
    var relBadge = '';
    var badge = '';
    var badgeShift = p.is_raw ? ';top:22px' : '';
    if (hasRel) {
        var pct = Math.round((1 - p.score) * 100);
        var clr = pct >= 60 ? '#3fb950' : pct >= 40 ? '#d29922' : '#f85149';
        relBadge = '<div class="badge badge-rel" style="color:' + clr + badgeShift + '">' + pct + '%</div>';
    }
    if (hasFaces) {
        var fcls = hasRel ? 'badge badge-faces' : 'badge badge-only';
        var ftop = hasRel ? (p.is_raw ? ' style="top:40px"' : '') : (p.is_raw ? ' style="top:22px"' : '');
        badge = '<div class="' + fcls + '"' + ftop + '>' + p.personas.length + ' лиц</div>';
    }
    var _videoHover = p.media_type === 'video' ? ' onmouseenter="startVideoPreview(this,' + idx + ')" onmouseleave="stopVideoPreview(this)"' : '';
    var html = '<div class="card' + (p.deleted ? ' deleted-card' : '') + '" data-date="' + esc(p.date_utc || p.date || '') + '" data-photo-id="' + esc(p.photo_id || '') + '"' + _videoHover + ' onclick="Viewer.open(currentPhotos,' + idx + ')" ondblclick="event.stopPropagation();Viewer.open(currentPhotos,' + idx + ');toggleFullscreen()">';
    html += '<button class="expand-btn" onclick="event.stopPropagation();openDetail(' + idx + ')" title="Подробности">&#8505;</button>';
    var q = '';
    var si = document.getElementById('searchInput');
    if (si) q = si.value.trim();
    if (q && (typeof goToTimelineFromCard === 'function')) html += '<button class="goto-btn" onclick="event.stopPropagation();goToTimelineFromCard(' + idx + ')" title="Найти в хронологии">&#x21E1;</button>';
    if (thumbBase) {
        var _rot = '';
        if (p.edits) { var _re = p.edits.find(function(e){return e.action==='rotate'}); if (_re) _rot = ' style="transform:rotate('+((_re.params.angle % 360 + 360) % 360)+'deg)"'; }
        html += '<img' + _rot + ' fetchpriority="high" src="' + thumbBase + '&size=sm" srcset="' + thumbBase + '&size=sm 400w, ' + thumbBase + '&size=md 800w" sizes="400px" loading="lazy" decoding="async" onerror="this.style.display=\'none\'">';
    }
    html += badge;
    html += relBadge;
    var topBadges = '';
    if (p.is_raw) topBadges += '<div class="tb raw">RAW</div>';
    if (p.gps_lat && p.gps_lon) topBadges += '<div class="tb gps" onclick="event.stopPropagation();window.open(\'/map#locate/\'+this.dataset.loc,\'_blank\')" data-loc="' + p.gps_lat + ',' + p.gps_lon + ',' + encodeURIComponent(p.photo_id || '') + '">GPS</div>';
    if (p.media_type === 'video' && p.duration_seconds) {
        var mins = Math.floor(p.duration_seconds / 60);
        var secs = Math.floor(p.duration_seconds % 60);
        var durStr = mins + ':' + (secs < 10 ? '0' : '') + secs;
        topBadges += '<div class="tb dur">' + durStr + '</div>';
    }
    if (topBadges) html += '<div class="top-badges">' + topBadges + '</div>';
    if (p.media_type === 'video' && p.duration_seconds) {
        html += '<div class="video-play-overlay"><span>&#9654;</span></div>';
    }
    if (!p.deleted) html += '<div class="del-mark" onclick="event.stopPropagation();markDeleted(\'' + esc(p.photo_id || '') + '\')" title="Удалить">&#128465;</div>';
    html += '<div class="overlay">';
    if (dateStr) html += '<div class="date">' + esc(dateStr) + '</div>';
    if (shortDesc) html += '<div class="desc">' + esc(shortDesc) + '</div>';
    html += facesHtml;
    html += '</div></div>';
    return html;
}

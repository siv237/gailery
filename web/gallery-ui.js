function closePhotoModal() {
    document.getElementById('photoModal').classList.remove('show');
    var img = document.getElementById('photoModalImg');
    var vid = document.getElementById('photoModalVideo');
    img.src = '';
    img.classList.remove('cover');
    img.style.display = 'block';
    vid.pause();
    vid.removeAttribute('src');
    vid.onended = null;
    vid.classList.remove('cover');
    vid.style.display = 'none';
    _mCoverMode = false;
    _mDate = '';
    _mPhotoId = '';
    _clearFaceBoxes();
    document.getElementById('photoModal').classList.remove('fs');
     if (_ssTimer) { clearInterval(_ssTimer); _ssTimer = null; _ssDir = 0; var lastPid = currentPhotos[_mIdx] && currentPhotos[_mIdx].photo_id; }
     document.getElementById('modalTopbar').classList.remove('playing');
      if (lastPid) { var c = document.querySelector('.card[data-photo-id="' + CSS.escape(lastPid) + '"]'); if (c) { c.scrollIntoView({block:'center'}); } }
     _modalOpen = false;
    // FLIR cleanup
    window.onmousemove = null;
    window.onmouseup = null;
    _flirDrag = false;
    _flirScaleCorner = null;
    _flirOX = 219; _flirOY = 141; _flirScale = 1.5;
    _flirProbes = [];
    document.getElementById('flirOverlayControls').style.display = 'none';
    var cvs = document.getElementById('photoModalCanvas');
    if (cvs) { cvs.style.display = 'none'; cvs.onmousedown = null; }
    _flirVisImg.src = '';
    _flirThImg.src = '';
    if (_embeddedMode && window.parent) {
        window.parent.postMessage({type: 'closeModal'}, '*');
    }
}

function goToTimeline() {
    var p = currentPhotos[_mIdx];
    if (!p) return;
    _goToTimeline(p);
}

function goToTimelineFromCard(idx) {
    var p = currentPhotos[idx];
    if (!p) return;
    _goToTimeline(p);
}

function _goToTimeline(p) {
    var date = p.date || '';
    var pid = p.photo_id || '';
    closeDetail();
    document.getElementById('searchInput').value = '';
    document.getElementById('searchMode').value = 'text';
    onModeChange();
    isSemanticMode = false;
    activeDate = '';
    _restoreNeedleDate = date;
    _restorePhotoId = pid;
    doSearch();
}

document.getElementById('vidModal').addEventListener('click', function(e) {
    if (e.target === this) closeVideoModal();
});

document.getElementById('photoModal').addEventListener('mousemove', function() {
    _scheduleTopbarHide();
});

function filterByPerson(name) {
    activePerson = name;
    closeDetail();
    doSearch();
}

function openPersonFilter() {
    if (allPersonas.length === 0) {
        fetch(API + '/persons/?limit=500&named_only=true').then(function(r) { return r.json(); }).then(function(data) {
            allPersonas = data.persons;
            renderPersonList(list);
            document.getElementById('personFilter').classList.add('show');
        });
    } else {
        renderPersonList(allPersonas);
        document.getElementById('personFilter').classList.add('show');
    }
}

function renderPersonList(list) {
    var groups = {};
    var unnamed = [];
    for (var i = 0; i < list.length; i++) {
        var p = list[i];
        if (p.display_name) {
            var key = p.display_name;
            if (!groups[key]) groups[key] = { display_name: key, face_count: 0, face_id: null, persona_ids: [] };
            groups[key].face_count += (p.face_count || 0);
            if (!groups[key].face_id && p.face_id) groups[key].face_id = p.face_id;
            groups[key].persona_ids.push(p.persona_id);
        } else {
            unnamed.push(p);
        }
    }
    var named = [];
    for (var k in groups) named.push(groups[k]);
    named.sort(function(a, b) { return b.face_count - a.face_count; });
    unnamed.sort(function(a, b) { return (b.face_count || 0) - (a.face_count || 0); });

    var html = '';
    if (activePerson) {
        html += '<div class="pf-item" onclick="clearPersonFilter()"><span class="nm" style="color:#d29922">Сбросить фильтр</span></div>';
    }
    for (var i = 0; i < named.length; i++) {
        var p = named[i];
        html += '<div class="pf-item" onclick="selectPersonFilter(\'' + esc(p.display_name) + '\')">';
        if (p.face_id) html += '<img src="' + API + '/photos/face/' + p.face_id + '?margin=0.5" loading="lazy">';
        html += '<span class="nm">' + esc(p.display_name) + '</span>';
        html += '<span class="cnt">' + p.face_count + 'л</span></div>';
    }
    if (unnamed.length > 0) {
        html += '<div style="color:#6e7681;font-size:10px;padding:6px 4px;margin-top:8px">Без имени:</div>';
        for (var i = 0; i < Math.min(unnamed.length, 20); i++) {
            var p = unnamed[i];
            html += '<div class="pf-item" onclick="selectPersonFilter(\'' + esc(p.name || p.persona_id) + '\')">';
        if (p.face_id) html += '<img src="' + API + '/photos/face/' + p.face_id + '?margin=0.5" loading="lazy">';
            html += '<span class="nm" style="color:#6e7681">' + esc(p.name || p.persona_id) + '</span>';
            html += '<span class="cnt">' + (p.face_count || 0) + 'л</span></div>';
        }
    }
    document.getElementById('pfList').innerHTML = html;
}

function filterPersonList() {
    var val = document.getElementById('pfSearch').value.toLowerCase();
    if (!val) {
        renderPersonList(allPersonas);
        return;
    }
    var filtered = allPersonas.filter(function(p) {
        var nm = (p.display_name || p.name || '').toLowerCase();
        return nm.indexOf(val) >= 0;
    });
    renderPersonList(filtered);
}

function selectPersonFilter(name) {
    activePerson = name;
    document.getElementById('personFilter').classList.remove('show');
    doSearch();
}

function clearPersonFilter() {
    activePerson = '';
    document.getElementById('personFilter').classList.remove('show');
    doSearch();
}

function closePersonFilter() {
    document.getElementById('personFilter').classList.remove('show');
}

function clearFilters() {
    document.getElementById('searchInput').value = '';
    document.getElementById('chkFaces').checked = false;
        document.getElementById('chkHasDesc').checked = false;
    document.getElementById('chkIssues').checked = false;
    document.getElementById('chkGps').checked = false;
    document.getElementById('chkDeleted').checked = false;
     document.getElementById('chkCatPhoto').checked = true;
     document.getElementById('chkCatScreenshot').checked = true;
     document.getElementById('chkCatDocument').checked = true;
     document.getElementById('chkCatMeme').checked = true;
     document.getElementById('chkCatIcon').checked = true;
     document.getElementById('chkCatOther').checked = true;
     updateCatFilterLabel();
     document.getElementById('chkRaw').checked = true;
     document.getElementById('chkJpeg').checked = true;
     document.getElementById('chkVideo').checked = true;
     updateTypeFilterLabel();
    activeDate = '';
    activePerson = '';
    doSearch();
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { closePhotoModal(); closeDetail(); closeFaceModal(); closePersonFilter(); closeVideoModal(); document.getElementById('renameDialog').classList.remove('show'); cancelDel(); }
    if (_mDate) {
        if (e.key === 'ArrowLeft') modalNav(-1);
        else if (e.key === 'ArrowRight') modalNav(1);
    }
});

FaceModalHooks.onSaved = function(personaId, displayName) {
    for (var i = 0; i < currentPhotos.length; i++) {
        var p = currentPhotos[i];
        var faces = p.faces || [];
        var changed = false;
        for (var j = 0; j < faces.length; j++) {
            if (faces[j].persona_id === personaId) {
                faces[j].display_name = displayName || null;
                faces[j].name = displayName || faces[j].name;
                changed = true;
            }
        }
        if (changed) {
            var personas = p.personas || [];
            for (var k = 0; k < personas.length; k++) {
                if (personas[k].persona_id === personaId) {
                    personas[k].display_name = displayName || null;
                    if (displayName) personas[k].name = displayName;
                }
            }
        }
    }
    var img = document.getElementById('photoModalImg');
    if (img && img.src && _mPhotoId) {
        var cp = currentPhotos.find(function(ph) { return ph.photo_id === _mPhotoId; });
        if (cp) _drawFaceBoxes(cp, img);
    }
};

loadTimeline();
onModeChange();

function saveFilters() {
    var state = {
        mode: document.getElementById('searchMode').value,
        q: document.getElementById('searchInput').value,
        sort: document.getElementById('sortSelect').value,
        faces: document.getElementById('chkFaces').checked,
        desc: document.getElementById('chkHasDesc').checked,
        issues: document.getElementById('chkIssues').checked,
        gps: document.getElementById('chkGps').checked,
        deleted: document.getElementById('chkDeleted').checked,
        catPhoto: document.getElementById('chkCatPhoto').checked,
        catScreenshot: document.getElementById('chkCatScreenshot').checked,
        catDocument: document.getElementById('chkCatDocument').checked,
        catMeme: document.getElementById('chkCatMeme').checked,
        catIcon: document.getElementById('chkCatIcon').checked,
        catOther: document.getElementById('chkCatOther').checked,
        chkRaw: document.getElementById('chkRaw').checked,
        chkJpeg: document.getElementById('chkJpeg').checked,
        chkVideo: document.getElementById('chkVideo').checked,
        needleDate: _needleDateISO || null,
        photoId: _firstVisiblePhotoId || null,
        tlZoom: _tlZoom,
        tlOffsetX: _tlOffsetX,
    };
    localStorage.setItem('gallery-filters', JSON.stringify(state));
}

function restoreFilters() {
    try {
        var raw = localStorage.getItem('gallery-filters');
        if (!raw) return;
        var s = JSON.parse(raw);
        if (s.mode) document.getElementById('searchMode').value = s.mode;
        if (s.q) document.getElementById('searchInput').value = s.q;
        if (s.sort) document.getElementById('sortSelect').value = s.sort;
        if (s.faces) document.getElementById('chkFaces').checked = true;
        if (s.desc) document.getElementById('chkHasDesc').checked = true;
        if (s.issues) document.getElementById('chkIssues').checked = true;
        if (s.gps) document.getElementById('chkGps').checked = true;
        if (s.deleted) document.getElementById('chkDeleted').checked = true;
        if (s.catPhoto !== undefined) document.getElementById('chkCatPhoto').checked = s.catPhoto;
        if (s.catScreenshot !== undefined) document.getElementById('chkCatScreenshot').checked = s.catScreenshot;
        if (s.catDocument !== undefined) document.getElementById('chkCatDocument').checked = s.catDocument;
        if (s.catMeme !== undefined) document.getElementById('chkCatMeme').checked = s.catMeme;
        if (s.catIcon !== undefined) document.getElementById('chkCatIcon').checked = s.catIcon;
        if (s.catOther !== undefined) document.getElementById('chkCatOther').checked = s.catOther;
        updateCatFilterLabel();
        if (s.chkRaw !== undefined) document.getElementById('chkRaw').checked = s.chkRaw;
        if (s.chkJpeg !== undefined) document.getElementById('chkJpeg').checked = s.chkJpeg;
        if (s.chkVideo !== undefined) document.getElementById('chkVideo').checked = s.chkVideo;
        updateTypeFilterLabel();
        onModeChange();
        _restoreNeedleDate = s.needleDate || null;
        _restorePhotoId = s.photoId || null;
    } catch(e) {}
}

var _restoreNeedleDate = null;
var _restorePhotoId = null;
var _openViewerOnLoad = false;
var _tlMonthFrom = null;
var _tlMonthTo = null;
var _needleDateISO = null;
var _firstVisiblePhotoId = null;

if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

document.getElementById('chkRaw').checked = true;
document.getElementById('chkJpeg').checked = true;
document.getElementById('chkVideo').checked = true;
updateTypeFilterLabel();
document.getElementById('chkCatPhoto').checked = true;
document.getElementById('chkCatScreenshot').checked = true;
document.getElementById('chkCatDocument').checked = true;
document.getElementById('chkCatMeme').checked = true;
document.getElementById('chkCatIcon').checked = true;
document.getElementById('chkCatOther').checked = true;
updateCatFilterLabel();

restoreFilters();
var _urlParams = new URLSearchParams(window.location.search);
var _urlPhotoId = _urlParams.get('photo_id');
var _urlDate = _urlParams.get('date');
var _embeddedMode = _urlParams.get('embedded') === '1';
if (_urlPhotoId) {
    _restorePhotoId = _urlPhotoId;
    _openViewerOnLoad = true;
    if (_urlDate) _restoreNeedleDate = _urlDate;
}
if (_embeddedMode) {
    document.documentElement.classList.add('embedded');
}
_initTimeline();
doSearch();

window.addEventListener('beforeunload', function() { saveFilters(); });

var _scrollYear = '';
var _lastScrollY = 0;
var _tlSyncPaused = false;
var _modalOpen = false;

function _syncTimelineToPhoto() {
    var p = currentPhotos[_mIdx];
    if (p && p.date) updateTimelinePosition(p.date);
}

function updateTimelinePosition(targetDate) {
    if (!dateData || !dateData.years) return;
    var needle = document.getElementById('tlNeedle');
    if (!needle) return;

    var nearDate;
    if (targetDate) {
        nearDate = targetDate;
    } else {
        var cards = document.querySelectorAll('.card[data-date]');
        if (cards.length === 0) return;

        var vvH = window.visualViewport ? window.visualViewport.height : window.innerHeight;
        var firstVisible = null;
        for (var i = 0; i < cards.length; i++) {
            var rect = cards[i].getBoundingClientRect();
            if (rect.bottom > 0 && rect.top < vvH) {
                firstVisible = cards[i];
                break;
            }
        }
        if (!firstVisible) return;

        nearDate = firstVisible.getAttribute('data-date');
        _firstVisiblePhotoId = firstVisible.getAttribute('data-photo-id') || null;
    }
    if (!nearDate) return;
    _needleDateISO = nearDate;

    updateNeedleFlag(nearDate);

    var newLeft = _dateToX(nearDate);
    needle.style.transition = 'left .4s ease-out';
    needle.style.left = newLeft + 'px';

    if (_tlZoom <= _tlDefaultZoom * 1.5) {
        var nearYear = parseInt(nearDate.substring(0, 4));
        if (nearYear && nearYear !== _scrollYear) {
            _scrollYear = nearYear;
        }
    }
}

window.addEventListener('scroll', function() {
     if (_modalOpen || _tlSyncPaused) return;
     var scrollY = window.scrollY || window.pageYOffset;
     var vvH = window.visualViewport ? window.visualViewport.height : window.innerHeight;
     var docH = document.documentElement.scrollHeight;
     var header = document.getElementById('headerSticky');
     var mmOpen = document.getElementById('mmPanel').classList.contains('open');
     var fsOpen = document.getElementById('filterSheet').classList.contains('open');

     if (!mmOpen && !fsOpen && scrollY > _lastScrollY && scrollY > 100 && (scrollY - _lastScrollY) > 5) {
          header.style.transform = 'translateY(-100%)';
          document.getElementById('timeline').style.top = '0';
      } else if (!mmOpen && !fsOpen && scrollY < _lastScrollY && (_lastScrollY - scrollY) > 10) {
          header.style.transform = 'translateY(0)';
          document.getElementById('timeline').style.top = header.offsetHeight + 'px';
      } else if (scrollY <= 50 || mmOpen || fsOpen) {
          header.style.transform = 'translateY(0)';
          document.getElementById('timeline').style.top = header.offsetHeight + 'px';
      }
     _lastScrollY = scrollY;

     if (!_isLoading) {
         if (_canLoadMore && scrollY + vvH >= docH - 2000) {
             console.log('scroll loadAfter', _lastDate, _isLoading, _canLoadMore);
             loadAfter(_lastDate, _lastPath);
         }
         if (_canLoadPrev && scrollY < 800) {
             console.log('scroll loadBefore', _firstDate, _isLoading, _canLoadPrev);
             loadBefore(_firstDate, _firstPath);
         }
     }

     updateTimelinePosition();
});

window.addEventListener('resize', function() {
    if (_tlCanvas) { _clampTlOffset(); renderTimeline(); if (_needleDateISO) { var n = document.getElementById('tlNeedle'); if (n) { n.style.transition = 'none'; n.style.left = _dateToX(_needleDateISO) + 'px'; } } }
    _positionModalControls();
});

 function openFilterSheet() {
     syncSheetFromBar();
     document.getElementById('filterSheet').classList.add('open');
     document.getElementById('filterSheetOverlay').classList.add('open');
     document.documentElement.classList.add('scroll-lock');
     var header = document.getElementById('headerSticky');
     header.style.transform = 'translateY(0)';
 }
 function closeFilterSheet() {
     document.getElementById('filterSheet').classList.remove('open');
     document.getElementById('filterSheetOverlay').classList.remove('open');
     document.documentElement.classList.remove('scroll-lock');
 }
function syncFilter(mobEl, deskId) {
    document.getElementById(deskId).checked = mobEl.checked;
    updateFilterBadge();
    doSearch();
}
function syncSelect(mobEl, deskId) {
    document.getElementById(deskId).value = mobEl.value;
    doSearch();
}
function syncTypeCheck(mobEl, deskId) {
    document.getElementById(deskId).checked = mobEl.checked;
    updateTypeFilterLabel();
    doSearch();
}
function syncCatCheck(mobEl, deskId) {
    document.getElementById(deskId).checked = mobEl.checked;
    updateCatFilterLabel();
    doSearch();
}
 function syncSheetFromBar() {
     var pairs = [['chkFacesMob','chkFaces'],['chkHasDescMob','chkHasDesc'],['chkIssuesMob','chkIssues'],['chkGpsMob','chkGps'],['chkDeletedMob','chkDeleted']];
     for (var i = 0; i < pairs.length; i++) {
         var mob = document.getElementById(pairs[i][0]);
         var desk = document.getElementById(pairs[i][1]);
         if (mob && desk) mob.checked = desk.checked;
     }
     var sortMob = document.getElementById('sortSelectMob');
     var sortDesk = document.getElementById('sortSelect');
     if (sortMob && sortDesk) sortMob.value = sortDesk.value;
     var catPairs = [
         ['chkCatPhotoMob','chkCatPhoto'],['chkCatScreenshotMob','chkCatScreenshot'],
         ['chkCatDocumentMob','chkCatDocument'],['chkCatMemeMob','chkCatMeme'],
         ['chkCatIconMob','chkCatIcon'],['chkCatOtherMob','chkCatOther']
     ];
     for (var i = 0; i < catPairs.length; i++) {
         var mob = document.getElementById(catPairs[i][0]);
         var desk = document.getElementById(catPairs[i][1]);
         if (mob && desk) mob.checked = desk.checked;
     }
     var fmtPairs = [['chkRawMob','chkRaw'],['chkJpegMob','chkJpeg'],['chkVideoMob','chkVideo']];
     for (var i = 0; i < fmtPairs.length; i++) {
         var mob = document.getElementById(fmtPairs[i][0]);
         var desk = document.getElementById(fmtPairs[i][1]);
         if (mob && desk) mob.checked = desk.checked;
     }
     var modeMob = document.getElementById('searchModeMob');
     var modeDesk = document.getElementById('searchMode');
     if (modeMob && modeDesk) modeMob.value = modeDesk.value;
 }
function updateFilterBadge() {
    var allFmts = document.getElementById('chkRaw').checked && document.getElementById('chkJpeg').checked && document.getElementById('chkVideo').checked;
    var allCats = true;
    var catIds = ['chkCatPhoto','chkCatScreenshot','chkCatDocument','chkCatMeme','chkCatIcon','chkCatOther'];
    for (var i = 0; i < catIds.length; i++) { if (!document.getElementById(catIds[i]).checked) { allCats = false; break; } }
    var any = document.getElementById('chkFaces').checked || document.getElementById('chkHasDesc').checked || document.getElementById('chkIssues').checked || document.getElementById('chkGps').checked || document.getElementById('chkDeleted').checked || !allFmts || !allCats;
    var btn = document.querySelector('.mob-filter-btn');
    if (btn) btn.classList.toggle('has-filters', any);
}
function mobClearFilters() {
     var ids = ['chkFacesMob','chkHasDescMob','chkIssuesMob','chkGpsMob','chkDeletedMob'];
     for (var i = 0; i < ids.length; i++) { var el = document.getElementById(ids[i]); if (el) el.checked = false; }
     var sortMob = document.getElementById('sortSelectMob'); if (sortMob) sortMob.value = 'date_desc';
      var catMobs = ['chkCatPhotoMob','chkCatScreenshotMob','chkCatDocumentMob','chkCatMemeMob','chkCatIconMob','chkCatOtherMob'];
      for (var i = 0; i < catMobs.length; i++) { var el = document.getElementById(catMobs[i]); if (el) el.checked = true; }
      document.getElementById('chkRawMob').checked = true;
      document.getElementById('chkJpegMob').checked = true;
      document.getElementById('chkVideoMob').checked = true;
     var catMobs = ['chkCatPhotoMob','chkCatScreenshotMob','chkCatDocumentMob','chkCatMemeMob','chkCatIconMob','chkCatOtherMob'];
     for (var i = 0; i < catMobs.length; i++) { var el = document.getElementById(catMobs[i]); if (el) el.checked = true; }
     var modeMob = document.getElementById('searchModeMob'); if (modeMob) modeMob.value = 'exact';
     clearFilters();
 }

(function() {
    var modal = document.getElementById('photoModal');
    var lastTap = 0;
    modal.addEventListener('touchend', function(e) {
        if (_mZoom > 1) return;
        var dx = e.changedTouches[0].clientX;
        var dy = e.changedTouches[0].clientY;
        var dt = Date.now();
        if (dt - lastTap < 300) { _scheduleTopbarHide(); }
        lastTap = dt;
    }, { passive: true });
})();

function _isMobile() { return window.innerWidth <= 768; }
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

(function() {
    var dp = document.getElementById('detailPanel');
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
})();

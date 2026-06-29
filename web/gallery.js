var API = '/api';
function videoSrc(p) {
    if (p.media_type === 'video' && p.needs_stream) {
        return API + '/photos/video_stream?path=' + encodeURIComponent(p.photo_id);
    }
    return p.photo_id ? (API + '/photos/?path=' + encodeURIComponent(p.photo_id)) : '';
}

ViewerHooks.onNavBoundary = function(dir, callback) {
    if (dir < 0) {
        loadBefore(_firstDate, _firstPath, function(batch) {
            callback(batch.length);
        });
    } else {
        var prevLen = currentPhotos.length;
        loadAfter(_lastDate, _lastPath, false, false, function() {
            callback(currentPhotos.length - prevLen);
        });
    }
};
ViewerHooks.syncTimeline = function(p) {
    if (typeof _syncTimelineToPhoto === 'function') _syncTimelineToPhoto(p);
};
ViewerHooks.onDelete = function(photoId) { markDeleted(photoId); };
ViewerHooks.onUndelete = function(photoId) { undeletePhoto(photoId); };
ViewerHooks.onClearGps = function(photoId) { clearPhotoGps(photoId); };
ViewerHooks.onAddGps = function(photoId) { addPhotoGps(photoId); };
ViewerHooks.onRotate = function(contentHash, saveAngle) { saveRotate(contentHash, saveAngle); };
ViewerHooks.onClose = function() {
    _modalOpen = false;
    var lastPid = currentPhotos[_mIdx] && currentPhotos[_mIdx].photo_id;
    if (lastPid) {
        var c = document.querySelector('.card[data-photo-id="' + CSS.escape(lastPid) + '"]');
        if (c) c.scrollIntoView({block:'center'});
    }
    if (typeof _embeddedMode !== 'undefined' && _embeddedMode && window.parent) {
        window.parent.postMessage({type: 'closeModal'}, '*');
    }
};

var _videoPreviewTimer = null;
var _videoPreviewEl = null;
function startVideoPreview(card, idx) {
    clearTimeout(_videoPreviewTimer);
    _videoPreviewTimer = setTimeout(function() {
        var p = currentPhotos[idx];
        if (!p || p.media_type !== 'video') return;
        var url = videoSrc(p);
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
var pageSize = 60;
var totalResults = 0;
var activeDate = '';
var activePerson = '';
var allPersonas = [];
var dateData = null;
var MONTH_NAMES = ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
var currentPhotos = [];
var _isLoading = false;
var _canLoadMore = true;
var _canLoadPrev = false;
var _firstDate = null;
var _lastDate = null;
var _firstPath = null;
var _lastPath = null;
var _needleMode = false;
var _filterNeedleDate = null;
var _filterNeedleFrac = 0;
var _tlCanvas = null;
var _tlCtx = null;
var _tlZoom = 0;
var _tlOffsetX = 20;
var _tlPad = 50;
var _tlMinYear = 0;
var _tlMaxYear = 1;
var _tlDefaultZoom = 0;
var _tlMinZoom = 1;
var _tlMaxZoom = 50000;
var _tlIsDragging = false;
var _tlDragStartX = 0;
var _tlDragStartOffset = 0;
var _tlWheelTimer = null;
var _tlPinchDist = 0;
var _tlPinchZoom = 0;
var _tlPinchOff = 0;
var _tlPinchCX = 0;
var _photoTimes = [];
var _photoTimeFracs = [];
var MONTH_SHORT = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];
var _prefetchQueue = [];
var _prefetching = false;
var _PREFETCH_AHEAD = 5;
// scroll sentinel / infinite scroll
var _faceLazyObs = null;
var _faceLoadEnabled = false;
setTimeout(function() { _faceLoadEnabled = true; _observeThumbs(); }, 1500);

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

function esc(s) {
    if (!s) return '';
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

var isSemanticMode = false;

 function onModeChange() {
     var mode = document.getElementById('searchMode').value;
     var input = document.getElementById('searchInput');
     var sr = document.getElementById('sortRelevance');
     var sortSel = document.getElementById('sortSelect');
     var hint = document.getElementById('searchModeHintMob');
     if (mode === 'semantic') {
         input.placeholder = 'Смысловой поиск: опишите что ищете...';
         sr.style.display = '';
         sortSel.onchange = null;
         sortSel.value = 'relevance';
         sortSel.onchange = doSearch;
         if (hint) hint.textContent = 'ИИ ищет по смыслу — можно описать сцену, настроение, время года';
     } else {
          input.placeholder = 'Поиск по описанию, пути или хешу...';
         sr.style.display = 'none';
         sortSel.onchange = null;
         if (sortSel.value === 'relevance') {
             sortSel.value = 'date_desc';
         }
         sortSel.onchange = doSearch;
         if (hint) hint.textContent = 'Поиск по точному совпадению слов в описании и пути файла';
     }
 }

function doSearch() {
    // Запомнить позицию (иглу времени) перед сбросом
    var savedNeedleDate = null;
    if (currentPhotos.length > 0 && !activeDate && !_restoreNeedleDate) {
        var cards = document.querySelectorAll('.card');
        var gridRect = document.getElementById('grid').getBoundingClientRect();
        for (var i = 0; i < cards.length; i++) {
            var rect = cards[i].getBoundingClientRect();
            if (rect.top >= gridRect.top - 10 && rect.bottom <= gridRect.bottom + 10) {
                savedNeedleDate = cards[i].getAttribute('data-date');
                break;
            }
        }
        if (!savedNeedleDate) savedNeedleDate = currentPhotos[0].date || null;
    }

    currentPhotos = [];
    _needleMode = false;
    _canLoadMore = true;
    _canLoadPrev = false;
    _isLoading = false;
    _prefetchQueue = [];
    _prefetching = false;
    _updateSentinel();
    _firstDate = null;
    _lastDate = null;
    _firstPath = null;
    _lastPath = null;
    isSemanticMode = false;
    document.getElementById('grid').innerHTML = '';
    var q = document.getElementById('searchInput').value.trim();
    var mode = document.getElementById('searchMode').value;
    if (_restoreNeedleDate) {
        document.getElementById('searchInput').value = '';
        document.getElementById('searchMode').value = 'exact';
        onModeChange();
        isSemanticMode = false;
    }
    q = document.getElementById('searchInput').value.trim();
    mode = document.getElementById('searchMode').value;
    if (mode === 'semantic' && q) {
        doSemanticSearch(q);
        return;
    }
    var afterDate = activeDate ? activeDate : null;
    saveFilters();
    if (_restoreNeedleDate && !afterDate) {
        var saved = _restoreNeedleDate;
        _needleDateISO = saved;
        _restoreNeedleDate = null;
        _needleMode = true;
        _canLoadPrev = true;
        _updateSentinel();
        var sortSel = document.getElementById('sortSelect');
        if (sortSel && sortSel.value === 'date_desc') sortSel.value = 'date_asc';
        loadAfter(saved, null, true);
    } else if (savedNeedleDate) {
        _canLoadPrev = true;
        _updateSentinel();
        _filterNeedleDate = savedNeedleDate;
        var sortVal = document.getElementById('sortSelect').value;
        if (sortVal === 'date_desc') {
            loadAfter(savedNeedleDate, null, false, true);
        } else {
            loadAfter(savedNeedleDate, null, true);
        }
    } else {
        _restoreNeedleDate = null;
        _canLoadPrev = !!afterDate;
        _updateSentinel();
        if (afterDate) {
            loadAfter(afterDate, null, true, null, function() {
                if (_canLoadPrev && _firstDate && currentPhotos.length > 0) {
                    loadBefore(_firstDate, _firstPath);
                }
            });
        } else {
            loadAfter(afterDate, null, !!afterDate);
        }
    }
}

function getSearchParams() {
    var q = document.getElementById('searchInput').value.trim();
    var sort = document.getElementById('sortSelect').value;
    var facesOnly = document.getElementById('chkFaces').checked;
    var hasDesc = document.getElementById('chkHasDesc').checked;
    var issuesOnly = document.getElementById('chkIssues').checked;
    var gpsOnly = document.getElementById('chkGps').checked;
    var deletedOnly = document.getElementById('chkDeleted').checked;
     var catTypes = [];
     if (document.getElementById('chkCatPhoto').checked) catTypes.push('photo');
     if (document.getElementById('chkCatScreenshot').checked) catTypes.push('screenshot');
     if (document.getElementById('chkCatDocument').checked) catTypes.push('document');
     if (document.getElementById('chkCatMeme').checked) catTypes.push('meme');
     if (document.getElementById('chkCatIcon').checked) catTypes.push('icon');
     if (document.getElementById('chkCatOther').checked) catTypes.push('other');
     var allCatsChecked = catTypes.length === 6;
     var noCatsChecked = catTypes.length === 0;
     var chkRaw = document.getElementById('chkRaw').checked;
     var chkJpeg = document.getElementById('chkJpeg').checked;
     var chkVideo = document.getElementById('chkVideo').checked;
     var allChecked = chkRaw && chkJpeg && chkVideo;
     var noneChecked = !chkRaw && !chkJpeg && !chkVideo;
     var params = 'limit=' + pageSize + '&sort=' + sort;
    if (q) params += '&q=' + encodeURIComponent(q);
    if (activePerson) params += '&person=' + encodeURIComponent(activePerson);
    if (facesOnly) params += '&has_faces=true';
    if (hasDesc) params += '&has_description=true';
    if (issuesOnly) params += '&has_issues=true';
    if (gpsOnly) params += '&has_gps=true';
     if (catTypes.length > 0 && catTypes.length < 6) params += '&photo_type=' + catTypes.join(',');
     if (!noneChecked && !allChecked) {
         if (!chkRaw && chkJpeg && !chkVideo) params += '&file_type=non_raw&media_type=photo';
         else if (chkRaw && !chkJpeg && !chkVideo) params += '&file_type=raw&media_type=photo';
         else if (!chkRaw && !chkJpeg && chkVideo) params += '&media_type=video';
         else if (!chkRaw && chkJpeg && chkVideo) params += '&file_type=non_raw';
         else if (chkRaw && !chkJpeg && chkVideo) params += '&file_type=raw';
         else if (chkRaw && chkJpeg && !chkVideo) params += '&media_type=photo';
     }
     if (noneChecked) params += '&photo_id=none';
    if (deletedOnly) params += '&deleted_only=true';
    return params;
}

function loadAfter(afterDate, afterPath, useDateFrom, useDateBefore, onComplete) {
    if (_isLoading || !_canLoadMore) { if (onComplete) onComplete(); return; }
    _isLoading = true;
    var params = getSearchParams();
    var sortVal = document.getElementById('sortSelect').value;
    var isDesc = sortVal === 'date_desc';
    var urlParams = '';
    if (afterDate) {
        if (useDateFrom) {
            urlParams = '&date_from=' + encodeURIComponent(afterDate);
        } else if (useDateBefore) {
            urlParams = '&date_before=' + encodeURIComponent(afterDate);
        } else {
            if (isDesc) {
                urlParams = '&date_before=' + encodeURIComponent(afterDate);
                if (afterPath) urlParams += '&path_before=' + encodeURIComponent(afterPath);
            } else {
                urlParams = '&date_after=' + encodeURIComponent(afterDate);
                if (afterPath) urlParams += '&path_after=' + encodeURIComponent(afterPath);
            }
        }
    }
    params += urlParams;
    if (currentPhotos.length === 0) document.getElementById('grid').innerHTML = '<div class="loading">Загрузка...</div>';

    var taken = _prefetchQueue.shift();
    if (taken && taken.key === params + '|' + (afterDate||'') + '|' + (afterPath||'') + '|' + (useDateFrom||'')) {
        _applyBatch(taken.data);
        _isLoading = false;
        _fillPrefetch();
        if (onComplete) onComplete();
    } else {
        _prefetchQueue = [];
        _showLoadBar();
        fetch(API + '/photos/search?' + params).then(function(r) { return r.json(); }).then(function(data) {
            _hideLoadBar();
            _applyBatch(data);
            _isLoading = false;
            _fillPrefetch();
            if (onComplete) onComplete();
        }).catch(function(e) {
            _hideLoadBar();
            if (currentPhotos.length === 0) document.getElementById('grid').innerHTML = '<div class="empty">Ошибка: ' + esc(e.message) + '</div>';
            _isLoading = false;
            if (onComplete) onComplete();
        });
    }
}

function _applyBatch(data) {
    totalResults = data.total;
    if (currentPhotos.length === 0) document.getElementById('grid').innerHTML = '';
    if (data.photos.length === 0 && currentPhotos.length === 0) {
        document.getElementById('grid').innerHTML = '<div class="empty">Ничего не найдено</div>';
    }
    var startIdx = currentPhotos.length;
    currentPhotos = currentPhotos.concat(data.photos);
    if (data.photos.length > 0) {
        var lastIdx = data.photos.length - 1;
        _lastDate = data.photos[lastIdx].date || null;
        _lastPath = data.photos[lastIdx].path || null;
        if (!_firstDate) {
            _firstDate = data.photos[0].date || null;
            _firstPath = data.photos[0].path || null;
        }
    }
    if (data.photos.length < pageSize) _canLoadMore = false;
    _updateSentinel();
    appendGrid(data.photos, startIdx);
    updateInfo();
    saveFilters();
     if (startIdx === 0) {
         if (_needleMode) {
              if (_restorePhotoId) {
                  var rid = _restorePhotoId;
                  _restorePhotoId = null;
                  var scrollAttempts = 0;
                  function scrollToPhoto() {
                      var el = document.querySelector('.card[data-photo-id="' + CSS.escape(rid) + '"]');
                      if (el) {
                          el.scrollIntoView({ block: 'start' });
                          if (_openViewerOnLoad) {
                              _openViewerOnLoad = false;
                              var idx = currentPhotos.findIndex(function(p) { return p.photo_id === rid; });
                              if (idx >= 0) setTimeout(function() { Viewer.open(currentPhotos, idx); }, 200);
                          }
                      }
                      scrollAttempts++;
                      if (scrollAttempts < 5) setTimeout(scrollToPhoto, 400);
                  }
                  setTimeout(scrollToPhoto, 300);
              }
             _needleMode = false;
         } else {
             setTimeout(function() { updateTimelinePosition(); }, 100);
         }
          if (_filterNeedleDate) {
              var needleFrac = _filterNeedleFrac;
              _filterNeedleDate = null;
              _filterNeedleFrac = 0;
              var cards = document.querySelectorAll('.card');
              var bestIdx = -1;
              var bestDist = Infinity;
              for (var i = 0; i < currentPhotos.length; i++) {
                  var d = currentPhotos[i].date || '';
                  var df = _dateToFracRaw(d);
                  var dist = Math.abs(df - needleFrac);
                  if (dist < bestDist) { bestDist = dist; bestIdx = i; }
                  if (df > needleFrac + 0.001) break;
              }
              if (bestIdx < 0 && currentPhotos.length > 0) bestIdx = 0;
              if (bestIdx >= 0 && cards[bestIdx]) {
                  cards[bestIdx].scrollIntoView({ block: 'start' });
                  var bp = currentPhotos[bestIdx];
                  if (bp && bp.date) {
                      _needleDateISO = bp.date;
                      var nd = document.getElementById('tlNeedle');
                      if (nd) { nd.style.transition = 'none'; nd.style.left = _dateToX(bp.date) + 'px'; updateNeedleFlag(bp.date); }
                  }
              }
          }
    }
}

function _showLoadBar() {
    var el = document.getElementById('scroll-sentinel');
    if (el) { el.classList.add('loading'); el.classList.remove('end'); }
}

function _hideLoadBar() {
    var el = document.getElementById('scroll-sentinel');
    if (el) el.classList.remove('loading');
}

function _updateSentinel() {
    var el = document.getElementById('scroll-sentinel');
    if (!el) return;
    el.classList.toggle('end', !_canLoadMore);
    var top = document.getElementById('top-sentinel');
    if (top) top.classList.toggle('at-end', !_canLoadPrev);
}

function _showTopLoadBar() {
    var el = document.getElementById('top-sentinel');
    if (el) { el.classList.add('loading'); el.classList.remove('at-end'); }
}

function _hideTopLoadBar() {
    var el = document.getElementById('top-sentinel');
    if (el) el.classList.remove('loading');
}

function _fillPrefetch() {
    if (!_canLoadMore || _prefetching) return;
    var needed = _PREFETCH_AHEAD - _prefetchQueue.length;
    if (needed <= 0) return;
    _prefetching = true;
    var params0 = getSearchParams();
    var chainDate = _lastDate;
    var chainPath = _lastPath;
    if (_prefetchQueue.length > 0) {
        var last = _prefetchQueue[_prefetchQueue.length - 1];
        if (last.data.photos.length > 0) {
            chainDate = last.data.photos[last.data.photos.length - 1].date || null;
            chainPath = last.data.photos[last.data.photos.length - 1].path || null;
        }
    }
    var requests = [];
    var curD = chainDate, curP = chainPath;
    for (var i = 0; i < needed; i++) {
        requests.push({ date: curD, path: curP });
        curD = null; curP = null;
    }
    function doNext(idx) {
        if (idx >= requests.length) { _prefetching = false; return; }
        var req = requests[idx];
        var par = params0;
        var sortVal = document.getElementById('sortSelect').value;
        var isDesc = sortVal === 'date_desc';
        if (req.date) {
            if (isDesc) {
                par += '&date_before=' + encodeURIComponent(req.date);
                if (req.path) par += '&path_before=' + encodeURIComponent(req.path);
            } else {
                par += '&date_after=' + encodeURIComponent(req.date);
                if (req.path) par += '&path_after=' + encodeURIComponent(req.path);
            }
        }
        var key = par + '|' + (req.date || '') + '|' + (req.path || '') + '|';
        fetch(API + '/photos/search?' + par).then(function(r) { return r.json(); }).then(function(data) {
            _prefetchQueue.push({ key: key, data: data });
            if (data.photos.length > 0) {
                for (var j = idx + 1; j < requests.length; j++) {
                    if (!requests[j].date) {
                        requests[j].date = data.photos[data.photos.length - 1].date || null;
                        requests[j].path = data.photos[data.photos.length - 1].path || null;
                    } else break;
                }
            }
            doNext(idx + 1);
        }).catch(function() { doNext(idx + 1); });
    }
    doNext(0);
}

function loadBefore(beforeDate, beforePath, onComplete) {
    if (_isLoading || !_canLoadPrev || !beforeDate) { if (onComplete) onComplete([]); return; }
    _isLoading = true;
    var sortVal = document.getElementById('sortSelect').value;
    var params = getSearchParams();
    var isDesc = sortVal === 'date_desc';
    if (isDesc) {
        // date_desc: "before" means newer photos (above current viewport)
        params = params.replace('sort=' + sortVal, 'sort=date_desc');
        params += '&date_after=' + encodeURIComponent(beforeDate);
        if (beforePath) params += '&path_after=' + encodeURIComponent(beforePath);
    } else {
        // date_asc: "before" means older photos (above current viewport)
        var sortForBefore = sortVal === 'date_asc' ? 'date_desc' : sortVal;
        params = params.replace('sort=' + sortVal, 'sort=' + sortForBefore);
        params += '&date_before=' + encodeURIComponent(beforeDate);
        if (beforePath) params += '&path_before=' + encodeURIComponent(beforePath);
    }

    _showTopLoadBar();
    var oldScrollH = document.documentElement.scrollHeight;
    fetch(API + '/photos/search?' + params).then(function(r) { return r.json(); }).then(function(data) {
        console.log('loadBefore got:', data.photos.length, 'photos');
        _hideTopLoadBar();
        if (data.photos.length > 0) {
            if (!isDesc) data.photos.reverse();
            _firstDate = data.photos[0].date || null;
            _firstPath = data.photos[0].path || null;
            var startIdx = 0;
            var wasEmpty = currentPhotos.length === 0;
            currentPhotos = data.photos.concat(currentPhotos);
            if (wasEmpty) {
                _lastDate = data.photos[data.photos.length - 1].date || null;
                _lastPath = data.photos[data.photos.length - 1].path || null;
            }
            prependGrid(data.photos, startIdx);
        }
        _canLoadPrev = data.photos.length >= pageSize;
        _updateSentinel();
        var newScrollH = document.documentElement.scrollHeight;
        window.scrollBy(0, newScrollH - oldScrollH);
        _lastScrollY = window.scrollY;
        _isLoading = false;
        updateInfo();
        if (onComplete) onComplete(data.photos || []);
    }).catch(function(e) { console.log('loadBefore error:', e); _hideTopLoadBar(); _updateSentinel(); _isLoading = false; if (onComplete) onComplete([]); });
}

function updateInfo() {
    var leftText = 'Найдено: <b>' + totalResults + '</b>';
    var q = document.getElementById('searchInput').value.trim();
    if (q) leftText += ' по запросу «' + esc(q) + '»';
    if (activePerson) leftText += ' персона: ' + esc(activePerson);
    document.getElementById('infoLeft').innerHTML = leftText;
    document.getElementById('infoRight').textContent = currentPhotos.length + ' / ' + totalResults;
}

function doSemanticSearch(q) {
    currentPhotos = [];
    _canLoadMore = false;
    _updateSentinel();
    _isLoading = true;
    isSemanticMode = true;
    document.getElementById('grid').innerHTML = '<div class="loading">Поиск по смыслу... (освобождаем GPU, это может занять до 30с)</div>';
    var url = API + '/photos/semantic_search?q=' + encodeURIComponent(q) + '&limit=100';
    var controller = new AbortController();
    var timeoutId = setTimeout(function() { controller.abort(); }, 90000);
    fetch(url, {signal: controller.signal}).then(function(r) {
        if (!r.ok) {
            return r.text().then(function(t) { throw new Error(t || 'HTTP ' + r.status); });
        }
        return r.json();
    }).then(function(data) {
        clearTimeout(timeoutId);
        totalResults = data.total;
        currentPhotos = data.photos;
        _canLoadMore = false;
        _updateSentinel();
        _isLoading = false;
        document.getElementById('grid').innerHTML = '';
        if (data.photos.length === 0) {
            document.getElementById('grid').innerHTML = '<div class="empty">Ничего не найдено' + (data.error ? ' (' + esc(data.error) + ')' : '') + '</div>';
        }
        appendGrid(data.photos, 0);
        var leftText = 'Смысловой поиск: <b>' + data.total + '</b> по запросу &laquo;' + esc(q) + '&raquo;';
        document.getElementById('infoLeft').innerHTML = leftText;
        document.getElementById('infoRight').textContent = data.total + ' фото';
    }).catch(function(e) {
        clearTimeout(timeoutId);
        document.getElementById('grid').innerHTML = '<div class="empty">Ошибка: ' + esc(e.message || e) + '</div>';
        _updateSentinel();
        _isLoading = false;
    });
}

function _monthKey(dateStr) {
    if (!dateStr || dateStr.length < 7) return null;
    return dateStr.substring(0, 7);
}

function _monthAgoLabel(year, month) {
    var now = new Date();
    var target = new Date(year, month - 1, 1);
    var daysAgo = Math.floor((now - target) / 86400000);
    if (daysAgo <= 0) return '';
    if (daysAgo < 30) {
        function dayWord(n) {
            if (n === 1) return '1 день';
            if (n >= 2 && n <= 4) return n + ' дня';
            return n + ' дней';
        }
        return dayWord(daysAgo) + ' назад';
    }
    var monthsAgo = (now.getFullYear() - year) * 12 + (now.getMonth() + 1 - month);
    if (monthsAgo < 12) {
        function monthWord(n) {
            if (n === 1) return '1 месяц';
            if (n >= 2 && n <= 4) return n + ' месяца';
            return n + ' месяцев';
        }
        return monthWord(monthsAgo) + ' назад';
    }
    var years = Math.floor(monthsAgo / 12);
    var remM = monthsAgo % 12;
    if (remM >= 6) years++;
    function yearWord(n) {
        if (n === 1) return '1 год';
        if (n >= 2 && n <= 4) return n + ' года';
        return n + ' лет';
    }
    return yearWord(years) + ' назад';
}

function _monthDividerHtml(dateStr) {
    var key = _monthKey(dateStr);
    if (!key) return '';
    var y = key.substring(0, 4);
    var m = parseInt(key.substring(5, 7), 10);
    var ago = _monthAgoLabel(parseInt(y, 10), m);
    var agoHtml = ago ? '<span class="md-ago">' + esc(ago) + '</span>' : '';
    return '<div class="month-divider" data-month="' + key + '"><span class="md-year">' + esc(y) + '</span><span class="md-month">' + MONTH_NAMES[m - 1] + '</span>' + agoHtml + '</div>';
}

function appendGrid(photos, startIdx) {
    if (typeof _embeddedMode !== 'undefined' && _embeddedMode) return;
    var grid = document.getElementById('grid');
    var html = '';
    var lastMonth = null;
    var lastCard = grid.querySelector('.card:last-child');
    if (lastCard) lastMonth = lastCard.getAttribute('data-date') ? _monthKey(lastCard.getAttribute('data-date')) : null;
    for (var i = 0; i < photos.length; i++) {
        if (!isSemanticMode) {
            var mk = _monthKey(photos[i].date || '');
            if (mk && mk !== lastMonth) {
                html += _monthDividerHtml(photos[i].date);
                lastMonth = mk;
            }
        }
        html += buildCardHtml(photos[i], startIdx + i);
    }
    grid.insertAdjacentHTML('beforeend', html);
    reindexAll();
    _observeThumbs();
}

function prependGrid(photos, startIdx) {
    var grid = document.getElementById('grid');
    var html = '';
    var lastMonth = null;
    for (var i = 0; i < photos.length; i++) {
        var mk = _monthKey(photos[i].date || '');
        if (mk && mk !== lastMonth) {
            html += _monthDividerHtml(photos[i].date);
            lastMonth = mk;
        }
        html += buildCardHtml(photos[i], startIdx + i);
    }
    grid.insertAdjacentHTML('afterbegin', html);
    reindexAll();
    _observeThumbs();
}

function reindexAll() {
    var cards = document.querySelectorAll('.card');
    var isMobile = _isMobile();
    for (var i = 0; i < cards.length; i++) {
        cards[i].setAttribute('onclick', 'openDetail(' + i + ')');
        var p = currentPhotos[i] || {};
        var isVid = p.media_type === 'video';
        var btn = cards[i].querySelector('.expand-btn');
        if (btn) btn.setAttribute('onclick', 'event.stopPropagation();Viewer.open(currentPhotos,' + i + ')');
        if (isMobile) {
            cards[i].removeAttribute('ondblclick');
        } else {
            cards[i].setAttribute('ondblclick', 'event.stopPropagation();Viewer.open(currentPhotos,' + i + ');toggleFullscreen()');
        }
        if (isVid) {
            cards[i].setAttribute('onmouseenter', 'startVideoPreview(this,' + i + ')');
        } else {
            cards[i].removeAttribute('onmouseenter');
        }
    }
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
    var hasRel = isSemanticMode && p.score !== undefined && p.score !== null;
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
     var html = '<div class="card' + (p.deleted ? ' deleted-card' : '') + '" data-date="' + esc(p.date || '') + '" data-photo-id="' + esc(p.photo_id || '') + '"' + _videoHover + ' onclick="openDetail(' + idx + ')" ondblclick="event.stopPropagation();Viewer.open(currentPhotos,' + idx + ');toggleFullscreen()">';
    html += '<button class="expand-btn" onclick="event.stopPropagation();Viewer.open(currentPhotos,' + idx + ')">' + (p.media_type === 'video' ? '&#9654;' : '&#x2922;') + '</button>';
    var q = document.getElementById('searchInput').value.trim();
    if (q) html += '<button class="goto-btn" onclick="event.stopPropagation();goToTimelineFromCard(' + idx + ')" title="Найти в хронологии">&#x21E1;</button>';
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

function playVideoCard(idx) {
    var p = currentPhotos[idx];
    if (!p) return;
    var url = videoSrc(p);
    var bar = document.getElementById('vidModalBar');
    var txt = formatDate(p.date);
    if (p.camera_make || p.camera_model) txt += ' <span style="color:#6e7681">&bull;</span> ' + esc((p.camera_make || '') + ' ' + (p.camera_model || ''));
    bar.innerHTML = txt;
    var old = document.getElementById('vidModalPlayer');
    old.outerHTML = '<video id="vidModalPlayer" src="' + url + '" controls preload="metadata" onclick="event.stopPropagation()"></video>';
    document.getElementById('vidModal').classList.add('show');
    setTimeout(function(){
        var v = document.getElementById('vidModalPlayer');
        if (v) v.play();
    }, 200);
}
function toggleTypeDropdown(e) {
    e.stopPropagation();
    document.getElementById('typeDropdownMenu').classList.toggle('open');
}
function onTypeFilterChange() {
    updateTypeFilterLabel();
    doSearch();
}
function updateTypeFilterLabel() {
    var r = document.getElementById('chkRaw').checked;
    var j = document.getElementById('chkJpeg').checked;
    var v = document.getElementById('chkVideo').checked;
    var allOn = r && j && v;
    document.getElementById('typeDropdownBtn').classList.toggle('has-filter', !allOn);
}
function updateCatFilterLabel() {
    var cats = ['chkCatPhoto','chkCatScreenshot','chkCatDocument','chkCatMeme','chkCatIcon','chkCatOther'];
    var allOn = true;
    for (var i=0; i<cats.length; i++) {
        if (!document.getElementById(cats[i]).checked) { allOn = false; break; }
    }
    document.getElementById('catDropdownBtn').classList.toggle('has-filter', !allOn);
}
document.addEventListener('click', function(e) {
    var menu = document.getElementById('typeDropdownMenu');
    if (menu && menu.classList.contains('open') && !e.target.closest('.type-dropdown')) {
        menu.classList.remove('open');
    }
});

function toggleCatDropdown(e) {
    e.stopPropagation();
    document.getElementById('catDropdownMenu').classList.toggle('open');
}
function onCatFilterChange() {
    updateCatFilterLabel();
    doSearch();
}

function _initTimeline() {}

function _applyDateData() {
    if (!dateData) return;
    _photoTimes = dateData.photo_times || [];
    _photoTimeFracs = [];
    for (var i = 0; i < _photoTimes.length; i++) {
        _photoTimeFracs.push(_dateToFracRaw(_photoTimes[i]));
    }
    var dr = dateData.date_range || {};
    var minD = dr.min, maxD = dr.max;
    if (!minD || !maxD) {
        var years = dateData.years || {};
        var keys = Object.keys(years).sort();
        for (var i = 0; i < keys.length; i++) {
            if (keys[i] === 'no_date') continue;
            var y = parseInt(keys[i]); if (isNaN(y)) continue;
            var jan1 = y + '-01-01';
            if (!minD || jan1 < minD) minD = jan1;
            if (!maxD || jan1 > maxD) maxD = jan1;
        }
    }
    if (!minD) minD = '2020-01-01';
    if (!maxD) { var _now = new Date(); maxD = _now.getFullYear() + '-12-31'; }
    _tlMinYear = _dateToFracRaw(minD);
    _tlMaxYear = _dateToFracRaw(maxD);
    var span = _tlMaxYear - _tlMinYear;
    if (span < 0.5) { _tlMinYear -= 0.25; _tlMaxYear += 0.25; span = 0.5; }
    _tlCanvas = document.getElementById('tlCanvas');
    _tlCtx = _tlCanvas.getContext('2d');
    var W = document.getElementById('timeline').clientWidth;
    _tlDefaultZoom = (W - 2 * _tlPad) / span;
    _tlMinZoom = Math.max(1, _tlDefaultZoom * 0.5);
    _tlMaxZoom = 365.25 * 24 * 6 / span * _tlDefaultZoom;
    _tlMaxZoom = Math.min(_tlMaxZoom, 365.25 * 24 * 8);
    _tlZoom = _tlDefaultZoom;
    _tlOffsetX = _tlPad;
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem('gallery-filters')); } catch(e) {}
    if (saved && saved.tlZoom) { _tlZoom = saved.tlZoom; _tlOffsetX = saved.tlOffsetX || _tlPad; }
    _clampTlOffset();
    renderTimeline();
    if (_needleDateISO) {
        var nd = document.getElementById('tlNeedle');
        if (nd) { nd.style.transition = 'none'; nd.style.left = _dateToX(_needleDateISO) + 'px'; updateNeedleFlag(_needleDateISO); }
    }
    var tl = document.getElementById('timeline');
    tl.addEventListener('wheel', _tlOnWheel, { passive: false });
    tl.addEventListener('mousedown', _tlOnMouseDown);
    tl.addEventListener('touchstart', _tlOnTouchStart, { passive: false });
    tl.addEventListener('touchmove', _tlOnTouchMove, { passive: false });
    tl.addEventListener('touchend', _tlOnTouchEnd);
}

function _timelineCacheKey() { return 'gallery-dates-v2'; }

function loadTimeline() {
    var cached = null;
    try { cached = JSON.parse(localStorage.getItem(_timelineCacheKey())); } catch(e) {}
    if (cached && cached.data) {
        dateData = cached.data;
        _applyDateData();
    }
    fetch(API + '/photos/dates').then(function(r) { return r.json(); }).then(function(data) {
        dateData = data;
        try { localStorage.setItem(_timelineCacheKey(), JSON.stringify({data: data, ts: Date.now()})); } catch(e) {}
        _applyDateData();
    }).catch(function() {});
}

function _dateToFracRaw(dateStr) {
    if (!dateStr || dateStr.length < 4) return 0;
    var y = parseInt(dateStr.substring(0, 4)) || 0;
    var m = parseInt(dateStr.substring(5, 7)) || 1;
    var d = parseInt(dateStr.substring(8, 10)) || 1;
    var h = parseInt(dateStr.substring(11, 13)) || 0;
    var mn = parseInt(dateStr.substring(14, 16)) || 0;
    return y + (m - 1) / 12 + (d - 1) / 365.25 + (h * 60 + mn) / 1440 / 365.25;
}

function _dateToFrac(dateStr) {
    if (!dateStr || dateStr.length < 4) return _tlMinYear;
    return _dateToFracRaw(dateStr);
}

function _fracToX(frac) { return _tlOffsetX + (frac - _tlMinYear) * _tlZoom; }
function _dateToX(dateStr) { return _fracToX(_dateToFrac(dateStr)); }
function _xToFrac(x) { return _tlMinYear + (x - _tlOffsetX) / _tlZoom; }

function _clampTlOffset() {
    var W = _tlCanvas ? _tlCanvas.clientWidth : 0;
    if (!W) return;
    var dataW = (_tlMaxYear - _tlMinYear) * _tlZoom;
    if (dataW + 2 * _tlPad <= W) {
        _tlOffsetX = (W - dataW) / 2;
    } else {
        _tlOffsetX = Math.max(W - _tlPad - dataW, Math.min(_tlPad, _tlOffsetX));
    }
}

function renderTimeline() {
    var ctx = _tlCtx;
    if (!ctx || !dateData) return;
    var dpr = window.devicePixelRatio || 1;
    var W = _tlCanvas.clientWidth;
    var H = _tlCanvas.clientHeight;
    if (!W || !H) return;
    _tlCanvas.width = W * dpr;
    _tlCanvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    var light = document.body.classList.contains('light-theme');
    var cAxis = light ? '#d0d7de' : '#21262d';
    var cYearTick = light ? '#57606a' : '#484f58';
    var cYearLabel = light ? '#57606a' : '#484f58';
    var cMonTick = light ? '#d0d7de' : '#30363d';
    var cMonLabel = light ? '#57606a' : '#3b424d';
    var cMonNum = light ? '#8b949e' : '#30363d';
    var cDayTick = light ? '#d0d7de' : '#21262d';
    var cDayLabel = light ? '#8b949e' : '#30363d';
    var cHourTick = light ? '#eaeef2' : '#161b22';
    var cHourLabel = light ? '#8b949e' : '#21262d';
    var cDateLabel = light ? '#24292f' : '#484f58';
    var cBar = light ? 'rgba(9,105,218,0.10)' : 'rgba(88,166,255,0.12)';
    var cScale = light ? '#8b949e' : '#30363d';

    var axisY = 24;
    var pxY = _tlZoom;
    var pxM = pxY / 12;
    var pxD = pxY / 365.25;
    var pxH = pxD / 24;

    var months = dateData.months || {};
    var days = dateData.days || {};
    var barTop = 3;
    var barMaxH = 16;

    if (pxD < 3) {
        var maxCnt = 1;
        for (var k in months) if (months[k] > maxCnt) maxCnt = months[k];
        for (var k in months) {
            var my = parseInt(k.substring(0, 4));
            var mm = parseInt(k.substring(5, 7)) - 1;
            if (isNaN(my) || isNaN(mm)) continue;
            var x1 = _fracToX(my + mm / 12);
            var x2 = _fracToX(my + (mm + 1) / 12);
            if (x2 < 0 || x1 > W) continue;
            var bh = Math.round(months[k] / maxCnt * barMaxH);
            ctx.fillStyle = cBar;
            ctx.fillRect(Math.max(0, x1), barTop + barMaxH - bh, Math.min(W, x2) - Math.max(0, x1), bh);
        }
    } else if (pxD < 20) {
        var maxCnt = 1;
        for (var k in days) if (days[k] > maxCnt) maxCnt = days[k];
        var dkeys = Object.keys(days);
        for (var i = 0; i < dkeys.length; i++) {
            var dk = dkeys[i];
            var dy = parseInt(dk.substring(0, 4));
            var dm = parseInt(dk.substring(5, 7)) - 1;
            var dd = parseInt(dk.substring(8, 10)) - 1;
            if (isNaN(dy) || isNaN(dm) || isNaN(dd)) continue;
            var frac1 = dy + dm / 12 + dd / 365.25;
            var frac2 = dy + dm / 12 + (dd + 1) / 365.25;
            var x1 = _fracToX(frac1);
            var x2 = _fracToX(frac2);
            if (x2 < 0 || x1 > W) continue;
            var bh = Math.round(days[dk] / maxCnt * barMaxH);
            ctx.fillStyle = cBar;
            ctx.fillRect(Math.max(0, x1), barTop + barMaxH - bh, Math.max(1, Math.min(W, x2) - Math.max(0, x1)), bh);
        }
    } else if (pxH >= 3 && _photoTimeFracs.length > 0) {
        var dotSize = Math.max(2, Math.min(4, Math.floor(pxH * 0.5)));
        var dotGap = Math.max(1, dotSize);
        var cDot = light ? 'rgba(9,105,218,0.75)' : 'rgba(88,166,255,0.75)';
        var vf0 = _xToFrac(0), vf1 = _xToFrac(W);
        var si = 0;
        while (si < _photoTimeFracs.length && _photoTimeFracs[si] < vf0) si++;
        var lastPx = -999;
        var dotRow = 0;
        for (var pi = si; pi < _photoTimeFracs.length; pi++) {
            if (_photoTimeFracs[pi] > vf1) break;
            var px = Math.floor(_fracToX(_photoTimeFracs[pi]));
            if (px === lastPx) {
                dotRow++;
            } else {
                dotRow = 0;
                lastPx = px;
            }
            var dotY = barTop + dotRow * (dotSize + dotGap);
            if (dotY + dotSize > barTop + barMaxH) { dotRow = 0; dotY = barTop; }
            ctx.fillStyle = cDot;
            ctx.fillRect(px, dotY, dotSize, dotSize);
        }
    } else {
        var sqSize = Math.min(Math.max(Math.floor(pxD * 0.7), 3), 10);
        var gap = Math.max(1, Math.floor(sqSize * 0.15));
        var maxCols = Math.floor(barMaxH / (sqSize + gap));
        if (maxCols < 1) maxCols = 1;
        var cSq = light ? 'rgba(9,105,218,0.55)' : 'rgba(88,166,255,0.55)';
        var cSqFill = light ? 'rgba(9,105,218,0.25)' : 'rgba(88,166,255,0.25)';
        var dkeys = Object.keys(days);
        for (var i = 0; i < dkeys.length; i++) {
            var dk = dkeys[i];
            var dy = parseInt(dk.substring(0, 4));
            var dm = parseInt(dk.substring(5, 7)) - 1;
            var dd = parseInt(dk.substring(8, 10)) - 1;
            if (isNaN(dy) || isNaN(dm) || isNaN(dd)) continue;
            var frac1 = dy + dm / 12 + dd / 365.25;
            var x = _fracToX(frac1);
            if (x < -sqSize || x > W + sqSize) continue;
            var cnt = days[dk];
            var row = 0, col = 0;
            for (var n = 0; n < cnt; n++) {
                var sx = Math.floor(x) + col * (sqSize + gap);
                var sy = barTop + row * (sqSize + gap);
                if (sy + sqSize > barTop + barMaxH + sqSize + gap) break;
                ctx.fillStyle = cSq;
                ctx.fillRect(sx, sy, sqSize, sqSize);
                col++;
                if (col >= maxCols) { col = 0; row++; }
                if (row >= 4) break;
            }
        }
    }

    ctx.strokeStyle = cAxis;
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, axisY); ctx.lineTo(W, axisY); ctx.stroke();

    var f0 = _xToFrac(0), f1 = _xToFrac(W);
    var clipL = _fracToX(_tlMinYear);
    var clipR = _fracToX(_tlMaxYear);

    ctx.save();
    ctx.beginPath();
    ctx.rect(Math.max(0, clipL), 0, Math.min(W, clipR) - Math.max(0, clipL), H);
    ctx.clip();

    if (pxY >= 5) {
        var y0 = Math.floor(f0) - 1, y1 = Math.ceil(f1) + 1;
        for (var y = y0; y <= y1; y++) {
            var x = _fracToX(y);
            if (x < -50 || x > W + 50) continue;
            ctx.strokeStyle = cYearTick;
            ctx.lineWidth = 1.5;
            ctx.beginPath(); ctx.moveTo(x, axisY); ctx.lineTo(x, axisY + (pxY >= 20 ? 8 : 4)); ctx.stroke();
            if (pxY >= 20) {
                ctx.fillStyle = cYearLabel;
                ctx.font = (pxY >= 50 ? '11' : '10') + 'px monospace';
                ctx.textAlign = 'center';
                ctx.fillText(y.toString(), x, axisY - 12);
            }
        }
    }

    if (pxM >= 3) {
        var y0 = Math.floor(f0) - 1, y1 = Math.ceil(f1) + 1;
        for (var y = y0; y <= y1; y++) {
            for (var m = 1; m <= 12; m++) {
                if (m === 1 && pxY >= 8) continue;
                var x = _fracToX(y + (m - 1) / 12);
                if (x < -10 || x > W + 10) continue;
                ctx.strokeStyle = cMonTick;
                ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(x, axisY); ctx.lineTo(x, axisY + 4); ctx.stroke();
                if (pxM >= 30) {
                    ctx.fillStyle = cMonLabel; ctx.font = '10px monospace'; ctx.textAlign = 'center';
                    ctx.fillText(MONTH_SHORT[m - 1], x, axisY - 12);
                } else if (pxM >= 12) {
                    ctx.fillStyle = cMonNum; ctx.font = '9px monospace'; ctx.textAlign = 'center';
                    ctx.fillText(m.toString(), x, axisY - 10);
                }
            }
        }
        if (pxM >= 12 && pxY < 50) {
            for (var y = y0; y <= y1; y++) {
                var x = _fracToX(y);
                if (x < -30 || x > W + 30) continue;
                ctx.fillStyle = cDateLabel; ctx.font = '11px monospace'; ctx.textAlign = 'left';
                ctx.fillText(y.toString(), x + 3, axisY - 12);
            }
        }
    }

    if (pxD >= 3) {
        var y0 = Math.floor(f0) - 1, y1 = Math.ceil(f1) + 1;
        for (var y = y0; y <= y1; y++) {
            for (var m = 0; m < 12; m++) {
                var daysInM = new Date(y, m + 1, 0).getDate();
                for (var d = 1; d <= daysInM; d++) {
                    var frac = y + m / 12 + (d - 1) / 365.25;
                    var x = _fracToX(frac);
                    if (x < -5 || x > W + 5) continue;
                    ctx.strokeStyle = cDayTick; ctx.lineWidth = 1;
                    ctx.beginPath(); ctx.moveTo(x, axisY); ctx.lineTo(x, axisY + 3); ctx.stroke();
                    var step = pxD >= 30 ? 1 : (pxD >= 15 ? 2 : 5);
                    if (pxD >= 15 && d % step === 0) {
                        ctx.fillStyle = cDayLabel; ctx.font = '9px monospace'; ctx.textAlign = 'center';
                        ctx.fillText(d.toString(), x, axisY - 10);
                    }
                }
            }
        }
        if (pxD >= 10 && pxM < 30) {
            for (var y = y0; y <= y1; y++) {
                for (var m = 0; m < 12; m++) {
                    var x = _fracToX(y + m / 12);
                    if (x < -40 || x > W + 40) continue;
                    ctx.fillStyle = cDateLabel; ctx.font = '10px monospace'; ctx.textAlign = 'left';
                    ctx.fillText(MONTH_SHORT[m] + ' ' + y, x + 2, axisY - 12);
                }
            }
        }
    }

    if (pxH >= 2) {
        var y0 = Math.floor(f0) - 1, y1 = Math.ceil(f1) + 1;
        for (var y = y0; y <= y1; y++) {
            for (var m = 0; m < 12; m++) {
                var daysInM = new Date(y, m + 1, 0).getDate();
                for (var d = 1; d <= daysInM; d++) {
                    for (var h = 0; h < 24; h++) {
                        if (h === 0 && pxD >= 5) continue;
                        var frac = y + m / 12 + (d - 1) / 365.25 + h / 24 / 365.25;
                        var x = _fracToX(frac);
                        if (x < -3 || x > W + 3) continue;
                        ctx.strokeStyle = cHourTick; ctx.lineWidth = 1;
                        ctx.beginPath(); ctx.moveTo(x, axisY); ctx.lineTo(x, axisY + 2); ctx.stroke();
                        var step = pxH >= 20 ? 1 : (pxH >= 10 ? 2 : 6);
                        if (pxH >= 10 && h % step === 0) {
                            ctx.fillStyle = cHourLabel; ctx.font = '8px monospace'; ctx.textAlign = 'center';
                            ctx.fillText(h + ':00', x, axisY - 8);
                        }
                    }
                }
            }
        }
        if (pxH >= 5 && pxD < 15) {
            for (var y = y0; y <= y1; y++) {
                for (var m = 0; m < 12; m++) {
                    var daysInM = new Date(y, m + 1, 0).getDate();
                    for (var d = 1; d <= daysInM; d++) {
                        var frac = y + m / 12 + (d - 1) / 365.25;
                        var x = _fracToX(frac);
                        if (x < -40 || x > W + 40) continue;
                        ctx.fillStyle = cDateLabel; ctx.font = '10px monospace'; ctx.textAlign = 'left';
                        ctx.fillText(('0' + d).slice(-2) + '.' + ('0' + (m + 1)).slice(-2) + '.' + y, x + 2, axisY - 12);
                    }
                }
            }
        }
    }

    var label = pxD >= 20 ? 'Фото' : pxH >= 10 ? 'Часы' : pxD >= 10 ? 'Дни' : pxM >= 12 ? 'Месяцы' : 'Года';
    ctx.restore();

    var clipLx = Math.max(0, _fracToX(_tlMinYear));
    var clipRx = Math.min(W, _fracToX(_tlMaxYear));
    if (clipLx > 2) {
        ctx.fillStyle = light ? 'rgba(88,166,255,0.08)' : 'rgba(88,166,255,0.06)';
        ctx.fillRect(0, 0, clipLx, H);
        ctx.fillStyle = light ? '#57606a' : '#3b424d';
        ctx.font = '9px monospace'; ctx.textAlign = 'center';
        ctx.fillText('◀', clipLx / 2, axisY + 16);
        ctx.fillText('старые', clipLx / 2, axisY + 28);
    }
    if (clipRx < W - 2) {
        ctx.fillStyle = light ? 'rgba(88,166,255,0.08)' : 'rgba(88,166,255,0.06)';
        ctx.fillRect(clipRx, 0, W - clipRx, H);
        ctx.fillStyle = light ? '#57606a' : '#3b424d';
        ctx.font = '9px monospace'; ctx.textAlign = 'center';
        ctx.fillText('▶', (clipRx + W) / 2, axisY + 16);
        ctx.fillText('свежие', (clipRx + W) / 2, axisY + 28);
    }

    ctx.fillStyle = cScale; ctx.font = '9px monospace'; ctx.textAlign = 'right';
    ctx.fillText(label, W - 6, 10);
}

function _tlOnWheel(e) {
    e.preventDefault();
    var delta = e.deltaY > 0 ? -1 : 1;
    var factor = delta > 0 ? 1.3 : 1 / 1.3;
    if (e.ctrlKey || e.metaKey) factor = delta > 0 ? 2 : 0.5;
    var tlRect = document.getElementById('timeline').getBoundingClientRect();
    var mouseX = e.clientX - tlRect.left;
    var mouseFrac = _xToFrac(mouseX);
    _tlZoom *= factor;
    _tlZoom = Math.max(_tlMinZoom, Math.min(_tlMaxZoom, _tlZoom));
    _tlOffsetX = mouseX - (mouseFrac - _tlMinYear) * _tlZoom;
    _clampTlOffset();
    renderTimeline();
    if (_needleDateISO) {
        var needle = document.getElementById('tlNeedle');
        if (needle) { needle.style.transition = 'none'; needle.style.left = _dateToX(_needleDateISO) + 'px'; }
    }
    clearTimeout(_tlWheelTimer);
    _tlWheelTimer = setTimeout(function() { saveFilters(); }, 500);
}

function _tlOnMouseDown(e) {
    if (e.button !== 0) return;
    _tlIsDragging = true;
    _tlDragStartX = e.clientX;
    _tlDragStartOffset = _tlOffsetX;
    document.getElementById('timeline').classList.add('dragging');
    e.preventDefault();
    document.addEventListener('mousemove', _tlOnMouseMove);
    document.addEventListener('mouseup', _tlOnMouseUp);
}

function _tlOnMouseMove(e) {
    if (!_tlIsDragging) return;
    _tlOffsetX = _tlDragStartOffset + (e.clientX - _tlDragStartX);
    _clampTlOffset();
    renderTimeline();
    if (_needleDateISO) {
        var needle = document.getElementById('tlNeedle');
        if (needle) { needle.style.transition = 'none'; needle.style.left = _dateToX(_needleDateISO) + 'px'; }
    }
}

function _tlOnMouseUp(e) {
    document.removeEventListener('mousemove', _tlOnMouseMove);
    document.removeEventListener('mouseup', _tlOnMouseUp);
    document.getElementById('timeline').classList.remove('dragging');
    var dx = Math.abs(e.clientX - _tlDragStartX);
    _tlIsDragging = false;
    if (dx < 5) {
        var tlRect = document.getElementById('timeline').getBoundingClientRect();
        _tlNavigateAt(e.clientX - tlRect.left);
    }
    saveFilters();
}

function _tlOnTouchStart(e) {
    if (e.touches.length === 1) {
        _tlIsDragging = true;
        _tlDragStartX = e.touches[0].clientX;
        _tlDragStartOffset = _tlOffsetX;
    } else if (e.touches.length === 2) {
        _tlIsDragging = false;
        _tlPinchDist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
        _tlPinchZoom = _tlZoom;
        _tlPinchOff = _tlOffsetX;
        var tlRect = document.getElementById('timeline').getBoundingClientRect();
        _tlPinchCX = (e.touches[0].clientX + e.touches[1].clientX) / 2 - tlRect.left;
    }
    e.preventDefault();
}

function _tlOnTouchMove(e) {
    if (e.touches.length === 1 && _tlIsDragging) {
        _tlOffsetX = _tlDragStartOffset + (e.touches[0].clientX - _tlDragStartX);
        _clampTlOffset();
        renderTimeline();
        if (_needleDateISO) {
            var needle = document.getElementById('tlNeedle');
            if (needle) { needle.style.transition = 'none'; needle.style.left = _dateToX(_needleDateISO) + 'px'; }
        }
    } else if (e.touches.length === 2) {
        var dist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
        var factor = dist / _tlPinchDist;
        var mouseFrac = _tlMinYear + (_tlPinchCX - _tlPinchOff) / _tlPinchZoom;
        _tlZoom = _tlPinchZoom * factor;
        _tlZoom = Math.max(_tlMinZoom, Math.min(_tlMaxZoom, _tlZoom));
        _tlOffsetX = _tlPinchCX - (mouseFrac - _tlMinYear) * _tlZoom;
        _clampTlOffset();
        renderTimeline();
        if (_needleDateISO) {
            var needle = document.getElementById('tlNeedle');
            if (needle) { needle.style.transition = 'none'; needle.style.left = _dateToX(_needleDateISO) + 'px'; }
        }
    }
    e.preventDefault();
}

function _tlOnTouchEnd(e) {
    if (e.touches.length === 0 && _tlIsDragging) {
        var dx = Math.abs((e.changedTouches[0] ? e.changedTouches[0].clientX : _tlDragStartX) - _tlDragStartX);
        _tlIsDragging = false;
        if (dx < 5) {
            var tlRect = document.getElementById('timeline').getBoundingClientRect();
            _tlNavigateAt((e.changedTouches[0] ? e.changedTouches[0].clientX : _tlDragStartX) - tlRect.left);
        }
        saveFilters();
    }
}

function _tlNavigateAt(clickX) {
    var clickFrac = _xToFrac(clickX);
    var needleX = clickX;
    var navDate = null;

    var dataL = _fracToX(_tlMinYear);
    var dataR = _fracToX(_tlMaxYear);

    if (_photoTimeFracs.length > 0) {
        if (clickX <= dataL) {
            navDate = _photoTimes[0];
            needleX = _fracToX(_photoTimeFracs[0]);
        } else if (clickX >= dataR) {
            var last = _photoTimeFracs.length - 1;
            navDate = _photoTimes[last];
            needleX = _fracToX(_photoTimeFracs[last]);
        } else {
            var lo = 0, hi = _photoTimeFracs.length - 1;
            while (lo <= hi) {
                var mid = (lo + hi) >> 1;
                if (_photoTimeFracs[mid] < clickFrac) lo = mid + 1;
                else hi = mid - 1;
            }
            var bestDist = Infinity, bestIdx = -1;
            for (var c = Math.max(0, lo - 5); c <= Math.min(_photoTimeFracs.length - 1, lo + 5); c++) {
                var dist = Math.abs(_photoTimeFracs[c] - clickFrac);
                if (dist < bestDist) { bestDist = dist; bestIdx = c; }
            }
            if (bestIdx >= 0) {
                navDate = _photoTimes[bestIdx];
                needleX = _fracToX(_photoTimeFracs[bestIdx]);
            }
        }
    }

    if (!navDate) {
        navDate = fracToISO(clickFrac);
    }

    var isLeftEdge = clickX <= dataL;
    var isRightEdge = clickX >= dataR;

    var needle = document.getElementById('tlNeedle');
    if (needle) { needle.style.transition = 'none'; needle.style.left = needleX + 'px'; updateNeedleFlag(navDate); }
    activeDate = navDate;
    _needleMode = true;
    currentPhotos = [];
    _isLoading = false;
    _prefetchQueue = [];
    _prefetching = false;
    _firstDate = null;
    _lastDate = null;
    _firstPath = null;
    _lastPath = null;
    document.getElementById('grid').innerHTML = '';
    var sortSel = document.getElementById('sortSelect');
    var sortMob = document.getElementById('sortSelectMob');
    if (sortSel) sortSel.value = 'date_asc';
    if (sortMob) sortMob.value = 'date_asc';
    _filterNeedleDate = navDate;
    _filterNeedleFrac = _dateToFracRaw(navDate);
    saveFilters();
    _tlMonthFrom = null;
    _tlMonthTo = null;

    if (isRightEdge) {
        _canLoadMore = false;
        _canLoadPrev = true;
        _isLoading = true;
        _updateSentinel();
        var params = getSearchParams();
        params = params.replace('sort=date_asc', 'sort=date_desc');
        _showLoadBar();
        fetch(API + '/photos/search?' + params).then(function(r) { return r.json(); }).then(function(data) {
            _hideLoadBar();
            data.photos.reverse();
            totalResults = data.total;
            currentPhotos = data.photos;
            if (data.photos.length > 0) {
                _firstDate = data.photos[0].date || null;
                _firstPath = data.photos[0].path || null;
                _lastDate = data.photos[data.photos.length - 1].date || null;
                _lastPath = data.photos[data.photos.length - 1].path || null;
            }
            _canLoadPrev = data.photos.length >= pageSize;
            _canLoadMore = false;
            _updateSentinel();
            appendGrid(data.photos, 0);
            updateInfo();
            _isLoading = false;
            _needleMode = false;
            setTimeout(function() {
                window.scrollTo(0, document.documentElement.scrollHeight);
                _lastScrollY = window.scrollY;
                updateTimelinePosition();
            }, 100);
        }).catch(function(e) {
            _hideLoadBar();
            _isLoading = false;
            if (currentPhotos.length === 0) document.getElementById('grid').innerHTML = '<div class="empty">Ошибка: ' + esc(e.message) + '</div>';
        });
    } else if (isLeftEdge) {
        _canLoadMore = true;
        _canLoadPrev = false;
        _updateSentinel();
        loadAfter(null, null);
    } else {
        _canLoadMore = true;
        _canLoadPrev = true;
        _updateSentinel();
        loadAfter(navDate, null, true, null, function() {
            if (_canLoadPrev && _firstDate && currentPhotos.length > 0) {
                loadBefore(_firstDate, _firstPath);
            }
        });
    }
}
function fracToISO(frac) {
    var y = Math.floor(frac);
    var rest = frac - y;
    if (rest < 0) rest = 0;
    var dayOfYear = Math.floor(rest * 365.25);
    var hourFrac = (rest * 365.25 - dayOfYear) * 24;
    var hour = Math.floor(hourFrac);
    var minute = Math.floor((hourFrac - hour) * 60);
    var d = new Date(y, 0, 1 + dayOfYear);
    var realY = d.getFullYear();
    var mm = ('0' + (d.getMonth() + 1)).slice(-2);
    var dd = ('0' + d.getDate()).slice(-2);
    var result = realY + '-' + mm + '-' + dd;
    if (hour > 0 || minute > 0 || _tlZoom > 5000) result += ' ' + ('0' + hour).slice(-2) + ':' + ('0' + minute).slice(-2);
    return result;
}


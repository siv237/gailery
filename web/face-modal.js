/* ===== Gailery Face Modal — редактор персоны по клику на лицо =====
   Подключается на любой странице где используется Viewer.
   Viewer вызывает _vFaceClick(personaId, faceId) → openFaceModal.

   API:
     openFaceModal(personaId, faceId)  — открыть редактор
     closeFaceModal()                 — закрыть

   Хук:
     FaceModalHooks.onSaved(personaId, name) — после сохранения (обновить карточки)
===== */

var FaceModalHooks = FaceModalHooks || {};

var _fmHTML = `
<div class="face-modal" id="faceModal" onclick="closeFaceModal()">
    <div class="fm-inner" onclick="event.stopPropagation()">
        <div class="fm-left">
            <img class="face-ctx" id="fmImg" src="">
        </div>
        <div class="fm-right">
            <h2 id="fmTitle">Персона</h2>
            <div class="cluster-info" id="fmClusterInfo"></div>
            <label>ФИО / Имя</label>
            <div class="ac-wrap">
                <input id="fmName" autocomplete="off" oninput="fmAcSearch()" onfocus="fmAcSearch()" onblur="fmAcHideDelayed()">
                <div class="ac-list" id="fmAcList"></div>
            </div>
            <label>Комментарий (кто это, родство, заметки)</label>
            <textarea id="fmComment" placeholder="Мама, бабушка, друг семьи..." style="height:60px"></textarea>
            <div id="fmRelatedBlock" class="related" style="display:none">
                <div class="related-title">Кластера с этим именем:</div>
                <div class="related-grid" id="fmRelatedGrid"></div>
            </div>
            <div class="btn-row">
                <button class="btn-save" onclick="fmSave()">Сохранить</button>
                <button class="btn-cancel" onclick="closeFaceModal()">Закрыть</button>
            </div>
            <div class="saved" id="fmSaved">Сохранено!</div>
        </div>
    </div>
</div>
<div class="rename-dialog" id="renameDialog">
    <div class="rd-box">
        <p id="rdText"></p>
        <div class="rd-btns">
            <button class="rd-all" onclick="fmDoSaveAll()">Ко всем кластерам</button>
            <button class="rd-one" onclick="fmDoSaveOne()">Только этот</button>
            <button class="rd-abort" onclick="fmDoSaveAbort()">Отмена</button>
        </div>
    </div>
</div>
`;

(function() {
    var div = document.createElement('div');
    div.innerHTML = _fmHTML;
    while (div.firstChild) document.body.appendChild(div.firstChild);
})();

var fmCurrentPid = null;
var fmOriginalName = '';
var fmOriginalComment = '';
var fmRelatedClusters = [];
var fmAcNames = [];

function _fmAPI() {
    return (typeof API !== 'undefined') ? API : '/api';
}

function _fmEsc(s) {
    if (typeof esc === 'function') return esc(s);
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function openFaceModal(personaId, faceId) {
    fmCurrentPid = personaId;
    document.getElementById('fmImg').src = _fmAPI() + '/photos/face_context/' + faceId;
    document.getElementById('fmTitle').textContent = personaId;
    document.getElementById('fmClusterInfo').textContent = 'Кластер: ' + personaId;
    document.getElementById('fmName').value = '';
    document.getElementById('fmComment').value = '';
    document.getElementById('fmSaved').style.display = 'none';
    document.getElementById('fmRelatedBlock').style.display = 'none';
    document.getElementById('fmRelatedGrid').innerHTML = '';
    fmRelatedClusters = [];

    fetch(_fmAPI() + '/persons/' + personaId).then(function(r) { return r.json(); }).then(function(p) {
        fmOriginalName = p.display_name || '';
        fmOriginalComment = p.comment || '';
        document.getElementById('fmName').value = fmOriginalName;
        document.getElementById('fmComment').value = fmOriginalComment;
        document.getElementById('fmTitle').textContent = p.display_name || p.name || personaId;
        document.getElementById('fmClusterInfo').textContent = 'Кластер: ' + personaId + ' | Лиц: ' + (p.face_count || 0);
        if (p.display_name) fmLoadRelated(personaId, p.display_name);
    });

    document.getElementById('faceModal').classList.add('show');
    if (typeof closeDetail === 'function') closeDetail();
    fmLoadAcNames();
}

function fmLoadRelated(currentId, name) {
    fetch(_fmAPI() + '/persons/by_name/' + encodeURIComponent(name)).then(function(r) { return r.json(); }).then(function(list) {
        fmRelatedClusters = list;
        if (list.length <= 1) { document.getElementById('fmRelatedBlock').style.display = 'none'; return; }
        var html = '';
        for (var i = 0; i < list.length; i++) {
            var c = list[i];
            var isCurrent = c.persona_id === currentId;
            var faceUrl = c.face_id ? (_fmAPI() + '/photos/face/' + c.face_id + '?margin=0.5') : '';
            var cls = isCurrent ? 'rel-chip current' : 'rel-chip';
            html += '<div class="' + cls + '" onclick="openFaceModal(\'' + _fmEsc(c.persona_id) + '\',\'' + _fmEsc(c.face_id || '') + '\')">';
            if (faceUrl) html += '<img src="' + faceUrl + '" loading="lazy">';
            html += '<div class="lbl">' + _fmEsc(c.persona_id) + ' (' + c.face_count + 'л)</div></div>';
        }
        document.getElementById('fmRelatedGrid').innerHTML = html;
        document.getElementById('fmRelatedBlock').style.display = 'block';
    });
}

function closeFaceModal() {
    document.getElementById('faceModal').classList.remove('show');
    fmCurrentPid = null;
}

function fmLoadAcNames() {
    fetch(_fmAPI() + '/persons/names').then(function(r) { return r.json(); }).then(function(n) { fmAcNames = n; });
}

function fmAcSearch() {
    var q = document.getElementById('fmName').value.toLowerCase();
    var list = document.getElementById('fmAcList');
    if (!q) { list.classList.remove('show'); list.innerHTML = ''; return; }
    var matches = fmAcNames.filter(function(n) { return n.toLowerCase().indexOf(q) >= 0; }).slice(0, 10);
    if (!matches.length) { list.classList.remove('show'); return; }
    var html = '';
    for (var i = 0; i < matches.length; i++) {
        html += '<div class="ac-item" onmousedown="fmAcSelect(\'' + _fmEsc(matches[i]) + '\')">' + _fmEsc(matches[i]) + '</div>';
    }
    list.innerHTML = html;
    list.classList.add('show');
}

function fmAcHideDelayed() {
    setTimeout(function() { document.getElementById('fmAcList').classList.remove('show'); }, 200);
}

function fmAcSelect(name) {
    document.getElementById('fmName').value = name;
    document.getElementById('fmAcList').classList.remove('show');
}

function fmSave() {
    if (!fmCurrentPid) return;
    var newName = document.getElementById('fmName').value.trim();
    var newComment = document.getElementById('fmComment').value.trim();
    if (fmOriginalName && fmOriginalName !== newName && fmRelatedClusters.length > 1) {
        document.getElementById('rdText').textContent = 'Имя меняется с "' + fmOriginalName + '" на "' + newName + '". Применить:';
        document.getElementById('renameDialog').classList.add('show');
        return;
    }
    fmDoSaveOne();
}

function fmDoSaveOne() {
    document.getElementById('renameDialog').classList.remove('show');
    if (!fmCurrentPid) return;
    var name = document.getElementById('fmName').value.trim();
    var comment = document.getElementById('fmComment').value.trim();
    fetch(_fmAPI() + '/persons/' + fmCurrentPid, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: name || null, comment: comment || null, clear_display_name: !name, clear_comment: !comment }),
    }).then(function(r) { return r.json(); }).then(function() {
        document.getElementById('fmSaved').style.display = 'block';
        setTimeout(function() { document.getElementById('fmSaved').style.display = 'none'; }, 2000);
        if (FaceModalHooks.onSaved) FaceModalHooks.onSaved(fmCurrentPid, name);
    });
}

function fmDoSaveAll() {
    document.getElementById('renameDialog').classList.remove('show');
    if (!fmCurrentPid) return;
    var name = document.getElementById('fmName').value.trim();
    var comment = document.getElementById('fmComment').value.trim();
    fetch(_fmAPI() + '/persons/batch/by_name?old_name=' + encodeURIComponent(fmOriginalName), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: name || null, comment: comment || null, clear_display_name: !name, clear_comment: !comment }),
    }).then(function(r) { return r.json(); }).then(function() {
        document.getElementById('fmSaved').style.display = 'block';
        setTimeout(function() { document.getElementById('fmSaved').style.display = 'none'; }, 2000);
        if (FaceModalHooks.onSaved) FaceModalHooks.onSaved(fmCurrentPid, name);
    });
}

function fmDoSaveAbort() {
    document.getElementById('renameDialog').classList.remove('show');
}

// Bridge: Viewer._vFaceClick → openFaceModal
if (typeof ViewerHooks !== 'undefined') {
    ViewerHooks.onFaceClick = function(personaId, faceId) { openFaceModal(personaId, faceId); };
}

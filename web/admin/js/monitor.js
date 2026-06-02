var MonP = {photos:[], _idx:-1, _timer:null, _expanded:null};

Admin.registerBlock('monitor_feed', 'Монитор фото', '📷', function(cid){
    MonP.loadInto(cid, 5);
});

Admin.on('navigate', function(page) {
    if (page === 'monitor') {
        MonP.init();
    } else {
        MonP.stop();
    }
});

MonP.loadInto = function(containerId, limit) {
    var el = Admin.$(containerId);
    if (!el) return;
    el.innerHTML = '<div class="c-dim" style="padding:20px 0;text-align:center;font-size:12px">Загрузка…</div>';
    Admin.ajax('/api/photos/monitor_feed?limit=' + (limit || 100), function(d) {
        MonP.photos = d.changes || [];
        MonP.renderFeedInto(containerId, limit || 100);
        var t = Admin.$('monpTime');
        if (t) t.textContent = new Date().toLocaleTimeString();
    }, function(e) {
        el.innerHTML = '<div class="c-dim" style="padding:20px 0;text-align:center;font-size:12px">Ошибка: '+Admin.esc(e.message||'?')+'</div>';
    });
};

MonP.renderFeedInto = function(containerId, limit) {
    var el = Admin.$(containerId);
    if (!el) return;
    var photos = MonP.photos;
    if (!photos.length) {
        el.innerHTML = '<div class="c-dim" style="padding:20px 0;text-align:center;font-size:12px">Нет фото</div>';
        return;
    }
    var h = '';
    for (var i = 0; i < photos.length; i++) {
        h += MonP.renderCard(photos[i], i, containerId, limit <= 10);
    }
    if (limit <= 10) {
        h += '<div style="text-align:center;padding:6px 0"><a href="#" onclick="Admin.navigate(\'monitor\');return false" style="color:#58a6ff;font-size:12px">Все фото →</a></div>';
    }
    el.innerHTML = h;
};

MonP.changeAction = function(p) {
    var field = p.field || '';
    var map = {
        'description': 'описание',
        'rich_description': 'обогащение',
        'faces_present': 'поиск лиц',
        'exif_raw': 'EXIF',
        'gps_lat': 'GPS',
        'gps_lon': 'GPS',
        'camera_make': 'камера',
        'camera_model': 'модель камеры',
        'photo_type': 'тип фото',
        'has_issues': 'проверка',
        'media_type': 'медиа',
        'img_width': 'размер',
        'img_height': 'размер',
        'duration_seconds': 'длительность',
        'date': 'дата',
        'date_conflict': 'дата',
        'persona_update': 'персона',
        'deleted': 'удаление',
    };
    return map[field] || field || 'изменение';
};

MonP.changeResult = function(p) {
    var field = p.field || '';
    var value = p.value || '';
    if (field === 'faces_present') {
        if (value === '1' || value === 'true') return 'лица найдены';
        return 'лиц не найдено';
    }
    if (field === 'description' || field === 'rich_description') {
        if (!value) return 'обновлено';
        return value.length > 50 ? value.substring(0, 50) + '…' : value;
    }
    if (field === 'exif_raw') return 'извлечён';
    if (field === 'gps_lat' || field === 'gps_lon') return value ? ('координаты ' + value) : 'обнаружен';
    if (field === 'camera_make' || field === 'camera_model') return value || 'обнаружена';
    if (field === 'photo_type') return value || 'определён';
    if (field === 'has_issues') return value === '1' || value === 'true' ? 'найдена проблема' : 'ok';
    if (field === 'media_type') return value || 'определён';
    if (field === 'img_width' || field === 'img_height') return 'обновлено';
    if (field === 'duration_seconds') return value ? (value + ' с') : 'обновлено';
    if (field === 'date') return value || 'обновлена';
    if (field === 'date_conflict') return 'конфликт дат';
    if (field === 'persona_update') return value ? (value.substring(0, 30)) : 'обновлено';
    if (field === 'deleted') return value === '1' || value === 'true' ? 'удалено' : 'восстановлено';
    return value || 'обновлено';
};

MonP.changeLabel = function(p) {
    return MonP.changeAction(p) + ' — ' + MonP.changeResult(p);
};

MonP.init = function() {
    var el = Admin.$('page-monitor');
    if (!el) return;
    if (!el.dataset.built) {
        el.innerHTML =
            '<h2 class="page-h2">📷 Монитор фото</h2>'+
            '<div class="monp-status" id="monpStatus"></div>'+
            '<div class="monp-toolbar" id="monpToolbar">'+
            '<select id="monpSort" onchange="MonP.loadInto(\'monpFeed\',100)">'+
            '<option value="date_desc">Сначала новые</option>'+
            '<option value="date_asc">Сначала старые</option>'+
            '</select>'+
            '<button class="btn" onclick="MonP.loadInto(\'monpFeed\',100)">Обновить</button>'+
            '<span class="c-dim" style="font-size:11px" id="monpTime"></span>'+
            '</div>'+
            '<div class="monp-feed" id="monpFeed"></div>'+
            '<div class="monp-modal-overlay" id="monpModal" onclick="MonP.closeModal()">'+
            '<div class="monp-modal-box" onclick="event.stopPropagation()">'+
            '<div class="monp-modal-head"><h3 id="monpModalTitle"></h3><button class="monp-modal-close" onclick="MonP.closeModal()">&times;</button></div>'+
            '<div class="monp-modal-body" id="monpModalBody"></div>'+
            '</div></div>';
        el.dataset.built = '1';
    }
    MonP.loadInto('monpFeed', 100);
    MonP.loadStatus();
    MonP._timer = setInterval(function(){ MonP.loadStatus(); }, 5000);
};

MonP.stop = function() {
    if (MonP._timer) { clearInterval(MonP._timer); MonP._timer = null; }
};

MonP.loadStatus = function() {
    Admin.ajax('/api/status', function(s) {
        var el = Admin.$('monpStatus');
        if (!el) return;
        var step = s.step_details || s.current_step || 'idle';
        var vlmOn = s.processes && s.processes.vlm;
        var faceOn = s.processes && s.processes.face_pipeline;
        var h = '<span class="monp-st'+(step!=='idle'?' active':'')+'">Шаг: <b>'+Admin.esc(step)+'</b></span>';
        h += '<span class="monp-st'+(vlmOn?' active':'')+'">VLM: <b>'+(vlmOn?'РАБОТАЕТ':'ожидание')+'</b></span>';
        h += '<span class="monp-st'+(faceOn?' active':'')+'">Face: <b>'+(faceOn?'РАБОТАЕТ':'ожидание')+'</b></span>';
        h += '<span class="monp-st">Описано: <b>'+(s.pct_described||0)+'%</b></span>';
        h += '<span class="monp-st">Лица: <b>'+(s.pct_faces||0)+'%</b></span>';
        h += '<span class="monp-st">EXIF: <b>'+(s.pct_exif||0)+'%</b></span>';
        h += '<span class="monp-st">Персон: <b>'+(s.personas_total||0)+'</b></span>';
        el.innerHTML = h;
    });
};

MonP.renderCard = function(p, idx, containerId, compact) {
    var thumb = p.thumbnail || ('/api/photos/thumbnail?path=' + encodeURIComponent(p.path || p.photo_id) + '&size=sm');
    var desc = p.description || '';
    var isExpanded = !compact && MonP._expanded === idx && MonP._expandedCid === containerId;

    var tags = [];
    if (desc) tags.push('<span class="mtag ok">DESC</span>');
    if (p.faces_present) tags.push('<span class="mtag ok">FACES</span>');
    else if (p.faces_present === false && p.total_faces === 0) tags.push('<span class="mtag no">FACES</span>');
    else if (p.faces_present === false && p.total_faces > 0) tags.push('<span class="mtag warn">FACES</span>');
    if (p.total_faces > 0) tags.push('<span class="mtag ok">DET</span>');
    var namedCount = (p.personas && p.personas.length) ? p.personas.length : 0;
    if (namedCount > 0) tags.push('<span class="mtag ok">PERS('+namedCount+')</span>');
    else if (p.total_faces > 0) tags.push('<span class="mtag no">PERS</span>');
    if (p.date) tags.push('<span class="mtag dim">DATE</span>');
    if (p.gps_lat) tags.push('<span class="mtag dim">GPS</span>');
    if (p.camera_model) tags.push('<span class="mtag dim">CAM</span>');

    var ago = '';
    if (p.changed_at) ago = MonP.fmtAgo(p.changed_at);
    else if (p.date) ago = MonP.fmtAgo(p.date);
    var action = MonP.changeAction(p);
    var result = MonP.changeResult(p);

    var h = '<div class="mcard'+(isExpanded?' expanded':'')+'" data-idx="'+idx+'" data-cid="'+containerId+'" onclick="MonP.toggleCard('+idx+',\''+containerId+'\')">';
    h += '<div class="mcard-left'+(isExpanded?' expanded':'')+'">';
    h += '<img src="'+thumb+'" loading="lazy" onclick="event.stopPropagation();MonP.openModal('+idx+')" onerror="this.style.display=\'none\'">';
    h += '</div>';
    h += '<div class="mcard-right">';
    if (ago) h += '<div class="mcard-time"><span class="mcard-ago">'+Admin.esc(ago)+'</span> — <span class="mcard-action">'+Admin.esc(action)+'</span> — <span class="mcard-result">'+Admin.esc(result)+'</span></div>';
    h += '<div class="mcard-tags">'+tags.join(' ')+'</div>';
    if (!isExpanded && desc) h += '<div class="mcard-desc">'+Admin.esc(desc.substring(0,200))+(desc.length>200?'...':'')+'</div>';

    if (p.personas && p.personas.length) {
        h += '<div class="mpers-list-compact">';
        for (var j = 0; j < Math.min(p.personas.length, 3); j++) {
            var per = p.personas[j];
            var faceUrl = (per.face_ids && per.face_ids.length) ? ('/api/photos/face/' + per.face_ids[0]) : '';
            var pName = per.display_name || per.name || '?';
            h += '<div class="mpers-sm">';
            if (faceUrl) h += '<img src="'+faceUrl+'" loading="lazy">';
            h += '<span>'+Admin.esc(pName)+'</span></div>';
        }
        if (p.personas.length > 3) h += '<div class="mpers-sm c-dim">+'+(p.personas.length-3)+'</div>';
        h += '</div>';
    }

    h += '<div class="mcard-path">'+Admin.esc((p.path || p.photo_id || '').split('/').pop())+'</div>';

    if (isExpanded) {
        h += '<div class="mcard-detail">';
        if (desc) h += '<div class="mcard-fulldesc">'+Admin.esc(desc)+'</div>';
        if (p.date) h += '<div class="mcard-meta">Дата: '+Admin.esc(p.date.substring(0,19).replace('T',' '))+'</div>';
        if (p.camera_make || p.camera_model) h += '<div class="mcard-meta">Камера: '+Admin.esc((p.camera_make||'')+' '+(p.camera_model||''))+'</div>';
        if (p.gps_lat) h += '<div class="mcard-meta">GPS: '+p.gps_lat.toFixed(4)+', '+p.gps_lon.toFixed(4)+'</div>';
        if (p.content_hash) h += '<div class="mcard-meta c-dim">hash: '+Admin.esc(p.content_hash)+'</div>';

        if (p.personas && p.personas.length) {
            h += '<div class="mpers-list">';
            for (var j = 0; j < p.personas.length; j++) {
                var per = p.personas[j];
                var faceUrl = (per.face_ids && per.face_ids.length) ? ('/api/photos/face/' + per.face_ids[0]) : '';
                var pName = per.display_name || per.name || '';
                h += '<div class="mpers-card" onclick="event.stopPropagation();MonP.openPersonaModal(\''+Admin.esc(per.persona_id)+'\',\''+Admin.esc(pName)+'\',\''+Admin.esc(per.comment||'')+'\',\''+Admin.esc(faceUrl)+'\')">';
                if (faceUrl) h += '<img class="mpers-face" src="'+faceUrl+'" loading="lazy">';
                else h += '<div class="mpers-face mpers-face-empty">?</div>';
                h += '<div class="mpers-body">';
                h += '<div class="mpers-name">'+(pName ? Admin.esc(pName) : '<span class="c-dim">без имени</span>')+'</div>';
                if (per.comment) h += '<div class="mpers-sub">'+Admin.esc(per.comment)+'</div>';
                h += '<div class="mpers-sub c-dim">'+(per.face_count||0)+' фото</div>';
                h += '</div></div>';
            }
            h += '</div>';
        }

        if (p.faces && p.faces.length) {
            var unbound = p.faces.filter(function(f){
                var hasPersona = f.persona_id && f.persona_id.indexOf('cluster_') === 0;
                return !hasPersona;
            });
            if (unbound.length) {
                h += '<div class="mpers-list">';
                for (var u = 0; u < Math.min(unbound.length, 8); u++) {
                    var uf = unbound[u];
                    var ufUrl = uf.face_id ? ('/api/photos/face/' + uf.face_id) : '';
                    h += '<div class="mpers-card" onclick="event.stopPropagation();MonP.openPersonaModal(\''+Admin.esc(uf.persona_id||'')+'\',\'\',\'\',\''+Admin.esc(ufUrl)+'\')">';
                    if (ufUrl) h += '<img class="mpers-face" src="'+ufUrl+'" loading="lazy">';
                    else h += '<div class="mpers-face mpers-face-empty">?</div>';
                    h += '<div class="mpers-body"><div class="mpers-name c-dim">без имени</div></div></div>';
                }
                if (unbound.length > 8) h += '<div class="mpers-card mpers-card-more">+'+(unbound.length-8)+'</div>';
                h += '</div>';
            }
        }

        h += '<div class="mcard-flags">';
        h += '<span class="c-dim">faces_present:'+(p.faces_present?'1':'0')+'</span>';
        h += '<span class="c-dim">faces_total:'+((p.total_faces||0))+'</span>';
        h += '<span class="c-dim">personas:'+(((p.personas&&p.personas.length)||0))+'</span>';
        h += '<span class="c-dim">embedded:'+(p.embedded?'1':'0')+'</span>';
        h += '<span class="c-dim">exif:'+(p.exif_checked?'1':'0')+'</span>';
        h += '<span class="c-dim">media:'+(p.media_type||'photo')+'</span>';
        h += '</div>';

        h += '</div>';
    }

    h += '</div></div>';
    return h;
};

MonP.toggleCard = function(idx, containerId) {
    if (MonP._expanded === idx && MonP._expandedCid === containerId) {
        MonP._expanded = null;
        MonP._expandedCid = null;
    } else {
        MonP._expanded = idx;
        MonP._expandedCid = containerId;
    }
    MonP.renderFeedInto(containerId, containerId === 'monpFeed' ? 100 : 5);
    if (MonP._expanded !== null) {
        var card = document.querySelector('.mcard[data-idx="'+MonP._expanded+'"][data-cid="'+containerId+'"]');
        if (card) card.scrollIntoView({behavior:'smooth', block:'nearest'});
    }
};

MonP.openModal = function(idx) {
    if (idx < 0 || idx >= MonP.photos.length) return;
    MonP._idx = idx;
    var p = MonP.photos[idx];
    var overlay = Admin.$('monpModal');
    var title = Admin.$('monpModalTitle');
    var body = Admin.$('monpModalBody');
    if (!overlay || !body) return;

    var imgUrl = '/api/photos/?path=' + encodeURIComponent(p.path || p.photo_id);
    title.textContent = (p.path || p.photo_id || '').split('/').pop();

    var h = '<img src="'+imgUrl+'" style="max-width:100%;max-height:70vh;border-radius:6px" onclick="event.stopPropagation()">';
    if (p.description) h += '<div class="mcard-fulldesc" style="text-align:left;margin-top:12px">'+Admin.esc(p.description)+'</div>';
    if (p.date) h += '<div class="mcard-meta" style="text-align:left;margin-top:6px">'+Admin.esc(p.date.substring(0,19).replace('T',' '))+'</div>';
    if (p.gps_lat) h += '<div class="mcard-meta" style="text-align:left">GPS: '+p.gps_lat.toFixed(4)+', '+p.gps_lon.toFixed(4)+'</div>';

    h += '<div style="margin-top:12px;display:flex;gap:8px;justify-content:center">';
    if (idx > 0) h += '<button class="btn" onclick="MonP.openModal('+(idx-1)+')">← Назад</button>';
    if (idx < MonP.photos.length - 1) h += '<button class="btn" onclick="MonP.openModal('+(idx+1)+')">Вперёд →</button>';
    h += '</div>';

    body.innerHTML = h;
    overlay.classList.add('open');
};

MonP.closeModal = function() {
    var overlay = Admin.$('monpModal');
    if (overlay) overlay.classList.remove('open');
    MonP._idx = -1;
};

MonP.fmtAgo = function(iso) {
    var then = new Date(iso + (iso.indexOf('Z')<0 && iso.indexOf('+')<0 ? '+00:00' : ''));
    var diff = Math.floor((new Date() - then) / 1000);
    if (diff < 0) diff = 0;
    if (diff < 60) return diff + 'с назад';
    if (diff < 3600) return Math.floor(diff/60) + 'м назад';
    if (diff < 86400) return Math.floor(diff/3600) + 'ч назад';
    return Math.floor(diff/86400) + 'д назад';
};

MonP.openPersonaModal = function(personaId, currentName, currentComment, faceUrl) {
    var overlay = Admin.$('monpModal');
    var title = Admin.$('monpModalTitle');
    var body = Admin.$('monpModalBody');
    if (!overlay || !body) return;

    title.textContent = currentName || 'Персона';
    var h = '<div class="mpm-layout">';
    if (faceUrl) {
        h += '<div class="mpm-face"><img src="'+faceUrl+'" onclick="event.stopPropagation()"></div>';
    }
    h += '<div class="mpm-form" onclick="event.stopPropagation()">';
    h += '<label class="mpm-label">ФИО</label>';
    h += '<input class="mpm-input" id="mpmName" value="'+Admin.esc(currentName||'')+'" placeholder="Иванов Иван Иванович">';
    h += '<label class="mpm-label">Комментарий</label>';
    h += '<input class="mpm-input" id="mpmComment" value="'+Admin.esc(currentComment||'')+'" placeholder="мать, дочь, жена...">';
    h += '<div class="mpm-btns">';
    h += '<button class="btn btn-primary" onclick="MonP.savePersonaModal(\''+Admin.esc(personaId)+'\')">Сохранить</button>';
    h += '<button class="btn" onclick="MonP.closeModal()">Отмена</button>';
    h += '</div></div></div>';
    body.innerHTML = h;
    overlay.classList.add('open');
    var nameEl = document.getElementById('mpmName');
    if (nameEl) nameEl.focus();
};

MonP.savePersonaModal = function(personaId) {
    var nameEl = document.getElementById('mpmName');
    var commentEl = document.getElementById('mpmComment');
    if (!nameEl) return;
    var data = {display_name: nameEl.value};
    if (commentEl) data.comment = commentEl.value;
    Admin.put('/api/persons/' + personaId, JSON.stringify(data), function(r) {
        MonP.closeModal();
        MonP.loadInto('monpFeed', 100);
    }, function(e) {
        alert('Ошибка: ' + e.message);
    });
};

MonP.editPersona = function(personaId, currentName, currentComment) {
    MonP.openPersonaModal(personaId, currentName, currentComment, '');
};

MonP.renamePersona = function(personaId, currentName) {
    MonP.editPersona(personaId, currentName, '');
};

MonP.nameCluster = function(personaId) {
    MonP.editPersona(personaId, '', '');
};

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') MonP.closeModal();
    if (MonP._idx >= 0 && e.key === 'ArrowLeft') { e.preventDefault(); MonP.openModal(MonP._idx - 1); }
    if (MonP._idx >= 0 && e.key === 'ArrowRight') { e.preventDefault(); MonP.openModal(MonP._idx + 1); }
});

var _monpStyle = document.createElement('style');
_monpStyle.textContent =
    '.monp-status{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 14px 0;padding:10px 14px;background:#161b22;border:1px solid #21262d;border-radius:8px;font-size:12px}'+
    '.monp-st{color:#8b949e}.monp-st b{color:#c9d1d9}.monp-st.active b{color:#3fb950}'+
    '.monp-toolbar{display:flex;align-items:center;gap:8px;margin:0 0 14px 0}'+
    '.monp-toolbar select{background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:4px 8px;font-size:12px}'+
    '.monp-toolbar .btn{background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:4px 12px;font-size:12px;cursor:pointer}'+
    '.monp-toolbar .btn:hover{background:#30363d}'+
    '.monp-feed{display:flex;flex-direction:column;gap:6px}'+
    '.mcard{display:flex;gap:10px;background:#161b22;border:1px solid #21262d;border-radius:8px;padding:10px 12px;cursor:pointer;transition:border-color .15s}'+
    '.mcard:hover{border-color:#30363d}'+
    '.mcard.expanded{border-color:#58a6ff}'+
    '.mcard-left{flex-shrink:0;width:80px;height:60px;overflow:hidden;border-radius:4px;background:#0d1117}'+
    '.mcard-left img{width:100%;height:100%;object-fit:cover;cursor:pointer;transition:transform .15s}'+
    '.mcard-left.expanded{width:160px;height:120px}'+
    '.mcard-right{flex:1;min-width:0;overflow:hidden}'+
    '.mcard-time{font-size:10px;color:#6e7681;margin-bottom:2px}'+
    '.mcard-tags{margin-bottom:4px}'+
    '.mtag{display:inline-block;font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;margin-right:3px;letter-spacing:.3px}'+
    '.mtag.ok{background:rgba(35,134,54,.2);color:#3fb950}'+
    '.mtag.no{background:rgba(218,54,51,.2);color:#f85149}'+
    '.mtag.warn{background:rgba(210,153,34,.2);color:#d29922}'+
    '.mtag.dim{background:rgba(139,148,158,.1);color:#6e7681}'+
    '.mcard-desc{font-size:12px;color:#c9d1d9;line-height:1.4;margin-bottom:4px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}'+
    '.mcard.expanded .mcard-desc{-webkit-line-clamp:unset}'+
    '.mcard-path{font-size:10px;color:#6e7681;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}'+
    '.mcard-personas-compact{display:flex;flex-wrap:wrap;gap:4px;margin:4px 0}'+
    '.mpers-sm{display:flex;align-items:center;gap:3px;font-size:10px;color:#c9d1d9}'+
    '.mpers-sm img{width:18px;height:18px;border-radius:50%;object-fit:cover}'+
    '.mcard-detail{margin-top:8px;padding-top:8px;border-top:1px solid #21262d}'+
    '.mcard-fulldesc{font-size:12px;color:#c9d1d9;line-height:1.5;margin-bottom:8px;white-space:pre-wrap}'+
    '.mcard-meta{font-size:11px;color:#8b949e;margin-bottom:2px}'+
    '.mpers-list{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}'+
    '.mpers-card{display:flex;align-items:center;gap:8px;background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:6px 10px;cursor:pointer;transition:border-color .15s}'+
    '.mpers-card:hover{border-color:#58a6ff}'+
    '.mpers-face{width:32px;height:32px;border-radius:50%;object-fit:cover;flex-shrink:0}'+
    '.mpers-face-empty{display:flex;align-items:center;justify-content:center;background:#21262d;color:#8b949e;font-size:14px}'+
    '.mpers-body{min-width:0}'+
    '.mpers-name{font-size:12px;color:#c9d1d9;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}'+
    '.mpers-sub{font-size:10px;color:#8b949e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}'+
    '.mpers-card-more{font-size:11px;color:#8b949e;padding:6px 10px}'+
    '.mpers-list-compact{display:flex;flex-wrap:wrap;gap:4px;margin:4px 0}'+
    '.mpers-sm{display:flex;align-items:center;gap:3px;font-size:10px;color:#c9d1d9}'+
    '.mpers-sm img{width:18px;height:18px;border-radius:50%;object-fit:cover}'+
    '.mpm-layout{display:flex;gap:20px;align-items:flex-start;justify-content:center;padding:10px}'+
    '.mpm-face img{width:120px;height:120px;border-radius:50%;object-fit:cover;border:2px solid #30363d}'+
    '.mpm-form{flex:1;min-width:200px;text-align:left}'+
    '.mpm-label{display:block;font-size:10px;color:#8b949e;margin:6px 0 2px;text-transform:uppercase;letter-spacing:.5px}'+
    '.mpm-input{display:block;width:100%;background:#161b22;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;padding:8px 10px;font-size:13px;font-family:monospace;box-sizing:border-box}'+
    '.mpm-input:focus{border-color:#58a6ff;outline:none}'+
    '.mpm-btns{display:flex;gap:8px;margin-top:12px}'+
    '.monp-modal-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);z-index:200;display:none;align-items:center;justify-content:center;padding:20px}'+
    '.monp-modal-overlay.open{display:flex}'+
    '.monp-modal-box{background:#0d1117;border:1px solid #30363d;border-radius:10px;width:90vw;max-width:900px;max-height:90vh;display:flex;flex-direction:column;overflow:hidden}'+
    '.monp-modal-head{display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-bottom:1px solid #21262d;background:#161b22}'+
    '.monp-modal-head h3{margin:0;font-size:14px;color:#c9d1d9}'+
    '.monp-modal-close{background:none;border:none;color:#8b949e;font-size:20px;cursor:pointer;padding:0 4px}'+
    '.monp-modal-close:hover{color:#f85149}'+
    '.monp-modal-body{flex:1;padding:16px;overflow:auto;text-align:center}'+
    '.light-theme .monp-status{background:#fff;border-color:#d0d7de}'+
    '.light-theme .monp-st b{color:#24292f}.light-theme .monp-st.active b{color:#1a7f37}'+
    '.light-theme .monp-toolbar select{background:#fff;color:#24292f;border-color:#d0d7de}'+
    '.light-theme .monp-toolbar .btn{background:#f6f8fa;color:#24292f;border-color:#d0d7de}'+
    '.light-theme .monp-toolbar .btn:hover{background:#eaeef2}'+
    '.light-theme .mcard{background:#fff;border-color:#d0d7de}'+
    '.light-theme .mcard:hover{border-color:#afb8c1}'+
    '.light-theme .mcard.expanded{border-color:#0969da}'+
    '.light-theme .mcard-left{background:#f6f8fa}'+
    '.light-theme .mcard-desc{color:#24292f}'+
    '.light-theme .mcard-path{color:#57606a}'+
    '.light-theme .mpers-sm{color:#24292f}'+
    '.light-theme .mcard-detail{border-top-color:#d0d7de}'+
    '.light-theme .mcard-fulldesc{color:#24292f}'+
    '.light-theme .mcard-meta{color:#57606a}'+
    '.light-theme .mpers-card{background:#fff;border-color:#d0d7de}'+
    '.light-theme .mpers-card:hover{border-color:#0969da}'+
    '.light-theme .mpers-face-empty{background:#f6f8fa;color:#57606a}'+
    '.light-theme .mpers-name{color:#24292f}'+
    '.light-theme .mpers-sub{color:#57606a}'+
    '.light-theme .mpers-sm{color:#24292f}'+
    '.light-theme .mpm-face img{border-color:#d0d7de}'+
    '.light-theme .mpm-form label{color:#57606a}'+
    '.light-theme .mpm-input{background:#f6f8fa;color:#24292f;border-color:#d0d7de}'+
    '.light-theme .mpm-input:focus{border-color:#0969da}'+
    '.light-theme .mtag.ok{background:rgba(31,136,61,.15);color:#1a7f37}'+
    '.light-theme .mtag.no{background:rgba(207,34,46,.15);color:#cf222e}'+
    '.light-theme .mtag.warn{background:rgba(154,103,0,.15);color:#9a6700}'+
    '.light-theme .mtag.dim{background:rgba(175,184,193,.15);color:#57606a}'+
    '.light-theme .mpers-edit-box{background:#fff;border-color:#d0d7de}'+
    '.light-theme .mpers-edit-input{background:#f6f8fa;color:#24292f;border-color:#d0d7de}'+
    '.light-theme .mpers-edit-input:focus{border-color:#0969da}'+
    '.light-theme .mpers-edit-label{color:#57606a}'+
    '.light-theme .mpers-comment{color:#57606a}'+
    '.light-theme .monp-modal-overlay{background:rgba(0,0,0,.5)}'+
    '.light-theme .monp-modal-box{background:#fff;border-color:#d0d7de}'+
    '.light-theme .monp-modal-head{background:#f6f8fa;border-color:#d0d7de}'+
    '.light-theme .monp-modal-head h3{color:#24292f}'+
    '.light-theme .monp-modal-close{color:#57606a}'+
    '.light-theme .monp-modal-close:hover{color:#cf222e}'+
    '.light-theme .monp-modal-body{color:#24292f}';
document.head.appendChild(_monpStyle);

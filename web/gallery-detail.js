/* global API, _isMobile, closePhotoModal, currentPhotos, esc, formatDate, videoSrc */
function openDetail(idx) {
     var p = currentPhotos[idx];
     if (!p) return;
     _dpRot = 0;
     _dpIdx = idx;
     _dpHash = p.content_hash || '';
     _flirMode = 'thermal';
      var photoUrl = p.photo_id ? (API + '/photos/?path=' + encodeURIComponent(p.photo_id)) : '';
      var thumbUrl = p.photo_id ? (API + '/photos/thumbnail?path=' + encodeURIComponent(p.photo_id)) : '';
      var vidUrl = videoSrc(p);

      var html;
      if (p.media_type === 'video') {
          html = '<video class="dp-img dp-video-bg" id="detailVideo" src="' + vidUrl + '" controls preload="metadata"></video>';
     } else {
         html = '<img class="dp-img" id="dpImg" src="' + thumbUrl + '" loading="lazy" onerror="this.style.display=\'none\'">';
          html += '<div class="dp-img-bar"><button onclick="rotateDetail(-90)">&#8634;</button><button onclick="rotateDetail(90)">&#8635;</button></div>';
         if (p.is_flir) {
             html += '<div class="flir-mode-bar" id="flirModeBar">';
             html += '<button class="active" onclick="setFlirMode(\'thermal\')">Тепловизор</button>';
             html += '<button onclick="setFlirMode(\'visual\')">Видимый</button>';
             html += '<button onclick="setFlirMode(\'overlay\')">Наложение</button>';
             html += '</div>';
         }
     }
     if (_dpHash) {
         fetch(API + '/photos/edits/' + encodeURIComponent(_dpHash)).then(function(r){return r.json()}).then(function(d){
             var re = (d.edits || []).find(function(e){return e.action==='rotate'});
             if (re && re.params && re.params.angle) {
                 _dpRot = re.params.angle;
                 var img = document.getElementById('dpImg');
                 if (img) img.style.transform = 'rotate(' + _dpRot + 'deg)';
             }
         }).catch(function(){});
     }
    html += '<h2>Подробности</h2>';
    html += '<div id="dpAlbums" style="margin-bottom:10px"></div>';
    if (p.description) html += '<div class="dp-desc">' + esc(p.description) + '</div>';
    html += '<div id="richDescDisplay">';
    if (p.rich_description) {
        html += '<div class="dp-desc rich">' + esc(p.rich_description) + '</div>';
    }
    html += '</div>';
    html += '<div id="richPreview" style="display:none;margin-top:6px"></div>';
    html += '<div id="customDescArea" style="display:none;margin-top:6px"></div>';
    if (p.faces_present) {
        html += '<div id="enrichArea" style="margin-top:6px">';
        html += '<button id="enrichBtn" class="dp-btn-enrich" onclick="enrichPhoto(\'' + esc(p.db_id || '') + '\')">' + (p.rich_description ? 'Обновить описание' : 'Обогатить описание') + '</button>';
        html += '<button class="dp-btn-custom" onclick="showCustomDesc(\'' + esc(p.db_id || '') + '\')">Своё описание</button>';
        html += '</div>';
    }
    html += '<div style="margin-top:6px">';
    html += '<button class="dp-btn-reprocess" onclick="showReprocessModal(\'' + esc(p.db_id || '') + '\')">Переобработать</button>';
    html += '<button class="dp-btn-toalbum" onclick="showAddToAlbum(\'' + esc(p.db_id || p.photo_id) + '\')">В альбом</button>';
    html += '<button class="dp-btn-share" onclick="copyShareLink(\'' + esc(p.db_id || '') + '\',this,\'photo\')">Поделиться</button>';
    html += '</div>';
    if (p.date) {
        var showDate = p.manual_date || p.date;
        html += '<div class="dp-meta" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">Дата: ' + formatDate(showDate, p.date_tz);
        if (p.manual_date) {
            html += ' <span class="manual-date-badge" onclick="showDateEdit()">ручная</span>';
            html += ' <span class="dp-date-btn dp-date-clear" onclick="clearPhotoDate(\'' + esc(p.photo_id) + '\')">✕</span>';
        } else {
            html += ' <span class="dp-date-btn" onclick="showDateEdit()">Изменить</span>';
        }
        html += '</div>';
        if (p.original_date && p.manual_date) html += '<div class="dp-meta dp-muted">EXIF дата: ' + formatDate(p.original_date, p.date_tz) + '</div>';
        html += '<div id="dateEditArea" style="display:none;margin:2px 0 6px">';
        html += '<div style="display:flex;align-items:center;gap:4px">';
        html += '<input type="datetime-local" id="manualDateInput" class="dp-date-input" value="">';
        html += '<button onclick="setPhotoDate(\'' + esc(p.photo_id) + '\')" class="dp-date-save">Задать</button>';
        html += '<button onclick="hideDateEdit()" class="dp-date-cancel">Отмена</button>';
        html += '</div></div>';
    }
    if (p.is_raw) html += '<div class="dp-meta dp-warning-bold">RAW</div>';
    var _fakeCam = /^(h264|h265|hevc|mjpeg|mpeg4|vp[89]|av1|aac|mp4a|pcm|opus|vp9|theora|flac)$/i;
    var _camMake = p.camera_make || '';
    var _camModel = p.camera_model || '';
    if (_fakeCam.test(_camMake)) _camMake = '';
    if (_fakeCam.test(_camModel)) _camModel = '';
    if (p.media_type !== 'video' && (_camMake || _camModel)) html += '<div class="dp-meta">Камера: ' + esc(_camMake + ' ' + _camModel) + '</div>';
    if (p.media_type !== 'video' && (_camMake || _camModel)) html += '<div id="camTimeArea"></div>';
    if (p.media_type === 'video') {
        html += '<div id="videoMetaArea"><div class="dp-meta dp-muted">Загрузка метаданных…</div></div>';
        (function(){
            var pid = p.photo_id;
            fetch(API + '/photos/video_meta?path=' + encodeURIComponent(pid)).then(function(r){return r.json()}).then(function(m){
                var el = document.getElementById('videoMetaArea');
                if (!el) return;
                var h = '';
                if (m.width && m.height) h += '<div class="dp-meta">Разрешение: <b>' + m.width + '×' + m.height + '</b></div>';
                if (m.duration) {
                    var mins = Math.floor(m.duration / 60);
                    var secs = Math.floor(m.duration % 60);
                    h += '<div class="dp-meta">Длительность: <b>' + mins + ':' + (secs < 10 ? '0' : '') + secs + '</b></div>';
                }
                if (m.creation_time) {
                    var ctDate = m.creation_time;
                    if (p.date_tz === 'utc' && ctDate.indexOf('Z') >= 0) {
                        var d = new Date(ctDate);
                        var yy = d.getFullYear();
                        var mm = String(d.getMonth()+1).padStart(2,'0');
                        var dd = String(d.getDate()).padStart(2,'0');
                        var hh = String(d.getHours()).padStart(2,'0');
                        var mi = String(d.getMinutes()).padStart(2,'0');
                        var ss = String(d.getSeconds()).padStart(2,'0');
                        ctDate = dd + '.' + mm + '.' + yy + ' ' + hh + ':' + mi + ':' + ss;
                    }
                    h += '<div class="dp-meta">Дата записи: <b>' + esc(ctDate) + '</b></div>';
                }
                if (m.camera) h += '<div class="dp-meta">Камера: ' + esc(m.camera) + '</div>';
                if (m.video_codec) h += '<div class="dp-meta">Видео: ' + esc(m.video_codec) + (m.pix_fmt ? ' ' + esc(m.pix_fmt) : '') + '</div>';
                if (m.audio_codec) {
                    var ai = esc(m.audio_codec);
                    if (m.audio_sample_rate) ai += ' ' + m.audio_sample_rate + 'Hz';
                    if (m.audio_channels) ai += ' ' + m.audio_channels + 'ch';
                    h += '<div class="dp-meta">Аудио: ' + ai + '</div>';
                } else {
                    h += '<div class="dp-meta dp-warning">Аудио: нет</div>';
                }
                if (m.fps) h += '<div class="dp-meta">Кадры: ' + m.fps + ' fps</div>';
                if (m.bit_rate) {
                    var mbps = (m.bit_rate / 1000000).toFixed(1);
                    h += '<div class="dp-meta">Битрейт: ' + mbps + ' Мбит/с</div>';
                }
                if (m.container) h += '<div class="dp-meta">Контейнер: ' + esc(m.container) + '</div>';
            if (m.tags && Object.keys(m.tags).length > 0) {
                var skipTags = {'creation_time':1,'major_brand':1,'minor_version':1,'compatible_brands':1};
                var tagItems = [];
                var brandItems = [];
                for (var tk in m.tags) {
                    if (skipTags[tk] && m[tk !== 'creation_time' ? '' : 'creation_time']) continue;
                    var tval = String(m.tags[tk]);
                    if (tk === 'major_brand' || tk === 'minor_version' || tk === 'compatible_brands') {
                        brandItems.push(esc(tk.replace(/_/g,' ')) + ': ' + esc(tval));
                    } else {
                        var tl = tk.replace(/^com\.apple\.quicktime\./, '').replace(/_/g, ' ');
                        tagItems.push(esc(tl) + ': ' + esc(tval));
                    }
                }
                if (brandItems.length > 0) {
                    h += '<div style="margin-top:6px">';
                    h += '<div class="dp-collapse" onclick="var el=document.getElementById(\'vtagBrand\');el.style.display=el.style.display===\'none\'?\'block\':\'none\'">Контейнер теги (' + brandItems.length + ') ▾</div>';
                    h += '<div id="vtagBrand" style="display:none;padding-left:8px">';
                    for (var bi = 0; bi < brandItems.length; bi++) h += '<div class="dp-meta">' + brandItems[bi] + '</div>';
                    h += '</div></div>';
                }
                if (tagItems.length > 0) {
                    h += '<div style="margin-top:6px">';
                    h += '<div class="dp-collapse" onclick="var el=document.getElementById(\'vtagOther\');el.style.display=el.style.display===\'none\'?\'block\':\'none\'">Метаданные (' + tagItems.length + ') ▾</div>';
                    h += '<div id="vtagOther" style="display:none;padding-left:8px">';
                    for (var oi = 0; oi < tagItems.length; oi++) h += '<div class="dp-meta">' + tagItems[oi] + '</div>';
                    h += '</div></div>';
                }
            }
                el.innerHTML = h;
            }).catch(function(){
                var el = document.getElementById('videoMetaArea');
                if (el) el.innerHTML = '<div class="dp-meta dp-warning">Метаданные недоступны</div>';
            });
        })();
    }
    html += '<div class="dp-meta">Лица: ' + p.total_faces + '</div>';
    if (p.photo_type && p.photo_type !== 'photo') html += '<div class="dp-meta">Тип: ' + esc(p.photo_type) + '</div>';
    if (p.has_issues) html += '<div class="dp-meta dp-error">Проблемы: ' + esc(p.issue_type || 'да') + '</div>';
    if (p.deleted) {
        html += '<div class="dp-meta dp-error-bold">Удалена</div>';
        html += '<button class="dp-btn-restore" onclick="undeletePhoto(\'' + esc(p.photo_id) + '\')">Восстановить</button>';
    }
    html += '<div class="dp-meta">Семантическая индексация: ' + (p.embedded ? 'да' : 'нет') + '</div>';
    if (p.content_hash) html += '<div class="dp-meta dp-hash" style="word-break:break-all;display:flex;align-items:center;gap:6px"><span class="dp-hash-label">Хеш:</span> <span>' + esc(p.content_hash) + '</span> <button class="copy-hash-btn" data-hash="' + esc(p.content_hash) + '" onclick="var t=document.createElement(\'textarea\');t.value=this.dataset.hash;document.body.appendChild(t);t.select();document.execCommand(\'copy\');document.body.removeChild(t);this.textContent=\'✓\';var b=this;setTimeout(function(){b.textContent=\'📋\'},1000)">📋</button></div>';
    html += '<div class="dp-meta" style="word-break:break-all">Путь: ' + esc(p.photo_id || p.path) + '</div>';
    var allPaths = [p.path];
    if (p.duplicate_paths && p.duplicate_paths.length > 0) {
        html += '<div class="dp-meta dp-warning" style="margin-top:6px">Дубликаты (' + p.duplicate_paths.length + '):</div>';
        for (var di = 0; di < p.duplicate_paths.length; di++) {
            var dp = p.duplicate_paths[di].replace(/\\/g,'/');
            allPaths.push(dp);
            var short = dp.split('/').slice(-3).join('/');
            html += '<div class="dp-meta dp-dup-path" title="' + esc(dp) + '">' + esc(short) + '</div>';
        }
    }
    html += '<div class="dp-meta" style="margin-top:6px">';
    for (var ai = 0; ai < allPaths.length; ai++) {
        var ap = allPaths[ai].replace(/\\/g,'/');
        var ashort = ap.split('/').slice(-2).join('/');
        html += '<a href="#" class="dp-alt-path" onclick="goToCatalog(\'' + esc(ap) + '\');return false" title="' + esc(ap) + '">📂 ' + esc(ashort) + '</a>';
    }
    html += '</div>';

    if (p.exif_raw) {
        try {
            var raw = JSON.parse(p.exif_raw);
            var groups = {
                'Камера': ['Image Make','Image Model','Image Orientation','Image Software','EXIF BodySerialNumber','EXIF CameraOwnerName','EXIF LensModel','EXIF LensSpecification','EXIF LensSerialNumber'],
                'Съёмка': ['EXIF ExposureTime','EXIF FNumber','EXIF ISOSpeedRatings','EXIF SensitivityType','EXIF RecommendedExposureIndex','EXIF ExposureProgram','EXIF ExposureMode','EXIF ExposureBiasValue','EXIF MeteringMode','EXIF Flash','EXIF FocalLength','EXIF FocalLengthIn35mmFilm','EXIF ShutterSpeedValue','EXIF ApertureValue','EXIF MaxApertureValue'],
                'Изображение': ['EXIF ExifImageWidth','EXIF ExifImageLength','Image ImageWidth','Image ImageLength','EXIF BitsPerSample','Image Compression','Image XResolution','Image YResolution','EXIF ColorSpace','EXIF ExifVersion','EXIF FlashPixVersion'],
                'Дата': ['Image DateTime','EXIF DateTimeOriginal','EXIF DateTimeDigitized','EXIF SubSecTime','EXIF SubSecTimeOriginal','EXIF SubSecTimeDigitized'],
                'Автор': ['Image Artist','Image Copyright'],
                'GPS': ['GPS GPSLatitude','GPS GPSLongitude','GPS GPSLatitudeRef','GPS GPSLongitudeRef','GPS GPSAltitude','GPS GPSAltitudeRef','Image GPSInfo']
            };
            var names = {
                'EXIF ExposureTime': 'Выдержка', 'EXIF FNumber': 'Диафрагма',
                'EXIF ISOSpeedRatings': 'ISO', 'EXIF FocalLength': 'Фокус',
                'EXIF FocalLengthIn35mmFilm': 'Фокус (35мм)', 'EXIF Flash': 'Вспышка',
                'EXIF ExposureMode': 'Экспозиция', 'EXIF WhiteBalance': 'Баланс белого',
                'EXIF MeteringMode': 'Замер', 'EXIF ExposureBiasValue': 'Компенсация',
                'EXIF ExifImageWidth': 'Ширина', 'EXIF ExifImageLength': 'Высота',
                'Image ImageWidth': 'Ширина', 'Image ImageLength': 'Высота',
                'EXIF SceneCaptureType': 'Сцена', 'EXIF Sharpness': 'Резкость',
                'EXIF Contrast': 'Контраст', 'EXIF Saturation': 'Насыщенность',
                'Image Software': 'Софт', 'Image Orientation': 'Ориентация',
                'Image Make': 'Производитель', 'Image Model': 'Модель',
                'Image DateTime': 'Дата', 'EXIF DateTimeOriginal': 'Дата съёмки',
                'EXIF DateTimeDigitized': 'Дата оцифровки',
                'EXIF ExposureProgram': 'Программа', 'EXIF SensitivityType': 'Тип ISO',
                'EXIF RecommendedExposureIndex': 'ISO (рекоменд.)',
                'EXIF ShutterSpeedValue': 'Скорость затвора', 'EXIF ApertureValue': 'Значение диафрагмы',
                'EXIF MaxApertureValue': 'Макс. диафрагма',
                'EXIF BitsPerSample': 'Глубина цвета', 'Image Compression': 'Сжатие',
                'Image XResolution': 'Разрешение X', 'Image YResolution': 'Разрешение Y',
                'EXIF ColorSpace': 'Цвет. пространство', 'Image Artist': 'Автор', 'Image Copyright': 'Копирайт',
                'EXIF LensModel': 'Объектив', 'EXIF LensSpecification': 'Специф. объектива',
                'EXIF LensSerialNumber': 'Серийный объектива', 'EXIF BodySerialNumber': 'Серийный камеры',
                'EXIF CameraOwnerName': 'Владелец', 'EXIF SubSecTime': 'Субсекунды',
                'EXIF SubSecTimeOriginal': 'Субсек. съёмки', 'EXIF SubSecTimeDigitized': 'Субсек. оцифровки',
                'GPS GPSLatitude': 'Широта', 'GPS GPSLongitude': 'Долгота',
                'GPS GPSAltitude': 'Высота', 'GPS GPSLatitudeRef': 'Сторона широты',
                'GPS GPSLongitudeRef': 'Сторона долготы', 'Image GPSInfo': 'GPS смещение',
                'Image ImageDescription': 'Описание'
            };
            var grouped = {};
            var used = {};
            for (var gName in groups) {
                var gKeys = groups[gName];
                var gItems = [];
                for (var gi = 0; gi < gKeys.length; gi++) {
                    var gk = gKeys[gi];
                    if (raw[gk] !== undefined) {
                        var lbl = names[gk] || gk.replace(/^(EXIF|Image|GPS) /, '');
                        gItems.push(esc(lbl) + ': ' + esc(raw[gk]));
                        used[gk] = true;
                    }
                }
                if (gItems.length > 0) grouped[gName] = gItems;
            }
            var otherItems = [];
            for (var k in raw) {
                if (used[k]) continue;
                var label = names[k] || k.replace(/^(EXIF|Image|GPS|Interoperability) /, '');
                otherItems.push(esc(label) + ': ' + esc(raw[k]));
            }
            if (otherItems.length > 0) grouped['Прочее'] = otherItems;

            if (grouped['GPS'] && p.gps_lat && p.gps_lon) {
                var gUrl = 'https://www.google.com/maps?q=' + p.gps_lat + ',' + p.gps_lon;
                var yUrl = 'https://yandex.ru/maps/?ll=' + p.gps_lon + ',' + p.gps_lat + '&z=15&mode=whatshere&whatshere[point]=' + p.gps_lon + ',' + p.gps_lat;
                grouped['GPS'].unshift(
                    '<div style="display:flex;gap:10px;margin-bottom:4px">' +
                    '<a href="' + gUrl + '" target="_blank" rel="noopener" class="dp-map-link">' +
                    '<span style="font-weight:bold;font-size:14px"><span style="color:#4285F4">G</span><span style="color:#EA4335">o</span><span style="color:#FBBC05">o</span><span style="color:#4285F4">g</span><span style="color:#34A853">l</span><span style="color:#EA4335">e</span></span> Maps</a>' +
                    '<a href="' + yUrl + '" target="_blank" rel="noopener" class="dp-map-link">' +
                    '<span style="font-weight:bold;font-size:15px;color:#FC3F1D">Я</span>ndex Карты</a>' +
                    '</div>'
                );
            }

            var gid = 0;
            for (let gName in grouped) {
                var gId = 'exifGrp_' + gid;
                html += '<div style="margin-top:6px">';
                html += '<div class="dp-collapse" onclick="var el=document.getElementById(\'' + gId + '\');el.style.display=el.style.display===\'none\'?\'block\':\'none\'">' + esc(gName) + ' (' + grouped[gName].length + ') ▾</div>';
                html += '<div id="' + gId + '" style="padding-left:8px">';
                for (var ii = 0; ii < grouped[gName].length; ii++) {
                    html += '<div class="dp-meta">' + grouped[gName][ii] + '</div>';
                }
                html += '</div></div>';
                gid++;
            }
        } catch(e) {}
    }

    if (p.personas && p.personas.length > 0) {
        html += '<div class="dp-personas"><div class="dp-section-label">Персоны (нажмите для редактирования):</div>';
        for (var j = 0; j < p.personas.length; j++) {
            var per = p.personas[j];
            var fid = (per.face_ids && per.face_ids.length > 0) ? per.face_ids[0] : '';
            var hasName = per.display_name ? true : false;
            var cls = hasName ? 'dp-pchip has-name' : 'dp-pchip';
            html += '<div class="' + cls + '" onclick="openFaceModal(\'' + esc(per.persona_id) + '\',\'' + esc(fid) + '\')">';
            if (fid) html += '<img src="' + API + '/photos/face/' + fid + '?margin=0.5" loading="lazy">';
            html += '<span class="nm">' + esc(per.display_name || per.name) + '</span>';
            if (per.comment) html += '<span class="cm dp-persona-comment">' + esc(per.comment) + '</span>';
            html += '</div>';
        }
        html += '</div>';
    }

    html += '<div style="margin-top:12px"><button class="dp-btn-full" onclick="openFullPhoto(\'' + esc(p.media_type === 'video' ? vidUrl : photoUrl) + '\')">Открыть полное фото</button></div>';

     document.getElementById('dpContent').innerHTML = html;
     document.getElementById('detailPanel').classList.add('show');
     if (_isMobile()) document.documentElement.classList.add('scroll-lock');
     _checkCamAlbum(p);
     _loadPhotoAlbums(p);
}

function _loadPhotoAlbums(p) {
    var ident = p.content_hash || p.photo_id;
    if (!ident) return;
    fetch(API + '/albums/by_photo/' + encodeURIComponent(ident)).then(function(r) {
        if (!r.ok) return null;
        return r.json();
    }).then(function(d) {
        var el = document.getElementById('dpAlbums');
        if (!el) return;
        if (!d || !d.albums || !d.albums.length) { el.innerHTML = ''; return; }
        var h = '<div class="dp-section-label">Альбомы (' + d.albums.length + '):</div>';
        h += '<div style="display:flex;flex-wrap:wrap;gap:4px">';
        for (var i = 0; i < d.albums.length; i++) {
            var a = d.albums[i];
            var date = a.date_start ? a.date_start.slice(0,10) : '';
            h += '<a href="/albums?album=' + encodeURIComponent(a.album_id) + '" class="dp-album-chip" title="' + esc(date + ' · ' + a.photo_count + ' фото') + '">' + esc(a.title) + '</a>';
        }
        h += '</div>';
        el.innerHTML = h;
    }).catch(function() {
        var el = document.getElementById('dpAlbums');
        if (el) el.innerHTML = '';
    });
}

 function closeDetail() {
     document.getElementById('detailPanel').classList.remove('show');
     if (_isMobile()) document.documentElement.classList.remove('scroll-lock');
 }

var _dpRot = 0;
var _dpIdx = -1;
var _dpHash = '';
var _flirMode = 'thermal';

function saveRotate(hash, angle) {
    if (!hash) return;
    fetch(API + '/photos/edits/' + encodeURIComponent(hash), {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'rotate', params: {angle: angle}, replace: true})
    }).then(function(){
        for (var i = 0; i < currentPhotos.length; i++) {
            if (currentPhotos[i].content_hash === hash) {
                currentPhotos[i].edits = [{action:'rotate',params:{angle:angle},edit_id:0,action_order:0,enabled:1}];
                var card = document.querySelector('.card[data-photo-id="' + CSS.escape(currentPhotos[i].photo_id || '') + '"]');
                if (card) { var ci = card.querySelector('img'); if (ci) ci.style.transform = 'rotate(' + ((angle % 360 + 360) % 360) + 'deg)'; }
            }
        }
    }).catch(function(){});
}


function rotateDetail(deg) {
    _dpRot = _dpRot + deg;
    var img = document.getElementById('dpImg');
    if (img) img.style.transform = 'rotate(' + _dpRot + 'deg)';
    var saveAngle = ((_dpRot % 360) + 360) % 360;
    saveRotate(_dpHash, saveAngle);
}

function setFlirMode(mode) {
    _flirMode = mode;
    var img = document.getElementById('dpImg');
    if (!img) return;
    var p = currentPhotos[_dpIdx];
    if (!p || !p.is_flir) return;
    var pid = encodeURIComponent(p.photo_id);
    if (mode === 'thermal') {
        img.src = API + '/photos/?path=' + pid;
    } else if (mode === 'visual') {
        img.src = API + '/photos/flir_visual?path=' + pid;
    } else if (mode === 'overlay') {
        img.src = API + '/photos/flir_overlay?path=' + pid + '&alpha=0.55';
    }
    var btns = document.querySelectorAll('#flirModeBar button');
    for (var i = 0; i < btns.length; i++) btns[i].classList.remove('active');
    if (mode === 'thermal') btns[0].classList.add('active');
    else if (mode === 'visual') btns[1].classList.add('active');
    else btns[2].classList.add('active');
}

 function addPhotoGps(photoId) {
    window.open('/map?mode=pick&photo_id=' + encodeURIComponent(photoId), '_blank');
}

function clearPhotoGps(photoId) {
    if (!confirm('Удалить GPS-привязку для этого фото?')) return;
    fetch(API + '/photos/clear_gps', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo_id: photoId })
    }).then(function(r) {
        if (r.ok) {
            var locEl = document.getElementById('modalLoc');
            locEl.innerHTML = '<span class="modal-add-gps" onclick="addPhotoGps(\'' + esc(photoId) + '\')">📍 Отметить на карте</span>';
            var p = currentPhotos.find(function(ph) { return ph.photo_id === photoId; });
            if (p) { p.gps_lat = null; p.gps_lon = null; p.manual_gps = 0; }
        } else {
            alert('Ошибка при удалении GPS');
        }
    }).catch(function(e) {
        alert('Ошибка: ' + e.message);
    });
}

function setPhotoDate(photoId) {
    var input = document.getElementById('manualDateInput');
    if (!input) return;
    var val = input.value;
    if (!val) { alert('Укажите дату и время'); return; }
    var manualDate = val.replace('T', ' ') + ':00';
    fetch(API + '/photos/set_date', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo_id: photoId, manual_date: manualDate })
    }).then(function(r) { return r.json(); }).then(function(data) {
        if (data.success) {
            var p = currentPhotos.find(function(ph) { return ph.photo_id === photoId; });
            if (p) {
                if (!p.original_date) p.original_date = p.date;
                p.manual_date = manualDate; p.date = manualDate;
            }
            var idx = currentPhotos.findIndex(function(ph) { return ph.photo_id === photoId; });
            if (idx >= 0) openDetail(idx);
        } else {
            alert('Ошибка: ' + (data.detail || 'не удалось задать дату'));
        }
    }).catch(function(e) { alert('Ошибка: ' + e.message); });
}

function showDateEdit() {
    var el = document.getElementById('dateEditArea');
    if (el) el.style.display = 'block';
    var input = document.getElementById('manualDateInput');
    if (input) input.focus();
}

function hideDateEdit() {
    var el = document.getElementById('dateEditArea');
    if (el) el.style.display = 'none';
}

function clearPhotoDate(photoId) {
    if (!confirm('Удалить ручную дату для этого фото?')) return;
    fetch(API + '/photos/clear_date', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo_id: photoId })
    }).then(function(r) { return r.json(); }).then(function(data) {
        if (data.success) {
            var p = currentPhotos.find(function(ph) { return ph.photo_id === photoId; });
            if (p) { p.manual_date = null; p.date = p.original_date || p.date; }
            var idx = currentPhotos.findIndex(function(ph) { return ph.photo_id === photoId; });
            if (idx >= 0) openDetail(idx);
        } else {
            alert('Ошибка при удалении даты');
        }
    }).catch(function(e) { alert('Ошибка: ' + e.message); });
}

var _pendingDelId = null;
function markDeleted(photoId) {
    _pendingDelId = photoId;
    document.getElementById('delDialog').classList.add('show');
}
function confirmDel() {
    var photoId = _pendingDelId;
    _pendingDelId = null;
    document.getElementById('delDialog').classList.remove('show');
    if (!photoId) return;
    fetch(API + '/photos/mark_deleted', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo_id: photoId })
    }).then(function(r) { return r.json(); }).then(function(data) {
        if (data.success) {
            var p = currentPhotos.find(function(ph) { return ph.photo_id === photoId; });
            if (p) p.deleted = true;
            var card = document.querySelector('.card[data-photo-id="' + CSS.escape(photoId) + '"]');
            if (card) {
                card.classList.add('deleted-card');
                var mark = card.querySelector('.del-mark');
                if (mark) mark.remove();
                var undo = document.createElement('div');
                undo.className = 'undo-mark';
                undo.setAttribute('onclick', "event.stopPropagation();undeletePhoto('" + photoId.replace(/'/g, "\\'") + "')");
                undo.textContent = 'Отменить';
                card.insertBefore(undo, card.querySelector('.overlay'));
            }
        } else {
            alert('Ошибка');
        }
    }).catch(function(e) { alert('Ошибка: ' + e.message); });
}

function cancelDel() {
    _pendingDelId = null;
    document.getElementById('delDialog').classList.remove('show');
}

function undeletePhoto(photoId) {
    fetch(API + '/photos/undelete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo_id: photoId })
    }).then(function(r) { return r.json(); }).then(function(data) {
        if (data.success) {
            var p = currentPhotos.find(function(ph) { return ph.photo_id === photoId; });
            if (p) p.deleted = false;
            var card = document.querySelector('.card[data-photo-id="' + CSS.escape(photoId) + '"]');
            if (card) {
                card.classList.remove('deleted-card');
                var undo = card.querySelector('.undo-mark');
                if (undo) undo.remove();
                if (!card.querySelector('.del-mark')) {
                    var mk = document.createElement('div');
                    mk.className = 'del-mark';
                    mk.setAttribute('onclick', "event.stopPropagation();markDeleted('" + photoId.replace(/'/g, "\\'") + "')");
                    mk.setAttribute('title', 'Удалить');
                    mk.innerHTML = '&#128465;';
                    card.insertBefore(mk, card.querySelector('.overlay'));
                }
            }
        } else {
            alert('Ошибка');
        }
    }).catch(function(e) { alert('Ошибка: ' + e.message); });
}
function goToGps(lat, lon) {
    closePhotoModal();
    window.open('/map', '_blank');
}

function goToCatalog(photoPath) {
    window.open('/catalog?photo=' + encodeURIComponent(photoPath), '_blank');
}

function enrichPhoto(photoId) {
    if (!photoId) return;
    var btn = document.getElementById('enrichBtn');
    btn.textContent = 'Идёт заполнение...';
    btn.disabled = true;
    var preview = document.getElementById('richPreview');
    preview.style.display = 'none';
    preview.innerHTML = '';
    fetch(API + '/photos/' + encodeURIComponent(photoId) + '/enrich', {method: 'POST'})
        .then(function(r) { return r.json(); })
        .then(function(d) {
            var hasRich = document.querySelector('#richDescDisplay .dp-desc');
            btn.textContent = hasRich ? 'Обновить описание' : 'Обогатить описание';
            btn.disabled = false;
            if (d.ok && d.rich_description) {
                preview.style.display = 'block';
                preview.className = 'rich-preview';
                preview.innerHTML =
                    '<div class="dp-desc rich">' + esc(d.rich_description) + '</div>' +
                    '<div class="rich-actions">' +
                    '<button onclick="acceptRich(\'' + esc(photoId) + '\')" style="padding:3px 10px;font-size:11px">Сохранить</button>' +
                    '<button class="btn-reject" onclick="rejectRich()">Отклонить</button>' +
                    '</div>';
                _pendingRich = d.rich_description;
            } else {
                preview.style.display = 'block';
                preview.innerHTML = '<div class="rich-error">Ошибка: ' + esc(d.error || 'нет результата') + '</div>';
            }
        })
        .catch(function() {
            btn.textContent = 'Ошибка';
            btn.style.background = '#da3633';
            btn.disabled = false;
        });
}

var _pendingRich = '';

function acceptRich(photoId) {
    if (!_pendingRich || !photoId) return;
    fetch(API + '/photos/' + encodeURIComponent(photoId) + '/rich_description', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({rich_description: _pendingRich})
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        if (d.ok) {
            var display = document.getElementById('richDescDisplay');
            display.innerHTML = '<div class="dp-desc rich">' + esc(_pendingRich) + '</div>';
            document.getElementById('richPreview').style.display = 'none';
            _pendingRich = '';
            var btn = document.getElementById('enrichBtn');
            if (btn) btn.textContent = 'Обновить описание';
        }
    });
}

function rejectRich() {
    document.getElementById('richPreview').style.display = 'none';
    _pendingRich = '';
}

function showCustomDesc(photoId) {
    var area = document.getElementById('customDescArea');
    if (area.style.display !== 'none' && area.innerHTML) {
        area.style.display = 'none';
        area.innerHTML = '';
        return;
    }
    var existing = document.querySelector('#richDescDisplay .dp-desc');
    var existingText = existing ? existing.textContent : '';
    area.style.display = 'block';
    area.className = 'rich-preview';
    area.innerHTML =
        '<textarea id="customDescInput">' + esc(existingText) + '</textarea>' +
        '<div class="rich-actions">' +
        '<button onclick="saveCustomDesc(\'' + esc(photoId) + '\')" style="padding:3px 10px;font-size:11px">Сохранить</button>' +
        '<button class="btn-cancel" onclick="document.getElementById(\'customDescArea\').style.display=\'none\'">Отмена</button>' +
        '</div>';
}

function saveCustomDesc(photoId) {
    var input = document.getElementById('customDescInput');
    var text = input.value.trim();
    if (!text || !photoId) return;
    fetch(API + '/photos/' + encodeURIComponent(photoId) + '/rich_description', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({rich_description: text})
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        if (d.ok) {
            var display = document.getElementById('richDescDisplay');
            display.innerHTML = '<div class="dp-desc rich">' + esc(text) + '</div>';
            document.getElementById('customDescArea').style.display = 'none';
            var btn = document.getElementById('enrichBtn');
            if (btn) btn.textContent = 'Обновить описание';
        }
    });
}

// ─── Коррекция времени камеры ──────────────────────────────

var _camD = null, _camS = 0, _camCss = false, _camDrag = false;

function _checkCamAlbum(p) {
    var area = document.getElementById('camTimeArea');
    if (!area || !p.db_id) return;
    if (typeof currentAlbum !== 'undefined' && currentAlbum && currentAlbum.photo_ids) {
        if (currentAlbum.photo_ids.indexOf(p.db_id) >= 0) {
            _camBtn(area, currentAlbum.album_id, p.db_id);
            return;
        }
    }
    fetch(API + '/albums/by_photo/' + encodeURIComponent(p.db_id))
        .then(function(r) { if (!r.ok) return null; return r.json(); })
        .then(function(d) {
            if (d && d.albums && d.albums.length > 0)
                _camBtn(area, d.albums[0].album_id, d.photo_uuid);
        }).catch(function() {});
}

function _camBtn(area, aid, pid) {
    area.innerHTML = '<button class="dp-btn-custom" style="margin-top:4px" onclick="openCam(\'' + esc(aid) + '\',\'' + esc(pid) + '\')">Коррекция времени камеры</button>';
}

function _camStyles() {
    if (_camCss) return;
    var s = document.createElement('style');
    s.textContent = [
        '.cm-modal{position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:1100;display:flex;justify-content:center;align-items:center}',
        '.cm-box{background:#161b22;border:1px solid #30363d;border-radius:8px;width:90vw;max-width:1400px;height:90vh;display:flex;flex-direction:column;padding:20px;color:#c9d1d9;font-family:monospace;font-size:13px;box-sizing:border-box}',
        '.cm-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-shrink:0}',
        '.cm-head h2{color:#58a6ff;font-size:18px;margin:0}',
        '.cm-x{cursor:pointer;color:#6e7681;font-size:28px}',
        '.cm-x:hover{color:#f85149}',
        '.cm-info{color:#8b949e;margin-bottom:10px;flex-shrink:0}',
        '.cm-info b{color:#c9d1d9}',
        '.cm-strip-w{flex:1;min-height:0;background:#0d1117;border:1px solid #21262d;border-radius:6px;overflow:hidden;margin-bottom:12px}',
        '.cm-strip{height:100%;overflow-y:auto;overflow-x:hidden;white-space:normal;padding:8px;display:flex;flex-wrap:wrap;align-content:flex-start;gap:6px}',
        '.cm-ph{width:90px;height:90px;border-radius:4px;object-fit:cover;opacity:0.5;flex-shrink:0}',
        '.cm-cm{width:120px;height:120px;border-radius:5px;object-fit:cover;border:2px solid #d29922;opacity:0.85;flex-shrink:0}',
        '.cm-an{width:120px;height:120px;border-radius:5px;object-fit:cover;border:3px solid #d29922;box-shadow:0 0 12px rgba(210,153,2,.7);cursor:grab;flex-shrink:0;position:relative;z-index:2}',
        '.cm-an.drag{cursor:grabbing;box-shadow:0 0 20px rgba(210,153,2,1);z-index:5}',
        '.cm-bot{flex-shrink:0}',
        '.cm-row{display:flex;align-items:center;gap:14px;padding:12px;background:#0d1117;border-radius:6px;border:1px solid #21262d;margin-bottom:10px}',
        '.cm-row input[type=range]{flex:1;height:8px;-webkit-appearance:none;appearance:none;background:#21262d;border-radius:4px;outline:none}',
        '.cm-row input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:24px;height:24px;border-radius:50%;background:#d29922;cursor:pointer;border:2px solid #161b22}',
        '.cm-row input[type=range]::-moz-range-thumb{width:24px;height:24px;border-radius:50%;background:#d29922;cursor:pointer;border:2px solid #161b22}',
        '.cm-sv{color:#d29922;font-weight:bold;min-width:90px;text-align:center;font-size:15px}',
        '.cm-ir{display:flex;gap:12px;align-items:center;padding:12px;background:#0d1117;border-radius:6px;border:1px solid #21262d;margin-bottom:10px}',
        '.cm-ir label{color:#8b949e;font-size:11px;white-space:nowrap}',
        '.cm-ir input{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;border-radius:4px;padding:8px;font-family:monospace;font-size:15px;flex:1}',
        '.cm-act{display:flex;gap:12px;justify-content:flex-end}',
        '.cm-act button{padding:10px 24px;border:none;border-radius:6px;cursor:pointer;font-family:monospace;font-size:14px}',
        '.cm-ok{background:#238636;color:#fff}',
        '.cm-no{background:#21262d;color:#c9d1d9}',
        '.light-theme .cm-box{background:#f6f8fa;border-color:#d0d7de;color:#24292f}',
        '.light-theme .cm-head h2{color:#0969da}',
        '.light-theme .cm-info{color:#57606a}',
        '.light-theme .cm-strip-w{background:#eaeef2;border-color:#d0d7de}',
        '.light-theme .cm-row{background:#eaeef2;border-color:#d0d7de}',
        '.light-theme .cm-ir{background:#eaeef2;border-color:#d0d7de}',
        '.light-theme .cm-ir input{background:#fff;color:#24292f;border-color:#d0d7de}',
        '.light-theme .cm-no{background:#eaeef2;color:#24292f;border:1px solid #d0d7de}',
        '.cm-prev{position:fixed;z-index:1200;pointer-events:none;display:none;border-radius:8px;overflow:hidden;box-shadow:0 8px 40px rgba(0,0,0,.8)}',
        '.cm-prev img{width:80vw;max-width:1000px;max-height:80vh;object-fit:contain;display:block}',
        '.cm-prev-info{position:absolute;bottom:0;left:0;right:0;background:rgba(0,0,0,.8);color:#fff;padding:8px 14px;font-family:monospace;font-size:16px;text-align:center}',
        '.cm-cap{text-align:center;flex-shrink:0;margin-bottom:4px}',
        '.cm-cap-time{font-size:12px;font-weight:bold;color:#d29922;white-space:nowrap}',
        '.cm-cap-date{font-size:9px;color:#6e7681;white-space:nowrap}',
        '.cm-cap-anc .cm-cap-time{color:#d29922;font-size:14px}',
        '.cm-cap-ph .cm-cap-time{color:#8b949e;font-size:10px;font-weight:normal}',
        '.cm-cap-diff{font-size:9px;color:#6e7681;white-space:nowrap}',
        '.cm-cap-diff.warn{color:#d29922;font-weight:bold}',
        '.cm-cap-diff.crit{color:#f85149;font-weight:bold}',
        '.cm-item-wrap{display:flex;flex-direction:column;align-items:center;flex-shrink:0}'
    ].join('\n');
    document.head.appendChild(s);
    _camCss = true;
}

function _d2j(s) { return s ? new Date(s.replace(' ', 'T')) : null; }
function _d2jTz(s, tz) {
    if (!s) return null;
    if (tz === 'utc') {
        var d = new Date(s.replace(' ', 'T') + 'Z');
        return new Date(d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'T'+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')+':'+String(d.getSeconds()).padStart(2,'0'));
    }
    return new Date(s.replace(' ', 'T'));
}
function _j2a(d) {
    if (!d) return '';
    return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+' '+
        String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')+':'+String(d.getSeconds()).padStart(2,'0');
}
function _j2i(d) {
    if (!d) return '';
    return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'T'+
        String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
}
function _fd(d) {
    if (!d) return '';
    return String(d.getDate()).padStart(2,'0')+'.'+String(d.getMonth()+1).padStart(2,'0')+'.'+d.getFullYear()+' '+
        String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
}
function _fs(sc) {
    var sg = sc >= 0 ? '+' : '-', a = Math.abs(sc);
    var h = Math.floor(a/3600), m = Math.floor((a%3600)/60);
    return sg + (h > 0 ? h+'ч '+m+'м' : m+'м');
}
function _fm(mn) {
    // Точное расхождение в минутах: "-5760 мин", "+3.5 мин", "0 мин"
    var r = Math.round(mn * 10) / 10;
    if (Math.abs(r) < 0.05) return '0 мин';
    return (r > 0 ? '+' : '') + r + ' мин';
}
function _fmCls(mn) {
    var a = Math.abs(mn);
    if (a < 0.05) return 'cm-cap-diff';
    if (a >= 720) return 'cm-cap-diff crit';
    return 'cm-cap-diff warn';
}

function openCam(aid, pid) {
    closeDetail();
    fetch(API + '/albums/' + encodeURIComponent(aid) + '/camera_group?photo_id=' + encodeURIComponent(pid))
        .then(function(r) { if (!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
        .then(function(d) { d.album_id = aid; _camD = d; _camS = 0; _camRender(); })
        .catch(function(e) { alert('\u041e\u0448\u0438\u0431\u043a\u0430: ' + e.message); });
}

function _camRender() {
    _camStyles();
    var d = _camD;
    if (!d) return;
    var old = document.getElementById('cmModal');
    if (old) old.remove();

    var items = [];
    for (var i = 0; i < d.timeline.length; i++) {
        var t = d.timeline[i];
        var dt = _d2jTz(t.date, t.date_tz);
        if (!dt) continue;
        var baseDt = t.is_camera
            ? (t.db_date ? _d2j(t.db_date) : null)
            : (t.original_date ? _d2jTz(t.original_date, t.date_tz) : null);
        items.push({i: i, d: dt, cam: t.is_camera, anc: t.is_anchor, id: t.db_id, base: baseDt});
    }
    items.sort(function(a, b) { return a.d - b.d; });
    d._items = items;

    var sh = '';
    for (var k = 0; k < items.length; k++) {
        var it = items[k];
        var url = API + '/photos/thumbnail?path=' + encodeURIComponent(it.id) + '&size=sm';
        var fullUrl = API + '/photos/?path=' + encodeURIComponent(it.id);
        var capCls = it.anc ? 'cm-cap-anc' : (it.cam ? '' : 'cm-cap-ph');
        var imgCls = it.anc ? 'cm-an' : (it.cam ? 'cm-cm' : 'cm-ph');
        var idAttr = it.anc ? ' id="cmAnc"' : '';
        var timeStr = _fd(it.d);
        var dateStr = it.d.getFullYear()+'-'+String(it.d.getMonth()+1).padStart(2,'0')+'-'+String(it.d.getDate()).padStart(2,'0');
        var timeOnly = String(it.d.getHours()).padStart(2,'0')+':'+String(it.d.getMinutes()).padStart(2,'0')+':'+String(it.d.getSeconds()).padStart(2,'0');
        var diffMn = it.base ? (it.d - it.base) / 60000 : 0;
        sh += '<div class="cm-item-wrap">' +
            '<img class="' + imgCls + '"' + idAttr + ' data-k="' + it.i + '" data-full="' + esc(fullUrl) + '" ' +
            'data-time="' + esc(timeStr) + '" src="' + url + '" loading="lazy" onerror="this.style.opacity=0.3" ' +
            'onmouseenter="_cmHover(this)" onmouseleave="_cmHoverEnd()">' +
            '<div class="cm-cap ' + capCls + '">' +
            '<div class="cm-cap-time">' + esc(timeOnly) + '</div>' +
            '<div class="cm-cap-date">' + esc(dateStr) + '</div>' +
            '<div class="' + _fmCls(diffMn) + '">' + esc(_fm(diffMn)) + '</div>' +
            '</div></div>';
    }

    var aOrig = _d2j(d.anchor_date);

    var m = document.createElement('div');
    m.id = 'cmModal';
    m.className = 'cm-modal';
    m.innerHTML =
        '<div class="cm-box">' +
        '<div class="cm-head"><h2>\u041a\u043e\u0440\u0440\u0435\u043a\u0446\u0438\u044f \u0432\u0440\u0435\u043c\u0435\u043d\u0438 \u043a\u0430\u043c\u0435\u0440\u044b</h2>' +
        '<span class="cm-x" onclick="closeCam()">&times;</span></div>' +
        '<div class="cm-info">\u041a\u0430\u043c\u0435\u0440\u0430: <b>' + esc(d.camera_name) + '</b> \u00b7 ' +
        '\u041a\u0430\u0434\u0440\u043e\u0432: <b>' + d.camera_count + '</b> \u00b7 ' +
        '\u0414\u0440\u0443\u0433\u0438\u0445: <b>' + d.other_count + '</b>' +
        ' \u2014 \u0442\u044f\u043d\u0438\u0442\u0435 \u043a\u0430\u0434\u0440 \u0441 \u0437\u043e\u043b\u043e\u0442\u043e\u0439 \u0440\u0430\u043c\u043a\u043e\u0439</div>' +
        '<div class="cm-strip-w"><div class="cm-strip" id="cmStrip">' + sh + '</div></div>' +
        '<div class="cm-bot">' +
        '<div class="cm-ir"><label>\u041f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u043e\u0435 \u0432\u0440\u0435\u043c\u044f:</label>' +
        '<input type="datetime-local" id="cmInput" value="' + (aOrig ? _j2i(aOrig) : '') + '">' +
        '<span class="dp-meta-sm">\u0418\u0441\u0445\u043e\u0434\u043d\u043e\u0435: ' + (aOrig ? _fd(aOrig) : '') + '</span></div>' +
        '<div class="cm-row"><span class="dp-meta-nowrap">\u0421\u0434\u0432\u0438\u0433:</span>' +
        '<input type="range" id="cmSlider" min="-86400" max="86400" step="60" value="0">' +
        '<span class="cm-sv" id="cmSv">+0\u043c</span></div>' +
        '<div class="cm-act"><button class="cm-no" onclick="closeCam()">\u041e\u0442\u043c\u0435\u043d\u0430</button>' +
        '<button class="cm-ok" onclick="_cmOk()">\u041f\u0440\u0438\u043c\u0435\u043d\u0438\u0442\u044c</button></div>' +
        '</div></div>';

    document.body.appendChild(m);
    _camInit();
}

function _camInit() {
    var sl = document.getElementById('cmSlider');
    var ip = document.getElementById('cmInput');
    var d = _camD;
    if (!d || !sl || !ip) return;
    var aOrig = _d2j(d.anchor_date);

    sl.addEventListener('input', function() {
        _camS = parseInt(sl.value, 10);
        if (aOrig) ip.value = _j2i(new Date(aOrig.getTime() + _camS * 1000));
        _camUpd();
    });

    ip.addEventListener('change', function() {
        var nt = new Date(ip.value);
        if (isNaN(nt) || !aOrig) return;
        _camS = Math.round((nt - aOrig) / 1000);
        _camS = Math.max(-86400, Math.min(86400, _camS));
        sl.value = _camS;
        _camUpd();
    });

    _camDragInit();
}

function _camUpd() {
    var d = _camD;
    if (!d) return;
    var sv = document.getElementById('cmSv');
    if (sv) sv.textContent = _fs(_camS);
    _camReorder();
}

function _camReorder() {
    var d = _camD;
    if (!d || !d._items) return;
    var strip = document.getElementById('cmStrip');
    if (!strip) return;

    var sorted = d._items.map(function(it) {
        var sh = it.cam ? new Date(it.d.getTime() + _camS * 1000) : it.d;
        var img = strip.querySelector('[data-k="' + it.i + '"]');
        var el = img ? (img.closest('.cm-item-wrap') || img) : null;
        if (el && it.cam) {
            var timeOnly = String(sh.getHours()).padStart(2,'0')+':'+String(sh.getMinutes()).padStart(2,'0')+':'+String(sh.getSeconds()).padStart(2,'0');
            var dateStr = sh.getFullYear()+'-'+String(sh.getMonth()+1).padStart(2,'0')+'-'+String(sh.getDate()).padStart(2,'0');
            var tEl = el.querySelector('.cm-cap-time');
            var dEl = el.querySelector('.cm-cap-date');
            var fEl = el.querySelector('.cm-cap-diff');
            if (tEl) tEl.textContent = timeOnly;
            if (dEl) dEl.textContent = dateStr;
            if (fEl && it.base) {
                var diffMn = (sh - it.base) / 60000;
                fEl.textContent = _fm(diffMn);
                fEl.className = _fmCls(diffMn);
            }
            if (img) img.dataset.time = _fd(sh);
        }
        return {el: el, d: sh};
    }).filter(function(x) { return x.el; });

    sorted.sort(function(a, b) { return a.d - b.d; });
    for (var k = 0; k < sorted.length; k++) strip.appendChild(sorted[k].el);

}

function _camDragInit() {
    var an = document.getElementById('cmAnc');
    var strip = document.getElementById('cmStrip');
    var d = _camD;
    if (!an || !strip || !d) return;
    var aOrig = _d2j(d.anchor_date);
    if (!aOrig) return;

    function start(e) {
        e.preventDefault(); e.stopPropagation();
        _camDrag = true; an.classList.add('drag');
        document.addEventListener('mousemove', mv);
        document.addEventListener('mouseup', en);
        document.addEventListener('touchmove', mv, {passive: false});
        document.addEventListener('touchend', en);
    }

    function mv(e) {
        if (!_camDrag) return;
        e.preventDefault();
        var cx = e.clientX !== undefined ? e.clientX : (e.touches && e.touches[0] ? e.touches[0].clientX : 0);
        var cy = e.clientY !== undefined ? e.clientY : (e.touches && e.touches[0] ? e.touches[0].clientY : 0);
        var rect = strip.getBoundingClientRect();
        var curX = cx - rect.left + strip.scrollLeft;
        var curY = cy - rect.top + strip.scrollTop;

        var others = strip.querySelectorAll('.cm-ph');
        var pos = [];
        for (var i = 0; i < others.length; i++) {
            var k = parseInt(others[i].dataset.k, 10);
            var it = null;
            for (var mi = 0; mi < d._items.length; mi++) { if (d._items[mi].i === k) { it = d._items[mi]; break; } }
            if (!it) continue;
            var wr = others[i].closest('.cm-item-wrap') || others[i];
            pos.push({c: wr.offsetLeft + wr.offsetWidth/2, y: wr.offsetTop + wr.offsetHeight/2, d: it.d});
        }
        pos.sort(function(a, b) { return a.c - b.c; });

        var pv = null, nx = null;
        for (var j = 0; j < pos.length; j++) {
            if (Math.abs(pos[j].y - curY) > 80) continue;
            if (pos[j].c <= curX) pv = pos[j];
            else { nx = pos[j]; break; }
        }

        var nt = null;
        if (pv && nx) {
            var r = (curX - pv.c) / (nx.c - pv.c);
            nt = new Date(pv.d.getTime() + r * (nx.d.getTime() - pv.d.getTime()));
        } else if (pv) nt = new Date(pv.d.getTime() + 60000);
        else if (nx) nt = new Date(nx.d.getTime() - 60000);

        if (nt) {
            _camS = Math.round((nt - aOrig) / 1000);
            _camS = Math.max(-86400, Math.min(86400, _camS));
            var sl = document.getElementById('cmSlider'); if (sl) sl.value = _camS;
            var ip = document.getElementById('cmInput'); if (ip) ip.value = _j2i(new Date(aOrig.getTime() + _camS * 1000));
            var sv = document.getElementById('cmSv'); if (sv) sv.textContent = _fs(_camS);
            _camReorder();
        }
    }

    function en() {
        _camDrag = false; an.classList.remove('drag');
        document.removeEventListener('mousemove', mv);
        document.removeEventListener('mouseup', en);
        document.removeEventListener('touchmove', mv);
        document.removeEventListener('touchend', en);
    }

    an.addEventListener('mousedown', start);
    an.addEventListener('touchstart', start, {passive: false});
}

function closeCam() {
    var m = document.getElementById('cmModal');
    if (m) m.remove();
    _camD = null;
}

function _cmOk() {
    var d = _camD;
    if (!d) return;
    var btn = document.querySelector('.cm-ok');
    if (btn) { btn.textContent = '\u0421\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0438\u0435...'; btn.disabled = true; }

    // Собираем время из подписей каждого кадра камеры
    var updates = [];
    var strip = document.getElementById('cmStrip');
    if (strip) {
        var cams = strip.querySelectorAll('.cm-cm, .cm-an');
        for (var i = 0; i < cams.length; i++) {
            var wrap = cams[i].closest('.cm-item-wrap');
            if (!wrap) continue;
            var tEl = wrap.querySelector('.cm-cap-time');
            var dEl = wrap.querySelector('.cm-cap-date');
            if (!tEl || !dEl) continue;
            var timeOnly = tEl.textContent;
            var dateStr = dEl.textContent;
            // dateStr = '2026-07-01', timeOnly = '15:14:17'
            var fullDate = dateStr + ' ' + timeOnly;
            var dbId = cams[i].dataset.k;
            // Найти UUID из _items
            for (var mi = 0; mi < d._items.length; mi++) {
                if (d._items[mi].i == dbId && d._items[mi].cam) {
                    updates.push({photo_id: d._items[mi].id, manual_date: fullDate});
                    break;
                }
            }
        }
    }

    if (!updates.length) {
        alert('\u041d\u0435\u0442 \u043a\u0430\u0434\u0440\u043e\u0432 \u043a\u0430\u043c\u0435\u0440\u044b');
        if (btn) { btn.textContent = '\u041f\u0440\u0438\u043c\u0435\u043d\u0438\u0442\u044c'; btn.disabled = false; }
        return;
    }

    var tzOffset = -new Date().getTimezoneOffset();

    fetch(API + '/albums/' + encodeURIComponent(d.album_id) + '/save_manual_dates', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({updates: updates, tz_offset: tzOffset})
    })
    .then(function(r) { return r.json(); })
    .then(function(r) {
        if (r.ok) {
            closeCam();
            if (typeof currentAlbum !== 'undefined' && currentAlbum)
                openAlbum(currentAlbum.album_id);
        } else {
            alert('\u041e\u0448\u0438\u0431\u043a\u0430: ' + (r.detail || ''));
            if (btn) { btn.textContent = '\u041f\u0440\u0438\u043c\u0435\u043d\u0438\u0442\u044c'; btn.disabled = false; }
        }
    })
    .catch(function(e) {
        alert('\u041e\u0448\u0438\u0431\u043a\u0430: ' + e.message);
        if (btn) { btn.textContent = '\u041f\u0440\u0438\u043c\u0435\u043d\u0438\u0442\u044c'; btn.disabled = false; }
    });
}

var _cmHoverTimer = null;
var _cmHoverEl = null;

function _cmHover(img) {
    if (_camDrag) return;
    _cmHoverEl = img;
    clearTimeout(_cmHoverTimer);
    _cmHoverTimer = setTimeout(function() { _cmShowHover(img); }, 300);
}

function _cmShowHover(img) {
    if (img !== _cmHoverEl) return;
    var full = img.dataset.full;
    var time = img.dataset.time;
    if (!full) return;
    var old = document.getElementById('cmPrev');
    if (old) old.remove();
    var p = document.createElement('div');
    p.id = 'cmPrev';
    p.className = 'cm-prev';
    p.style.display = 'block';
    p.innerHTML = '<img src="' + esc(full) + '" onerror="this.style.display=\'none\'">' +
        '<div class="cm-prev-info">' + esc(time || '') + '</div>';
    document.body.appendChild(p);
    var vw = window.innerWidth, vh = window.innerHeight;
    p.style.left = ((vw - p.offsetWidth) / 2) + 'px';
    p.style.bottom = '0';
    p.style.top = '';
}

function _cmHoverEnd() {
    _cmHoverEl = null;
    clearTimeout(_cmHoverTimer);
    var p = document.getElementById('cmPrev');
    if (p) p.remove();
}

var _addToAlbumPhotoId = null;

function showAddToAlbum(photoId) {
    _addToAlbumPhotoId = photoId;
    var old = document.getElementById('addToAlbumModal');
    if (old) old.remove();
    var m = document.createElement('div');
    m.id = 'addToAlbumModal';
    m.className = 'album-create-modal show';
    m.innerHTML = '<div class="album-create-box" onclick="event.stopPropagation()">' +
        '<h3>Добавить в альбом</h3>' +
        '<div id="addToAlbumList" style="max-height:300px;overflow-y:auto;margin-bottom:12px">Загрузка...</div>' +
        '<div class="acm-btns">' +
        '<button class="btn-secondary" onclick="closeAddToAlbum()">Отмена</button>' +
        '</div></div>';
    m.onclick = closeAddToAlbum;
    document.body.appendChild(m);
    loadAddToAlbumList();
}

function closeAddToAlbum() {
    var m = document.getElementById('addToAlbumModal');
    if (m) m.remove();
    _addToAlbumPhotoId = null;
}

async function loadAddToAlbumList() {
    var resp = await fetch('/api/albums/?source=manual');
    var albums = await resp.json();
    var el = document.getElementById('addToAlbumList');
    if (!el) return;
    if (!albums.length) {
        el.innerHTML = '<p class="dp-muted-sm">Нет ручных альбомов. Создайте альбом на странице Альбомы.</p>';
        return;
    }
    var html = '';
    for (var i = 0; i < albums.length; i++) {
        var a = albums[i];
        html += '<label class="album-pick-row"><input type="checkbox" value="' + esc(a.album_id) + '" style="cursor:pointer">' +
            '<span>' + esc(a.title) + ' <span class="dp-muted-sm">(' + a.photo_count + ')</span></span>' +
            '</label>';
    }
    html += '<button style="margin-top:12px;width:100%" onclick="submitAddToAlbum()">Добавить в выбранные</button>';
    el.innerHTML = html;
}

async function submitAddToAlbum() {
    if (!_addToAlbumPhotoId) return;
    var checkboxes = document.querySelectorAll('#addToAlbumList input[type=checkbox]:checked');
    var albumIds = [];
    for (var i = 0; i < checkboxes.length; i++) albumIds.push(checkboxes[i].value);
    if (!albumIds.length) return;
    var added = 0;
    for (var j = 0; j < albumIds.length; j++) {
        var resp = await fetch('/api/albums/' + encodeURIComponent(albumIds[j]) + '/photos', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({photo_ids: [_addToAlbumPhotoId]})
        });
        var data = await resp.json();
        if (data.ok) added++;
    }
    closeAddToAlbum();
}

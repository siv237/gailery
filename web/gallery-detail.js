function updateNeedleFlag(dateStr) {
    var flag = document.getElementById('tlNeedleFlag');
    var needle = document.getElementById('tlNeedle');
    if (!flag) return;
    if (!dateStr) { flag.textContent = ''; return; }
    if (needle) needle.style.opacity = '1';
    var p = dateStr.substring(0, 10).split('-');
    if (p.length === 3) {
        var text = p[2] + '.' + p[1] + '.' + p[0];
        var timePart = dateStr.substring(11, 16);
        if (timePart && timePart !== '00:0' && timePart !== '00:00') text += ' ' + timePart;
        else if (_tlZoom > 5000) text += ' 00:00';
        flag.textContent = text;
    } else {
        flag.textContent = dateStr.substring(0, 10);
    }
}

function selectYear(year) {
    activeDate = year ? (year + '-01-01') : '';
    updateNeedleFlag(activeDate);
    var needle = document.getElementById('tlNeedle');
    if (needle && year) {
        needle.style.transition = 'left .4s ease-out';
        needle.style.left = _fracToX(parseInt(year)) + 'px';
    }
    doSearch();
}

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
          html = '<video class="dp-img" id="detailVideo" src="' + vidUrl + '" controls preload="metadata" style="width:100%;max-height:400px;background:#000;border-radius:4px"></video>';
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
        html += '<button id="enrichBtn" onclick="enrichPhoto(\'' + esc(p.db_id || '') + '\')" style="padding:4px 12px;background:#238636;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;font-family:monospace;margin-right:4px">' + (p.rich_description ? 'Обновить описание' : 'Обогатить описание') + '</button>';
        html += '<button onclick="showCustomDesc(\'' + esc(p.db_id || '') + '\')" style="padding:4px 12px;background:#1f6feb;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;font-family:monospace">Своё описание</button>';
        html += '</div>';
    }
    html += '<div style="margin-top:6px">';
    html += '<button onclick="showReprocessModal(\'' + esc(p.db_id || '') + '\')" style="padding:4px 12px;background:#6e40c9;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;font-family:monospace">Переобработать</button>';
    html += '</div>';
    if (p.date) {
        var showDate = p.manual_date || p.date;
        html += '<div class="dp-meta" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">Дата: ' + formatDate(showDate);
        if (p.manual_date) {
            html += ' <span class="manual-date-badge" onclick="showDateEdit()">ручная</span>';
            html += ' <span class="dp-date-btn dp-date-clear" onclick="clearPhotoDate(\'' + esc(p.photo_id) + '\')">✕</span>';
        } else {
            html += ' <span class="dp-date-btn" onclick="showDateEdit()">Изменить</span>';
        }
        html += '</div>';
        if (p.original_date && p.manual_date) html += '<div class="dp-meta" style="color:#6e7681">EXIF дата: ' + formatDate(p.original_date) + '</div>';
        html += '<div id="dateEditArea" style="display:none;margin:2px 0 6px">';
        html += '<div style="display:flex;align-items:center;gap:4px">';
        html += '<input type="datetime-local" id="manualDateInput" class="dp-date-input" value="">';
        html += '<button onclick="setPhotoDate(\'' + esc(p.photo_id) + '\')" class="dp-date-save">Задать</button>';
        html += '<button onclick="hideDateEdit()" class="dp-date-cancel">Отмена</button>';
        html += '</div></div>';
    }
    if (p.is_raw) html += '<div class="dp-meta" style="color:#f0883e;font-weight:600">RAW</div>';
    var _fakeCam = /^(h264|h265|hevc|mjpeg|mpeg4|vp[89]|av1|aac|mp4a|pcm|opus|vp9|theora|flac)$/i;
    var _camMake = p.camera_make || '';
    var _camModel = p.camera_model || '';
    if (_fakeCam.test(_camMake)) _camMake = '';
    if (_fakeCam.test(_camModel)) _camModel = '';
    if (p.media_type !== 'video' && (_camMake || _camModel)) html += '<div class="dp-meta">Камера: ' + esc(_camMake + ' ' + _camModel) + '</div>';
    if (p.media_type === 'video') {
        html += '<div id="videoMetaArea"><div class="dp-meta" style="color:#6e7681">Загрузка метаданных…</div></div>';
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
                if (m.creation_time) h += '<div class="dp-meta">Дата записи: <b>' + esc(m.creation_time) + '</b></div>';
                if (m.camera) h += '<div class="dp-meta">Камера: ' + esc(m.camera) + '</div>';
                if (m.video_codec) h += '<div class="dp-meta">Видео: ' + esc(m.video_codec) + (m.pix_fmt ? ' ' + esc(m.pix_fmt) : '') + '</div>';
                if (m.audio_codec) {
                    var ai = esc(m.audio_codec);
                    if (m.audio_sample_rate) ai += ' ' + m.audio_sample_rate + 'Hz';
                    if (m.audio_channels) ai += ' ' + m.audio_channels + 'ch';
                    h += '<div class="dp-meta">Аудио: ' + ai + '</div>';
                } else {
                    h += '<div class="dp-meta" style="color:#f0883e">Аудио: нет</div>';
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
                    h += '<div style="color:#58a6ff;font-size:11px;cursor:pointer;padding:2px 0;border-bottom:1px solid #21262d" onclick="var el=document.getElementById(\'vtagBrand\');el.style.display=el.style.display===\'none\'?\'block\':\'none\'">Контейнер теги (' + brandItems.length + ') ▾</div>';
                    h += '<div id="vtagBrand" style="display:none;padding-left:8px">';
                    for (var bi = 0; bi < brandItems.length; bi++) h += '<div class="dp-meta">' + brandItems[bi] + '</div>';
                    h += '</div></div>';
                }
                if (tagItems.length > 0) {
                    h += '<div style="margin-top:6px">';
                    h += '<div style="color:#58a6ff;font-size:11px;cursor:pointer;padding:2px 0;border-bottom:1px solid #21262d" onclick="var el=document.getElementById(\'vtagOther\');el.style.display=el.style.display===\'none\'?\'block\':\'none\'">Метаданные (' + tagItems.length + ') ▾</div>';
                    h += '<div id="vtagOther" style="display:none;padding-left:8px">';
                    for (var oi = 0; oi < tagItems.length; oi++) h += '<div class="dp-meta">' + tagItems[oi] + '</div>';
                    h += '</div></div>';
                }
            }
                el.innerHTML = h;
            }).catch(function(){
                var el = document.getElementById('videoMetaArea');
                if (el) el.innerHTML = '<div class="dp-meta" style="color:#f0883e">Метаданные недоступны</div>';
            });
        })();
    }
    html += '<div class="dp-meta">Лица: ' + p.total_faces + '</div>';
    if (p.photo_type && p.photo_type !== 'photo') html += '<div class="dp-meta">Тип: ' + esc(p.photo_type) + '</div>';
    if (p.has_issues) html += '<div class="dp-meta" style="color:#f85149">Проблемы: ' + esc(p.issue_type || 'да') + '</div>';
    if (p.deleted) {
        html += '<div class="dp-meta" style="color:#f85149;font-weight:600">Удалена</div>';
        html += '<button onclick="undeletePhoto(\'' + esc(p.photo_id) + '\')" style="padding:4px 12px;background:#238636;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;font-family:monospace;margin:4px 0">Восстановить</button>';
    }
    html += '<div class="dp-meta">Семантическая индексация: ' + (p.embedded ? 'да' : 'нет') + '</div>';
    if (p.content_hash) html += '<div class="dp-meta dp-hash" style="word-break:break-all;display:flex;align-items:center;gap:6px"><span style="color:#6e7681">Хеш:</span> <span>' + esc(p.content_hash) + '</span> <button class="copy-hash-btn" data-hash="' + esc(p.content_hash) + '" onclick="var t=document.createElement(\'textarea\');t.value=this.dataset.hash;document.body.appendChild(t);t.select();document.execCommand(\'copy\');document.body.removeChild(t);this.textContent=\'✓\';var b=this;setTimeout(function(){b.textContent=\'📋\'},1000)">📋</button></div>';
    html += '<div class="dp-meta" style="word-break:break-all">Путь: ' + esc(p.photo_id || p.path) + '</div>';
    var allPaths = [p.path];
    if (p.duplicate_paths && p.duplicate_paths.length > 0) {
        html += '<div class="dp-meta" style="margin-top:6px;color:#f0883e">Дубликаты (' + p.duplicate_paths.length + '):</div>';
        for (var di = 0; di < p.duplicate_paths.length; di++) {
            var dp = p.duplicate_paths[di].replace(/\\/g,'/');
            allPaths.push(dp);
            var short = dp.split('/').slice(-3).join('/');
            html += '<div class="dp-meta" style="padding-left:10px;word-break:break-all;color:#8b949e" title="' + esc(dp) + '">' + esc(short) + '</div>';
        }
    }
    html += '<div class="dp-meta" style="margin-top:6px">';
    for (var ai = 0; ai < allPaths.length; ai++) {
        var ap = allPaths[ai].replace(/\\/g,'/');
        var ashort = ap.split('/').slice(-2).join('/');
        html += '<a href="#" onclick="goToCatalog(\'' + esc(ap) + '\');return false" style="color:#58a6ff;margin-right:10px" title="' + esc(ap) + '">📂 ' + esc(ashort) + '</a>';
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
                    '<a href="' + gUrl + '" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:5px;color:#58a6ff;text-decoration:none;background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:4px 8px;font-size:11px">' +
                    '<span style="font-weight:bold;font-size:14px"><span style="color:#4285F4">G</span><span style="color:#EA4335">o</span><span style="color:#FBBC05">o</span><span style="color:#4285F4">g</span><span style="color:#34A853">l</span><span style="color:#EA4335">e</span></span> Maps</a>' +
                    '<a href="' + yUrl + '" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:5px;color:#58a6ff;text-decoration:none;background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:4px 8px;font-size:11px">' +
                    '<span style="font-weight:bold;font-size:15px;color:#FC3F1D">Я</span>ndex Карты</a>' +
                    '</div>'
                );
            }

            var gid = 0;
            for (var gName in grouped) {
                var gId = 'exifGrp_' + gid;
                html += '<div style="margin-top:6px">';
                html += '<div style="color:#58a6ff;font-size:11px;cursor:pointer;padding:2px 0;border-bottom:1px solid #21262d" onclick="var el=document.getElementById(\'' + gId + '\');el.style.display=el.style.display===\'none\'?\'block\':\'none\'">' + esc(gName) + ' (' + grouped[gName].length + ') ▾</div>';
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
        html += '<div class="dp-personas"><div style="color:#8b949e;font-size:10px;margin-bottom:4px">Персоны (нажмите для редактирования):</div>';
        for (var j = 0; j < p.personas.length; j++) {
            var per = p.personas[j];
            var fid = (per.face_ids && per.face_ids.length > 0) ? per.face_ids[0] : '';
            var hasName = per.display_name ? true : false;
            var cls = hasName ? 'dp-pchip has-name' : 'dp-pchip';
            html += '<div class="' + cls + '" onclick="openFaceModal(\'' + esc(per.persona_id) + '\',\'' + esc(fid) + '\')">';
            if (fid) html += '<img src="' + API + '/photos/face/' + fid + '?margin=0.5" loading="lazy">';
            html += '<span class="nm">' + esc(per.display_name || per.name) + '</span>';
            if (per.comment) html += '<span class="cm" style="font-size:9px;color:#8b949e;margin-left:2px">' + esc(per.comment) + '</span>';
            html += '</div>';
        }
        html += '</div>';
    }

    html += '<div style="margin-top:12px"><button style="background:#238636;color:#fff;border:none;padding:6px 14px;border-radius:4px;cursor:pointer;font-size:12px" onclick="openFullPhoto(\'' + esc(p.media_type === 'video' ? vidUrl : photoUrl) + '\')">Открыть полное фото</button></div>';

     document.getElementById('dpContent').innerHTML = html;
     document.getElementById('detailPanel').classList.add('show');
     if (_isMobile()) document.documentElement.classList.add('scroll-lock');
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

var _dpRot = 0;
var _dpIdx = -1;
var _dpHash = '';
var _flirMode = 'thermal';

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
                    '<button class="btn-save" onclick="acceptRich(\'' + esc(photoId) + '\')">Сохранить</button>' +
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
        '<button class="btn-save" onclick="saveCustomDesc(\'' + esc(photoId) + '\')">Сохранить</button>' +
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

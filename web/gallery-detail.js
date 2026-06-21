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

function openFullPhoto(url) {
    openViewer(currentPhotos.findIndex(function(p) { return videoSrc(p) === url || (API + '/photos/?path=' + encodeURIComponent(p.photo_id)) === url; }));
}

var _mZoom = 1, _mPx = 0, _mPy = 0, _mDrag = false, _mDX = 0, _mDY = 0, _mDate = '', _mPhotoId = '', _mRot = 0, _mIdx = -1, _mCoverMode = false;
var _ssDir = 0, _ssTimer = null;
var _imgCache = {};

function _cacheImg(idx) {
    if (idx < 0 || idx >= currentPhotos.length) return;
    var p = currentPhotos[idx];
    if (p.media_type === 'video') return;
    var url = p.photo_id ? (API + '/photos/?path=' + encodeURIComponent(p.photo_id)) : '';
    if (url && !_imgCache[url]) {
        var img = new Image();
        img.src = url;
        _imgCache[url] = img;
    }
}

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

function rotatePhoto(deg) {
    var p = currentPhotos[_mIdx];
    if (!p) return;
    _mRot = _mRot + deg;
    var wrap = document.getElementById('modalImgWrap');
    if (wrap) {
        var zoomT = _mZoom !== 1 ? ' scale(' + _mZoom + ')' : '';
        var panT = (_mPx || _mPy) ? ' translate(' + _mPx + 'px,' + _mPy + 'px)' : '';
        wrap.style.transform = 'rotate(' + _mRot + 'deg)' + zoomT + panT;
    }
    var saveAngle = ((_mRot % 360) + 360) % 360;
    saveRotate(p.content_hash, saveAngle);
    setTimeout(_positionModalControls, 50);
}

var _dpRot = 0;
var _dpIdx = -1;
var _dpHash = '';
var _flirMode = 'thermal';
var _mFlirMode = 'thermal';

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

var _flirVisImg = new Image();
var _flirThImg = new Image();
var _flirOX = 219, _flirOY = 141;
var _flirScale = 1.5;
var _flirDrag = false, _flirDX = 0, _flirDY = 0;
var _flirStartX = 0, _flirStartY = 0;
var _flirScaleCorner = null;
var _flirToken = 0;
var _flirProbes = [];

function setModalFlir(mode) {
    _mFlirMode = mode;
    var p = currentPhotos[_mIdx];
    if (!p || !p.is_flir) return;
    var pid = encodeURIComponent(p.photo_id);
    var img = document.getElementById('photoModalImg');
    var cvs = document.getElementById('photoModalCanvas');
    var flirCtrl = document.getElementById('flirOverlayControls');
    if (!img || !cvs) return;
    if (mode === 'overlay') {
        img.style.display = 'none';
        cvs.style.display = 'block';
        flirCtrl.style.display = 'inline-flex';
        _flirToken++;
        var tok = _flirToken;
        _flirVisImg.onload = function() {
            if (tok !== _flirToken) return;
            if (_flirThImg.complete && _flirThImg.naturalWidth > 0) drawFlirOverlay();
            else _flirThImg.onload = function() { if (tok === _flirToken) drawFlirOverlay(); };
        };
        var ts = Date.now();
        _flirVisImg.src = API + '/photos/flir_visual?path=' + pid + '&_t=' + ts;
        _flirThImg.src = API + '/photos/flir_raw_palette?path=' + pid + '&_t=' + ts;
    } else {
        img.style.display = 'block';
        cvs.style.display = 'none';
        flirCtrl.style.display = 'none';
        _flirToken++;
        if (mode === 'thermal') {
            img.src = API + '/photos/?path=' + pid;
        } else if (mode === 'visual') {
            img.src = API + '/photos/flir_visual?path=' + pid;
        }
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
    var wrap = document.getElementById('modalImgWrap');
    if (!cvs || !_flirVisImg.complete || !_flirThImg.complete) return;
    var alpha = parseFloat(document.getElementById('flirA').value) || 0.5;
    document.getElementById('flirAv').textContent = alpha.toFixed(2);
    var vw = _flirVisImg.naturalWidth || 1440;
    var vh = _flirVisImg.naturalHeight || 1080;
    var tw = _flirThImg.naturalWidth || 640;
    var th = _flirThImg.naturalHeight || 480;
    cvs.width = vw;
    cvs.height = vh;
    var ctx = cvs.getContext('2d');
    ctx.clearRect(0, 0, vw, vh);
    ctx.drawImage(_flirVisImg, 0, 0, vw, vh);
    var sw = Math.round(tw * _flirScale);
    var sh = Math.round(th * _flirScale);
    ctx.globalAlpha = alpha;
    ctx.drawImage(_flirThImg, _flirOX, _flirOY, sw, sh);
    ctx.globalAlpha = 1.0;
    ctx.strokeStyle = '#0f0';
    ctx.lineWidth = 1;
    ctx.strokeRect(_flirOX, _flirOY, sw, sh);
    var hs = 6;
    ctx.fillStyle = '#0f0';
    [
        [_flirOX, _flirOY],
        [_flirOX + sw, _flirOY],
        [_flirOX, _flirOY + sh],
        [_flirOX + sw, _flirOY + sh]
    ].forEach(function(p) {
        ctx.fillRect(p[0] - hs/2, p[1] - hs/2, hs, hs);
    });
    cvs.style.width = '100%';
    cvs.style.height = '100%';
    // draw probes
    ctx.font = '12px monospace';
    ctx.lineWidth = 2;
    for (var i = 0; i < _flirProbes.length; i++) {
        var pr = _flirProbes[i];
        var px = _flirOX + pr.tx * _flirScale;
        var py = _flirOY + pr.ty * _flirScale;
        ctx.fillStyle = '#ff0';
        ctx.beginPath();
        ctx.arc(px, py, 4, 0, 2*Math.PI);
        ctx.fill();
        var txt = pr.temp + '\u00B0C';
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 3;
        ctx.strokeText(txt, px + 8, py + 4);
        ctx.fillStyle = '#000';
        ctx.lineWidth = 1;
        ctx.fillText(txt, px + 8, py + 4);
    }
}

function slideshowToggle(dir) {
     _ssDir = dir;
     clearInterval(_ssTimer);
     _ssTimer = null;
     document.getElementById('modalTopbar').classList.add('playing');
     _clearFaceBoxes();
     var p = currentPhotos[_mIdx];
     var vid = document.getElementById('photoModalVideo');
      if (p && p.media_type === 'video' && vid) {
          vid.onended = function() {
              if (_ssDir !== 0) slideshowAdvance();
          };
          if (vid.paused) vid.play().catch(function(){});
      } else {
          _ssTimer = setInterval(function() { slideshowAdvance(); }, 5000);
      }
      _syncTimelineToPhoto();
 }

  function _slideshowOpen(newIdx) {
      if (newIdx < 0 || newIdx >= currentPhotos.length) return;
      openViewer(newIdx);
      _clearFaceBoxes();
      _cacheImg(newIdx + _ssDir);
      _cacheImg(newIdx + _ssDir * 2);
      _syncTimelineToPhoto();
      var p = currentPhotos[newIdx];
      clearInterval(_ssTimer);
      _ssTimer = null;
      if (p && p.media_type !== 'video') {
          _ssTimer = setInterval(function() { slideshowAdvance(); }, 5000);
      }
  }

  function slideshowAdvance() {
      if (_ssDir === 0) return;
      var newIdx = _mIdx + _ssDir;
      if (newIdx < 0) {
          if (_canLoadPrev && !_isLoading && _ssDir < 0 && _firstDate) {
              loadBefore(_firstDate, _firstPath, function(batch) {
                  if (_ssDir !== 0 && batch.length > 0) {
                      _mIdx += batch.length;
                      newIdx = _mIdx + _ssDir;
                      if (newIdx >= 0 && newIdx < currentPhotos.length) _slideshowOpen(newIdx);
                  }
              });
          } else {
              slideshowStop();
          }
          return;
      }
      if (newIdx >= currentPhotos.length) {
          if (_canLoadMore && !_isLoading) {
              loadAfter(_lastDate, _lastPath, false, false, function() {
                  if (_ssDir !== 0 && newIdx < currentPhotos.length) _slideshowOpen(newIdx);
              });
          } else {
              slideshowStop();
          }
          return;
      }
      _slideshowOpen(newIdx);
  }

 function slideshowStop() {
     _ssDir = 0;
     clearInterval(_ssTimer);
     _ssTimer = null;
     document.getElementById('modalTopbar').classList.remove('playing');
     var p = currentPhotos[_mIdx];
     var vid = document.getElementById('photoModalVideo');
     if (vid) { vid.onended = null; }
     if (p && p.media_type !== 'video') {
         var img = document.getElementById('photoModalImg');
         if (img) _drawFaceBoxes(p, img);
     }
 }

function openViewer(idx) {
    if (idx < 0 || idx >= currentPhotos.length) return;
    _modalOpen = true;
    closeDetail();
    _mIdx = idx;
    var p = currentPhotos[idx];
    _mDate = p.date || '';
    _mPhotoId = p.photo_id || '';
    var url = videoSrc(p);
    var img = document.getElementById('photoModalImg');
    var vid = document.getElementById('photoModalVideo');
    var wrap = document.getElementById('modalImgWrap');
    var isVideo = p.media_type === 'video';

    // Clean previous video ended handler
    vid.onended = null;
    // Hide FLIR canvas when opening new photo
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
                var pctX = ((fx1 + fx2) / 2 / natW * 100).toFixed(1);
                var pctY = ((fy1 + fy2) / 2 / natH * 100).toFixed(1);
                vid.style.objectPosition = pctX + '% ' + pctY + '%';
            }
        } else {
            vid.style.objectPosition = '';
        }
    } else {
        vid.style.display = 'none';
        vid.src = '';
        img.style.display = 'block';
        img.src = url;
        img.classList.remove('cover');
        vid.classList.remove('cover');
        wrap.classList.remove('cover-wrap');
        img.style.objectPosition = '';
    }

          wrap.style.transform = _mRot ? 'rotate(' + _mRot + 'deg)' : '';
     _mZoom = 1; _mPx = 0; _mPy = 0;
     _mRot = 0;
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
     if (p.camera_make || p.camera_model) txt += '<span class="modal-cam">' + esc((p.camera_make || '') + ' ' + (p.camera_model || '')) + '</span>';
      document.getElementById('modalDate').innerHTML = txt;
      var flirBar = document.getElementById('modalFlirBar');
      if (p.is_flir) {
          flirBar.style.display = '';
          _mFlirMode = 'thermal';
          var flirBtns = flirBar.querySelectorAll('.flir-mbtn');
          for (var fi = 0; fi < flirBtns.length; fi++) flirBtns[fi].classList.remove('active');
          if (flirBtns[0]) flirBtns[0].classList.add('active');
      } else {
          flirBar.style.display = 'none';
      }
      updateModalGps(p);
     var delBtn = document.getElementById('modalDelBtn');
     if (p.deleted) {
         delBtn.innerHTML = '&#8634;';
         delBtn.title = 'Восстановить';
         delBtn.onclick = function() { undeletePhoto(p.photo_id); updateModalDel(p); };
     } else {
         delBtn.innerHTML = '&#128465;';
         delBtn.title = 'Удалить';
         delBtn.onclick = function() { markDeleted(p.photo_id); };
     }
    var modal = document.getElementById('photoModal');
    modal.classList.add('show');
    var isMobile = _isMobile();
    var keepFs = modal.classList.contains('fs') || !!document.fullscreenElement;
    if (isMobile || keepFs) {
        modal.classList.add('fs');
    } else {
        modal.classList.remove('fs');
    }

    var overlays = document.getElementById('faceOverlays');
    if (isVideo) {
        _clearFaceBoxes();
        overlays.style.display = 'none';
    } else {
        overlays.style.display = 'block';
        _drawFaceBoxes(p, img);
    }
    // FLIR overlay canvas drag/scale/probe
    var cvs = document.getElementById('photoModalCanvas');
    cvs.onmousedown = function(e) {
        if (_mFlirMode !== 'overlay') return;
        var r = cvs.getBoundingClientRect();
        var px = (e.clientX - r.left) * (cvs.width / r.width);
        var py = (e.clientY - r.top) * (cvs.height / r.height);
        var tw = _flirThImg.naturalWidth || 640;
        var th = _flirThImg.naturalHeight || 480;
        var sw = Math.round(tw * _flirScale);
        var sh = Math.round(th * _flirScale);
        var hit = 15;
        var corners = [
            {cx:_flirOX, cy:_flirOY, corner:'tl'},
            {cx:_flirOX+sw, cy:_flirOY, corner:'tr'},
            {cx:_flirOX, cy:_flirOY+sh, corner:'bl'},
            {cx:_flirOX+sw, cy:_flirOY+sh, corner:'br'}
        ];
        _flirScaleCorner = null;
        for (var i = 0; i < corners.length; i++) {
            if (Math.abs(px - corners[i].cx) < hit && Math.abs(py - corners[i].cy) < hit) {
                _flirScaleCorner = corners[i].corner;
                break;
            }
        }
        _flirDrag = true;
        _flirDX = e.clientX;
        _flirDY = e.clientY;
        _flirStartX = e.clientX;
        _flirStartY = e.clientY;
        if (_flirScaleCorner) {
            cvs.style.cursor = 'nwse-resize';
        } else {
            cvs.style.cursor = 'grabbing';
        }
    };
    cvs.onmouseup = function(e) {
        if (_mFlirMode !== 'overlay') return;
        var dist = Math.abs(e.clientX - _flirStartX) + Math.abs(e.clientY - _flirStartY);
        if (dist < 5 && !_flirScaleCorner) {
            _flirProbeClick(e);
        }
    };

    _cacheImg(idx + 1);
    _cacheImg(idx - 1);
    _cacheImg(idx + 2);
    // FLIR overlay canvas drag move/up
    window.onmousemove = _flirOnMove;
    window.onmouseup = _flirOnUp;

    if (isVideo) {
        // Always autoplay video
        vid.play().catch(function(){});
        // In slideshow: stop fixed timer and advance on ended
        if (_ssDir !== 0) {
            clearInterval(_ssTimer);
            _ssTimer = null;
            vid.onended = function() {
                if (_ssDir !== 0) slideshowAdvance();
            };
        }
        if (_mCoverMode) _updateFitIcon(p, true);
        function onVidMeta() {
            requestAnimationFrame(_positionModalControls);
            vid.removeEventListener('loadedmetadata', onVidMeta);
        }
        if (vid.readyState >= 1) { requestAnimationFrame(_positionModalControls); }
        else { vid.addEventListener('loadedmetadata', onVidMeta); }
        setTimeout(_positionModalControls, 200);
    } else if (isMobile || _mCoverMode) {
        function onImgReady() {
            if (img.complete && img.naturalWidth) {
                smartFit();
                img.removeEventListener('load', onImgReady);
            }
        }
        if (img.complete && img.naturalWidth) { smartFit(); }
        else { img.addEventListener('load', onImgReady); }
    } else {
        function onImgPos() {
            requestAnimationFrame(_positionModalControls);
            img.removeEventListener('load', onImgPos);
        }
        if (img.complete && img.naturalWidth) { requestAnimationFrame(_positionModalControls); }
        else { img.addEventListener('load', onImgPos); }
    }
    _syncTimelineToPhoto();
    var card = p.photo_id ? document.querySelector('.card[data-photo-id="' + CSS.escape(p.photo_id) + '"]') : null;
    if (card) card.scrollIntoView({block:'center', behavior:'smooth'});
}

function updateModalGps(p) {
    var locEl = document.getElementById('modalLoc');
    var sepEl = locEl ? locEl.previousElementSibling : null;
    if (!p) return;
    if (p.gps_lat && p.gps_lon) {
        var html = '';
        if (p.manual_gps) {
            html += '<span class="modal-gps-manual">ручная</span>';
            html += '<span class="modal-gps" onclick="goToGps(' + p.gps_lat + ',' + p.gps_lon + ')">GPS</span>';
            html += '<span class="modal-clear-gps" onclick="clearPhotoGps(\'' + esc(p.photo_id) + '\')">✕</span>';
        } else {
            html += '<span class="modal-gps" onclick="goToGps(' + p.gps_lat + ',' + p.gps_lon + ')">GPS</span>';
        }
        locEl.innerHTML = html;
        locEl.style.display = '';
        if (sepEl) sepEl.style.display = '';
    } else {
        if (p.photo_id) {
            locEl.innerHTML = '<span class="modal-add-gps" onclick="addPhotoGps(\'' + esc(p.photo_id) + '\')">📍 Карта</span>';
            locEl.style.display = '';
            if (sepEl) sepEl.style.display = '';
        } else {
            locEl.innerHTML = '';
            locEl.style.display = 'none';
            if (sepEl) sepEl.style.display = 'none';
        }
    }
}

function _drawFaceBoxes(p, img) {
    var ov = document.getElementById('faceOverlays');
    ov.innerHTML = '';
    var faces = p.faces || [];
    if (!faces.length) return;
    function doDraw() {
        if (img.classList.contains('cover')) {
            _drawFaceBoxesCover(p, img);
            return;
        }
        var dispW = img.clientWidth;
        var dispH = img.clientHeight;
        if (!dispW || !dispH) return;
        var natW = img.naturalWidth || p.img_width || 1;
        var natH = img.naturalHeight || p.img_height || 1;
        var scaleX = dispW / natW;
        var scaleY = dispH / natH;
        var html = '';
        for (var i = 0; i < faces.length; i++) {
            var f = faces[i];
            if (f.bbox_x1 == null) continue;
            var x1 = f.bbox_x1 * scaleX;
            var y1 = f.bbox_y1 * scaleY;
            var x2 = f.bbox_x2 * scaleX;
            var y2 = f.bbox_y2 * scaleY;
            var name = f.display_name || f.name || '';
            html += '<div class="face-box" style="left:' + x1 + 'px;top:' + y1 + 'px;width:' + (x2 - x1) + 'px;height:' + (y2 - y1) + 'px"';
            if (f.persona_id) html += ' onclick="event.stopPropagation();openFaceModal(\'' + esc(f.persona_id) + '\',\'' + esc(f.face_id) + '\')"';
            html += '>';
            if (name) html += '<div class="face-box-label">' + esc(name) + '</div>';
            html += '</div>';
        }
         ov.innerHTML = html;
     if (_mZoom > 1) applyModalTransform();
         if (_mZoom > 1) applyModalTransform();
     }
     if (img.complete && img.naturalWidth) {
         doDraw();
     } else {
         img.addEventListener('load', doDraw, {once: true});
     }
 }

 function _clearFaceBoxes() {
     document.getElementById('faceOverlays').innerHTML = '';
 }

 function _drawFaceBoxesCover(p, img) {
     var ov = document.getElementById('faceOverlays');
     ov.innerHTML = '';
     var faces = p.faces || [];
     if (!faces.length) return;
     var dispW = img.clientWidth;
     var dispH = img.clientHeight;
     if (!dispW || !dispH) return;
     var natW = img.naturalWidth || p.img_width || 1;
     var natH = img.naturalHeight || p.img_height || 1;
     var scale = Math.max(dispW / natW, dispH / natH);
     var renderedW = natW * scale;
     var renderedH = natH * scale;
     var offX = (dispW - renderedW) / 2;
     var offY = (dispH - renderedH) / 2;
     var pos = img.style.objectPosition || '50% 50%';
     var posParts = pos.split(/\s+/);
     var pxPct = parseFloat(posParts[0]) / 100;
     var pyPct = parseFloat(posParts[1]) / 100;
     if (renderedW > dispW) offX = -(renderedW - dispW) * pxPct;
     if (renderedH > dispH) offY = -(renderedH - dispH) * pyPct;
     var html = '';
     for (var i = 0; i < faces.length; i++) {
         var f = faces[i];
         if (f.bbox_x1 == null) continue;
          var x1 = offX + f.bbox_x1 * scale;
          var y1 = offY + f.bbox_y1 * scale;
          var x2 = offX + f.bbox_x2 * scale;
          var y2 = offY + f.bbox_y2 * scale;
         if (x2 < 0 || y2 < 0 || x1 > dispW || y1 > dispH) continue;
         x1 = Math.max(0, x1); y1 = Math.max(0, y1);
         x2 = Math.min(dispW, x2); y2 = Math.min(dispH, y2);
         var name = f.display_name || f.name || '';
         html += '<div class="face-box" style="left:' + x1 + 'px;top:' + y1 + 'px;width:' + (x2 - x1) + 'px;height:' + (y2 - y1) + 'px"';
         if (f.persona_id) html += ' onclick="event.stopPropagation();openFaceModal(\'' + esc(f.persona_id) + '\',\'' + esc(f.face_id) + '\')"';
         html += '>';
         if (name) html += '<div class="face-box-label">' + esc(name) + '</div>';
         html += '</div>';
     }
     ov.innerHTML = html;
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

function modalNav(dir) {
    var newIdx = _mIdx + dir;
    if (newIdx < 0) {
        if (_canLoadPrev && !_isLoading && dir < 0 && _firstDate) {
            loadBefore(_firstDate, _firstPath, function(batch) {
                if (batch.length > 0) {
                    _mIdx += batch.length;
                    newIdx = _mIdx + dir;
                    if (newIdx >= 0 && newIdx < currentPhotos.length) {
                        _mIdx = newIdx;
                        openViewer(newIdx);
                    }
                }
            });
        }
        return;
    }
    if (newIdx >= currentPhotos.length) {
        if (_canLoadMore && !_isLoading && dir > 0) {
            loadAfter(_lastDate, _lastPath, false, false, function() {
                if (newIdx < currentPhotos.length) {
                    _mIdx = newIdx;
                    openViewer(newIdx);
                }
            });
        }
        return;
    }
    _mIdx = newIdx;
    openViewer(newIdx);
}

function formatDate(ds) {
    if (!ds) return '';
    var p = ds.substring(0, 19).replace('T', ' ');
    return p.replace(/^(\d{4})[:\-](\d{2})[:\-](\d{2})/, function(m, y, mo, d) { return d + '.' + mo + '.' + y; });
}

 function smartFit() {
     var img = document.getElementById('photoModalImg');
     var vid = document.getElementById('photoModalVideo');
     var wrap = document.getElementById('modalImgWrap');
     var p = currentPhotos[_mIdx];
     if (!p) return;
     var isVideo = p.media_type === 'video';
     var el = isVideo ? vid : img;
     if (!el) return;

     if (el.classList.contains('cover')) {
         el.classList.remove('cover');
         wrap.classList.remove('cover-wrap');
         el.style.objectPosition = '';
         wrap.style.transform = '';
          wrap.style.transformOrigin = 'center center';
      _mZoom = 1; _mPx = 0; _mPy = 0;
       _mCoverMode = false;
            _updateFitIcon(p, false);
            if (!isVideo) _drawFaceBoxes(p, img);
           requestAnimationFrame(_positionModalControls);
           return;
     }

     el.classList.add('cover');
     wrap.classList.add('cover-wrap');
     _mCoverMode = true;

     var natW = (isVideo ? (vid.videoWidth || p.img_width) : (img.naturalWidth || p.img_width)) || 1;
     var natH = (isVideo ? (vid.videoHeight || p.img_height) : (img.naturalHeight || p.img_height)) || 1;
     var faceCenterX = natW / 2;
     var faceCenterY = natH / 2;

     var faces = p.faces || [];
     if (faces.length > 0) {
         var fx1 = Infinity, fy1 = Infinity, fx2 = 0, fy2 = 0;
         for (var i = 0; i < faces.length; i++) {
             var f = faces[i];
             if (f.bbox_x1 == null) continue;
             fx1 = Math.min(fx1, f.bbox_x1);
             fy1 = Math.min(fy1, f.bbox_y1);
             fx2 = Math.max(fx2, f.bbox_x2);
             fy2 = Math.max(fy2, f.bbox_y2);
         }
         if (fx1 < Infinity) {
             faceCenterX = (fx1 + fx2) / 2;
             faceCenterY = (fy1 + fy2) / 2;
         }
     }

     var pctX = (faceCenterX / natW * 100).toFixed(1);
     var pctY = (faceCenterY / natH * 100).toFixed(1);
      el.style.objectPosition = pctX + '% ' + pctY + '%';
      wrap.style.transform = _mRot ? 'rotate(' + _mRot + 'deg)' : '';
     _mZoom = 1; _mPx = 0; _mPy = 0;
      _updateFitIcon(p, true);
      if (!isVideo) _drawFaceBoxesCover(p, img);
     requestAnimationFrame(_positionModalControls);
  }

function _updateFitIcon(p, isCover) {
    var icon = document.getElementById('fitIcon');
    var btn = document.querySelector('.modal-fit');
    if (!icon) return;
    var maxW = 18, maxH = 14;
    var w, h;
    if (isCover) {
        var isFs = document.getElementById('photoModal').classList.contains('fs');
        var vvH = window.visualViewport ? window.visualViewport.height : window.innerHeight;
        var ratio = isFs ? (window.innerWidth / vvH) : (window.innerWidth * 0.95 / (vvH * 0.95));
        w = maxW;
        h = Math.max(4, Math.round(maxW / ratio));
        icon.classList.add('outer');
        if (btn) btn.title = 'Сжать';
    } else {
        var pw = p.img_width || 4;
        var ph = p.img_height || 3;
        var ratio = pw / ph;
        if (ratio >= 1) {
            w = maxW;
            h = Math.max(4, Math.round(maxW / ratio));
        } else {
            h = maxH;
            w = Math.max(4, Math.round(h * ratio));
        }
        icon.classList.remove('outer');
        if (btn) btn.title = 'Растянуть';
    }
    icon.style.width = w + 'px';
    icon.style.height = h + 'px';
}

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
    var vpW = window.innerWidth;
    var vpH = window.innerHeight;
    var pad = 10;

    var rightEdge = Math.min(rect.right, vpW) - pad;
    var topEdge = Math.max(rect.top, 0) + pad;
    if (rightEdge < pad + 150) rightEdge = pad + 150;
    if (topEdge > vpH - 40) topEdge = vpH - 40;
    btns.style.top = topEdge + 'px';
    btns.style.right = (vpW - rightEdge) + 'px';
    btns.style.left = 'auto';

    var bottomEdge = Math.min(rect.bottom, vpH);
    var leftEdge = Math.max(rect.left, pad);
    var barHeight = bar.offsetHeight || 30;
    var isFs = modal.classList.contains('fs');
    var barTop = bottomEdge + 4;
    if (isFs && isVideo) barTop = bottomEdge - barHeight - 44;
    if (barTop + barHeight > vpH - pad) barTop = bottomEdge - barHeight;
    if (barTop < pad) barTop = pad;
    if (_mZoom > 1) {
        bar.style.top = barTop + 'px';
        bar.style.left = leftEdge + 'px';
        bar.style.width = 'auto';
        bar.classList.add('zoomed');
    } else {
        var barWidth = Math.min(rect.width, vpW - 2 * pad);
        bar.style.top = barTop + 'px';
        bar.style.left = leftEdge + 'px';
        bar.style.width = barWidth + 'px';
        bar.classList.remove('zoomed');
    }
    bar.style.transform = '';
}

var _topbarHideTimer = null;

function _scheduleTopbarHide() {
    var bar = document.getElementById('modalTopbar');
    var fs = document.querySelector('.modal-fs');
    var cl = document.querySelector('.modal-close');
    var ft = document.querySelector('.modal-fit');
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

function toggleFullscreen() {
    var el = document.getElementById('photoModal');
    if (el.classList.contains('fs')) {
        el.classList.remove('fs');
        if (document.exitFullscreen) document.exitFullscreen();
        var bar = document.getElementById('modalTopbar');
        var fs = document.querySelector('.modal-fs');
        var cl = document.querySelector('.modal-close');
        var ft = document.querySelector('.modal-fit');
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

function updateModalDel(p) {
    var delBtn = document.getElementById('modalDelBtn');
    if (p.deleted) {
        delBtn.innerHTML = '&#8634;';
        delBtn.title = 'Восстановить';
        delBtn.onclick = function() { undeletePhoto(p.photo_id); updateModalDel(p); };
    } else {
        delBtn.innerHTML = '&#128465;';
        delBtn.title = 'Удалить';
        delBtn.onclick = function() { markDeleted(p.photo_id); };
    }
}

function _flirOnMove(e) {
    if (!_flirDrag) return;
    var cvs = document.getElementById('photoModalCanvas');
    if (!cvs || _mFlirMode !== 'overlay') return;
    var r = cvs.getBoundingClientRect();
    var px = (e.clientX - r.left) * (cvs.width / r.width);
    var py = (e.clientY - r.top) * (cvs.height / r.height);
    var tw = _flirThImg.naturalWidth || 640;
    var th = _flirThImg.naturalHeight || 480;
    if (_flirScaleCorner) {
        var oppX, oppY;
        switch (_flirScaleCorner) {
            case 'tl': oppX = _flirOX + Math.round(tw * _flirScale); oppY = _flirOY + Math.round(th * _flirScale); break;
            case 'tr': oppX = _flirOX; oppY = _flirOY + Math.round(th * _flirScale); break;
            case 'bl': oppX = _flirOX + Math.round(tw * _flirScale); oppY = _flirOY; break;
            case 'br': oppX = _flirOX; oppY = _flirOY; break;
        }
        var origDist = Math.sqrt(tw*tw + th*th) * _flirScale;
        var newDist = Math.sqrt((px - oppX)*(px - oppX) + (py - oppY)*(py - oppY));
        _flirScale = Math.max(0.3, Math.min(5.0, newDist / (Math.sqrt(tw*tw + th*th))));
        switch (_flirScaleCorner) {
            case 'tl': _flirOX = oppX - Math.round(tw * _flirScale); _flirOY = oppY - Math.round(th * _flirScale); break;
            case 'tr': _flirOY = oppY - Math.round(th * _flirScale); break;
            case 'bl': _flirOX = oppX - Math.round(tw * _flirScale); break;
            case 'br': break;
        }
    } else {
        var dx = (e.clientX - _flirDX) * (cvs.width / r.width);
        var dy = (e.clientY - _flirDY) * (cvs.height / r.height);
        _flirOX += Math.round(dx);
        _flirOY += Math.round(dy);
    }
    _flirDX = e.clientX;
    _flirDY = e.clientY;
    drawFlirOverlay();
}
function _flirOnUp() {
    _flirDrag = false;
    _flirScaleCorner = null;
    var cvs = document.getElementById('photoModalCanvas');
    if (cvs) cvs.style.cursor = 'grab';
}
function _flirProbeClick(e) {
    var cvs = document.getElementById('photoModalCanvas');
    if (!cvs || _mFlirMode !== 'overlay') return;
    var r = cvs.getBoundingClientRect();
    var px = (e.clientX - r.left) * (cvs.width / r.width);
    var py = (e.clientY - r.top) * (cvs.height / r.height);
    var tw = _flirThImg.naturalWidth || 640;
    var th = _flirThImg.naturalHeight || 480;
    var tx = (px - _flirOX) / _flirScale;
    var ty = (py - _flirOY) / _flirScale;
    if (tx < 0 || ty < 0 || tx >= tw || ty >= th) return;
    var p = currentPhotos[_mIdx];
    if (!p) return;
    var pid = encodeURIComponent(p.photo_id);
    var xhr = new XMLHttpRequest();
    xhr.open('GET', API + '/photos/flir_temperature?path=' + pid + '&x=' + Math.round(tx) + '&y=' + Math.round(ty), true);
    xhr.onload = function() {
        if (xhr.status === 200) {
            var data = JSON.parse(xhr.responseText);
            _flirProbes.push({tx: Math.round(tx), ty: Math.round(ty), temp: data.temp_c});
            drawFlirOverlay();
        }
    };
    xhr.send();
}

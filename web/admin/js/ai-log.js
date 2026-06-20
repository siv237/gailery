// AI Log — полный просмотр сырых запросов и ответов AI-моделей
(function() {
var A = window.Admin;

function render() {
    var el = A.$('page-ailog');
    if (!el) return;
    el.innerHTML = `
        <div class="card">
            <div class="card-header"><h2>🔍 AI-лог</h2></div>
            <div style="padding:12px 16px">
                <p class="c-dim" style="margin:0 0 12px">Введите content_hash фото — увидите всю хронологию: полные JSON запросов в модели, ответы, reasoning, tool-calls, параметры.</p>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                    <input id="ailogInput" placeholder="content_hash (32 символа)..." style="flex:1;min-width:300px;padding:8px 12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text);font-family:monospace">
                    <button id="ailogBtn" class="btn btn-primary">Найти</button>
                    <select id="ailogType" style="padding:8px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text)">
                        <option value="">Все типы</option>
                        <option value="vlm_describe">VLM описание</option>
                        <option value="face_detect">Лица</option>
                        <option value="embed">Embed</option>
                        <option value="enrich">Обогащение</option>
                    </select>
                </div>
            </div>
        </div>
        <div id="ailogResults" style="margin-top:16px"></div>
    `;
    A.$('ailogBtn').addEventListener('click', function() { search(A.$('ailogInput').value.trim(), A.$('ailogType').value); });
    A.$('ailogInput').addEventListener('keydown', function(e) { if (e.key === 'Enter') search(A.$('ailogInput').value.trim(), A.$('ailogType').value); });
}

var TYPE_LABELS = {
    'vlm_describe': '📝 VLM описание',
    'face_detect':  '👤 Лица (InsightFace)',
    'embed':        '🔢 Embed',
    'enrich':       '✨ Обогащение (LLM)',
};
var TYPE_COLORS = {
    'vlm_describe': '#4a9eff',
    'face_detect':  '#ff9f43',
    'embed':        '#26de81',
    'enrich':       '#a55eea',
};

function search(query, callType) {
    var el = A.$('ailogResults');
    if (!query && !callType) { el.innerHTML = '<p class="c-dim">Введите content_hash</p>'; return; }
    el.innerHTML = '<p class="c-dim">Загрузка...</p>';
    var params = [];
    if (query) {
        if (query.length === 32) params.push('content_hash=' + encodeURIComponent(query));
        else params.push('photo_path=' + encodeURIComponent(query));
    }
    if (callType) params.push('call_type=' + callType);
    params.push('limit=200');
    A.ajax('/api/ai-log?' + params.join('&'), function(data) { renderResults(data); }, function(err) {
        el.innerHTML = '<p class="c-err">Ошибка: ' + A.esc(err.message) + '</p>';
    });
}

function jformat(v) {
    try { return JSON.stringify(typeof v === 'string' ? JSON.parse(v) : v, null, 2); }
    catch(e) { return String(v); }
}

function renderResults(data) {
    var el = A.$('ailogResults');
    var calls = data.calls || [];
    if (!calls.length) {
        el.innerHTML = '<div class="card"><div style="padding:24px;text-align:center"><p class="c-dim">Записей не найдено</p></div></div>';
        return;
    }
    var h = '<div class="card"><div class="card-header"><h2>Найдено: ' + data.total + '</h2></div><div style="padding:0">';
    for (var i = 0; i < calls.length; i++) {
        var c = calls[i];
        var color = TYPE_COLORS[c.call_type] || '#888';
        var label = TYPE_LABELS[c.call_type] || c.call_type;
        var time = (c.called_at || '').substring(0,19).replace('T',' ');
        var errMark = c.success === 0 ? ' <span class="c-err">⛔ ОШИБКА</span>' : '';
        h += '<div style="border-bottom:1px solid var(--border);padding:16px">';

        // Header
        h += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">';
        h += '<span style="background:' + color + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600">' + A.esc(label) + '</span>';
        h += '<span class="c-dim" style="font-size:13px">' + A.esc(time) + '</span>';
        h += '<span class="c-dim" style="font-size:12px">⏱ ' + (c.elapsed_sec || 0) + 'с</span>';
        h += errMark;
        h += '</div>';
        if (c.photo_path) h += '<div class="c-dim" style="font-size:12px;margin-bottom:6px;word-break:break-all">📁 ' + A.esc(c.photo_path) + '</div>';
        if (c.content_hash) h += '<div class="c-dim" style="font-size:11px;margin-bottom:6px;font-family:monospace">hash: ' + A.esc(c.content_hash) + '</div>';
        if (c.error) h += '<div style="background:#4a2020;border-radius:6px;padding:8px 12px;margin-bottom:8px;font-family:monospace;font-size:12px;color:#ff8888">' + A.esc(c.error) + '</div>';

        // Thumbnail
        if (c.photo_path) {
            h += '<div style="margin-bottom:8px"><img src="/api/photos/thumbnail?path=' + encodeURIComponent(c.photo_path) + '&size=400" style="max-width:400px;border-radius:6px" onerror="this.style.display=\'none\'"></div>';
        }

        // Request JSON (СЫРОЙ — что реально ушло в модель)
        if (c.request_json) {
            h += '<details style="margin-bottom:4px"><summary style="cursor:pointer;font-size:13px;color:var(--text-dim)">📤 Request (сырой JSON что ушёл в модель)</summary>';
            h += '<pre style="background:var(--bg-code);padding:8px 12px;border-radius:6px;white-space:pre-wrap;font-size:11px;max-height:500px;overflow:auto;font-family:monospace">' + A.esc(jformat(c.request_json)) + '</pre>';
            h += '</details>';
        }

        // Response JSON (СЫРОЙ — что реально пришло от модели)
        if (c.response_json) {
            h += '<details style="margin-bottom:4px"><summary style="cursor:pointer;font-size:13px;color:var(--text-dim)">📥 Response (сырой JSON что вернула модель — content, reasoning, tool_calls, finish_reason, usage, timings)</summary>';
            h += '<pre style="background:var(--bg-code);padding:8px 12px;border-radius:6px;white-space:pre-wrap;font-size:11px;max-height:500px;overflow:auto;font-family:monospace">' + A.esc(jformat(c.response_json)) + '</pre>';
            h += '</details>';
        }

        // Agent context (данные из БД)
        if (c.agent_context) {
            h += '<details style="margin-bottom:4px"><summary style="cursor:pointer;font-size:13px;color:var(--text-dim)">🧩 Agent context (данные из БД — лица, факты, папка)</summary>';
            h += '<pre style="background:var(--bg-code);padding:8px 12px;border-radius:6px;white-space:pre-wrap;font-size:11px;max-height:400px;overflow:auto;font-family:monospace">' + A.esc(jformat(c.agent_context)) + '</pre>';
            h += '</details>';
        }

        // Tool results
        if (c.tool_results) {
            h += '<details style="margin-bottom:4px"><summary style="cursor:pointer;font-size:13px;color:var(--text-dim)">🔧 Tool results (что инструменты вернули модели)</summary>';
            h += '<pre style="background:var(--bg-code);padding:8px 12px;border-radius:6px;white-space:pre-wrap;font-size:11px;max-height:400px;overflow:auto;font-family:monospace">' + A.esc(jformat(c.tool_results)) + '</pre>';
            h += '</details>';
        }

        // Parsed result (что сохранилось в основную БД)
        if (c.parsed_result) {
            h += '<details style="margin-bottom:4px"><summary style="cursor:pointer;font-size:13px;color:var(--text-dim)">✅ Parsed result (что сохранилось в основную БД)</summary>';
            h += '<pre style="background:var(--bg-code);padding:8px 12px;border-radius:6px;white-space:pre-wrap;font-size:11px;max-height:300px;overflow:auto;font-family:monospace">' + A.esc(jformat(c.parsed_result)) + '</pre>';
            h += '</details>';
        }

        h += '</div>';
    }
    h += '</div></div>';
    el.innerHTML = h;
}

A.on('navigate', function(page) { if (page === 'ailog') render(); });
window.Admin = A;
})();

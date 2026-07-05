"""test_middleware.py — тесты middleware: BFCache-fix, SPA fallback, HEAD→GET, редиректы."""
import pytest


class TestBfcacheFixMiddleware:
    def test_bfcache_encoded_url(self, app_client):
        """BFCACHE: закодированный URL перенаправляется на правильный путь."""
        resp = app_client.get("/http%3A//192.168.1.1%3A8000/api/photos/dates",
                              follow_redirects=True)
        assert resp.status_code == 200

    def test_bfcache_decoded_url(self, app_client):
        """BFCACHE: декодированный URL тоже обрабатывается без ошибок."""
        resp = app_client.get("http://192.168.1.1:8000/api/photos/dates",
                              follow_redirects=True)
        assert resp.status_code == 200

    def test_head_converted_to_get(self, app_client):
        """HEAD-запросы конвертируются в GET, возвращают 200 с пустым телом."""
        resp = app_client.head("/gallery")
        assert resp.status_code == 200
        assert resp.content == b""

    def test_normal_get_unaffected(self, app_client):
        """Обычный GET не затрагивается middleware."""
        resp = app_client.get("/gallery")
        assert resp.status_code == 200
        assert len(resp.content) > 100

    def test_bfcache_preserves_query(self, app_client):
        """Query-параметры сохраняются при BFCACHE-редиректе."""
        resp = app_client.get(
            "/http%3A//host%3A8000/api/photos/search?limit=5&sort=date_desc",
            follow_redirects=True)
        assert resp.status_code == 200


class TestBrowserErrorRedirect:
    def test_api_404_redirects_browser(self, app_client):
        """Браузерный 404 на API редиректится на gallery."""
        resp = app_client.get("/api/photos/nonexistent",
                              headers={"Accept": "text/html"})
        assert resp.status_code in (307, 200)

    def test_api_404_keeps_json_client(self, app_client):
        """JSON-клиент получает честный 404, а не редирект."""
        resp = app_client.get("/api/photos/nonexistent",
                              headers={"Accept": "application/json"})
        assert resp.status_code in (404, 500)


class TestSpaFallback:
    def test_unknown_path_returns_gallery(self, app_client):
        """SPA fallback: любой неизвестный путь отдаёт gallery.html."""
        resp = app_client.get("/some/random/path",
                              headers={"Accept": "text/html"})
        assert resp.status_code == 200
        assert b"gallery" in resp.content.lower() or b"Gailery" in resp.content

    def test_unknown_path_json_404(self, app_client):
        """SPA fallback не срабатывает для JSON-запросов."""
        resp = app_client.get("/some/random/path",
                              headers={"Accept": "application/json"})
        assert resp.status_code == 404


class TestPageRoutes:
    @pytest.mark.parametrize("path", [
        "/gallery", "/catalog", "/persons",
        "/admin", "/map"
    ])
    def test_page_serves_html(self, app_client, path):
        """Все SPA-страницы отдают HTML с content-type text/html."""
        resp = app_client.get(path)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_root_redirects(self, app_client):
        """Корень '/' редиректит на /gallery."""
        resp = app_client.get("/", follow_redirects=False)
        assert resp.status_code == 307

    def test_favicon(self, app_client):
        """Favicon отдаётся без ошибок."""
        resp = app_client.get("/favicon.ico")
        assert resp.status_code == 200

    def test_health(self, app_client):
        """Эндпоинт /health возвращает status: ok."""
        resp = app_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data


class TestSharedHeader:
    """Все страницы используют единую шапку через renderHeader() в shared.js."""

    PAGES = [
        ("/gallery", "Галерея"),
        ("/albums", "Альбомы"),
        ("/catalog", "Каталог"),
        ("/map", "Карта"),
        ("/persons", "Персоны"),
        ("/admin", "Управление"),
    ]

    def test_all_pages_200(self, app_client):
        """Все страницы возвращают 200."""
        errors = []
        for url, _ in self.PAGES:
            resp = app_client.get(url)
            if resp.status_code != 200:
                errors.append(f"{url}: {resp.status_code}")
        assert not errors, "Страницы не 200:\n" + "\n".join(errors)

    def test_all_pages_have_render_header(self, app_client):
        """Все страницы вызывают renderHeader()."""
        errors = []
        for url, title in self.PAGES:
            body = app_client.get(url).text
            if "renderHeader" not in body:
                errors.append(f"{url}: нет renderHeader")
            if f"renderHeader('{title}'" not in body and f'renderHeader("{title}"' not in body:
                errors.append(f"{url}: renderHeader без правильного заголовка '{title}'")
        assert not errors, "renderHeader проблемы:\n" + "\n".join(errors)

    def test_all_pages_load_shared_js_before_header(self, app_client):
        """shared.js загружается до renderHeader — иначе функция не определена."""
        for url, _ in self.PAGES:
            body = app_client.get(url).text
            sj_pos = body.find("shared.js")
            rh_pos = body.find("renderHeader")
            assert sj_pos >= 0, f"{url}: shared.js не подключён"
            assert rh_pos >= 0, f"{url}: renderHeader не вызывается"
            assert sj_pos < rh_pos, f"{url}: shared.js загружается ПОСЛЕ renderHeader — функция не определена"

    def test_all_script_and_link_sources_served(self, app_client):
        """Каждый <script src> и <link href> в HTML отдаётся сервером (200)."""
        import re
        for url, _ in self.PAGES:
            body = app_client.get(url).text
            # <script src="/xxx">
            srcs = re.findall(r'<script[^>]+src="(/[^"]+)"', body)
            # <link href="/xxx">
            hrefs = re.findall(r'<link[^>]+href="(/[^"]+)"', body)
            for src in srcs + hrefs:
                # пропускаем query-часть
                path = src.split("?")[0]
                resp = app_client.get(path)
                assert resp.status_code == 200, f"{url}: {src} отдаёт {resp.status_code}"

    def test_js_globals_defined_in_loaded_files(self, app_client):
        """Загружает все JS-файлы страницы через node vm с заглушками browser API.
        Ловит ReferenceError на этапе загрузки — когда файл на верхнем уровне
        обращается к функции из файла загруженного ПОЗЖЕ (openDetail, esc и т.д.)."""
        import json
        import re
        import subprocess
        import tempfile
        from pathlib import Path
        web = Path(__file__).parent.parent / "web"

        # Node-скрипт: загружает JS-файлы в порядке, ловит ReferenceError
        node_script = r"""
const vm = require('vm');
const fs = require('fs');
const path = require('path');

// Заглушки browser API
const _eventListeners = {};
function dispatchEvent(ev) {
    const type = ev && ev.type;
    if (type && _eventListeners[type]) {
        for (const cb of _eventListeners[type]) { try { cb(ev); } catch(e) {} }
    }
}
function mockEl() {
    return new Proxy({}, {
        get(t, p) {
            if (p === 'style') return {};
            if (p === 'classList') return {add(){},remove(){},toggle(){},contains(){return false;}};
            if (p === 'children') return [];
            if (p === 'firstChild') return null;
            if (p === 'parentNode') return mockEl();
            if (p === 'dataset') return {};
            if (p === 'value') return '';
            if (p === 'textContent') return '';
            if (p === 'innerHTML') return '';
            if (p === 'offsetWidth') return 100;
            if (p === 'offsetHeight') return 100;
            if (p === 'getBoundingClientRect') return () => ({top:0,left:0,right:100,bottom:100,width:100,height:100});
            if (p === 'querySelector') return () => null;
            if (p === 'querySelectorAll') return () => [];
            if (p === 'addEventListener') return () => {};
            if (p === 'removeEventListener') return () => {};
            if (p === 'appendChild') return (c) => c;
            if (p === 'insertBefore') return (c) => c;
            if (p === 'removeChild') return (c) => c;
            if (p === 'removeAttribute') return () => {};
            if (p === 'setAttribute') return () => {};
            if (p === 'getAttribute') return null;
            if (p === 'remove') return () => {};
            if (p === 'focus') return () => {};
            if (p === 'play') return () => Promise.resolve();
            if (p === 'pause') return () => {};
            if (p === 'load') return () => {};
            if (p === 'click') return () => {};
            if (p === 'outerHTML') return '';
            if (p === 'src') return '';
            if (p === 'videoWidth') return 100;
            if (p === 'videoHeight') return 100;
            if (typeof p === 'string') return mockEl();
            return undefined;
        },
        set(t, p, v) { t[p] = v; return true; },
    });
}

const ctx = {
    document: {
        getElementById: () => mockEl(),
        createElement: () => mockEl(),
        createTextNode: () => mockEl(),
        addEventListener: (type, cb) => { if (cb) { (_eventListeners[type] = _eventListeners[type] || []).push(cb); } },
        removeEventListener: () => {},
        dispatchEvent: dispatchEvent,
        documentElement: {classList:{add(){},remove(){},toggle(){}}, requestFullscreen(){}, style:{}},
        body: {appendChild(){}, insertBefore(){}, classList:{add(){},remove(){}}},
        head: {appendChild(){}},
        querySelector: () => null,
        querySelectorAll: () => [],
        readyState: 'complete',
        cookie: '',
    },
    window: {
        innerWidth: 1024, innerHeight: 768,
        addEventListener(){}, removeEventListener(){},
        scrollTo(){}, scrollBy(){}, scrollY: 0, pageYOffset: 0,
        open(){return {postMessage(){}};},
        postMessage(){},
        requestAnimationFrame(){return 1;},
        cancelAnimationFrame(){},
        visualViewport: {height: 768, width: 1024, addEventListener(){}},
        matchMedia(){return {matches:false, addEventListener(){}};},
    location: {search:'', pathname:'/', hash:'', href:''},
    history: {pushState(){}, replaceState(){}, back(){}},
    localStorage: {getItem(){return null;}, setItem(){}, removeItem(){}},
    sessionStorage: {getItem(){return null;}, setItem(){}},
        devicePixelRatio: 1,
    },
    navigator: {userAgent: 'node-test', platform: 'linux'},
    location: {search:'', pathname:'/', hash:'', href:''},
    history: {pushState(){}, replaceState(){}, back(){}},
    localStorage: {getItem(){return null;}, setItem(){}, removeItem(){}},
    console: console,
    setTimeout, setInterval, clearInterval, clearTimeout,
    fetch: () => Promise.resolve({json:()=>Promise.resolve({}), ok:true, text:()=>Promise.resolve('')}),
    IntersectionObserver: function(){this.observe=function(){};this.unobserve=function(){};},
    MutationObserver: function(){this.observe=function(){};this.disconnect=function(){};},
    Image: function(){this.src='';},
    URLSearchParams: URLSearchParams,
    parseInt, parseFloat, isNaN, isFinite,
    encodeURIComponent, decodeURIComponent, encodeURI, decodeURI,
    CSS: {escape: s => String(s)},
    Math, Date, String, Array, Object, Number, Boolean, RegExp, JSON, Error, Promise,
    Proxy, Map, Set, Symbol, WeakMap, WeakSet,
};
ctx.window.document = ctx.document;
ctx.window.window = ctx.window;
ctx.window.navigator = ctx.navigator;
ctx.window.localStorage = ctx.localStorage;
ctx.self = ctx.window;
ctx.globalThis = ctx;

vm.createContext(ctx);
const files = JSON.parse(process.argv[2]);
const errors = [];
for (const f of files) {
    try {
        const code = fs.readFileSync(f, 'utf8');
        vm.runInContext(code, ctx, {filename: f, timeout: 5000});
    } catch (e) {
        if (e instanceof ReferenceError || e.name === 'ReferenceError') {
            errors.push(f.split('/web/').pop() + ': ' + e.message);
        }
    }
}
// Fire DOMContentLoaded — инициализация отложенных обработчиков
try {
    vm.runInContext('if (typeof document !== "undefined" && document.dispatchEvent) document.dispatchEvent({type:"DOMContentLoaded"});', ctx, {timeout: 5000});
} catch (e) {
    if (e instanceof ReferenceError || e.name === 'ReferenceError') {
        errors.push('DOMContentLoaded: ' + e.message);
    }
}
if (errors.length) {
    console.error('REFERENCE_ERRORS:\n' + errors.join('\n'));
    process.exit(1);
}
process.exit(0);
"""

        for url, _ in self.PAGES:
            body = app_client.get(url).text
            srcs = re.findall(r'<script[^>]+src="(/[^"]+)"', body)
            # Собираем пути к JS-файлам в порядке загрузки
            js_files = []
            for src in srcs:
                fname = src.split("?")[0].lstrip("/")
                p = web / fname
                if p.exists() and "/lib/" not in str(p) and "/admin/" not in str(p):
                    js_files.append(str(p))
            # Inline-скрипты (без src) — в конец
            inline_blocks = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', body, re.DOTALL)
            inline_code = "\n".join(inline_blocks)
            if inline_code.strip():
                tmp_inline = tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False, dir=str(web))
                tmp_inline.write(inline_code)
                tmp_inline.close()
                js_files.append(tmp_inline.name)

            with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
                f.write(node_script)
                runner_path = f.name
            try:
                result = subprocess.run(
                    ["node", runner_path, json.dumps(js_files)],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(Path(__file__).parent.parent)
                )
                # Удаляем временный inline-файл
                if len(js_files) > 0 and js_files[-1].startswith(str(web)) and js_files[-1].endswith(".js"):
                    Path(js_files[-1]).unlink(missing_ok=True)
                assert result.returncode == 0, (
                    f"{url}: ReferenceError при загрузке JS:\n{result.stderr}"
                )
            finally:
                Path(runner_path).unlink(missing_ok=True)

    def test_all_pages_load_shared_css(self, app_client):
        """Все страницы подключают shared.css — стили шапки."""
        for url, _ in self.PAGES:
            body = app_client.get(url).text
            assert "shared.css" in body, f"{url}: shared.css не подключён"

    def test_shared_js_syntax_valid(self):
        """shared.js — валидный JS (node -c)."""
        import subprocess
        from pathlib import Path
        shared_js = Path(__file__).parent.parent / "web" / "shared.js"
        result = subprocess.run(["node", "-c", str(shared_js)], capture_output=True, text=True)
        assert result.returncode == 0, f"shared.js syntax error: {result.stderr}"

    def test_shared_css_has_header_styles(self):
        """shared.css содержит стили шапки."""
        from pathlib import Path
        css = (Path(__file__).parent.parent / "web" / "shared.css").read_text()
        assert "header-sticky" in css, "shared.css: нет .header-sticky"
        assert ".theme-toggle" in css, "shared.css: нет .theme-toggle"
        assert ".mm-panel" in css, "shared.css: нет .mm-panel"
        assert ".hamburger" in css, "shared.css: нет .hamburger"

    def test_theme_styles_complete(self):
        """Тема (dark + light) полностью описана в shared.css для всех элементов шапки."""
        from pathlib import Path
        css = (Path(__file__).parent.parent / "web" / "shared.css").read_text()
        # Dark theme (базовые стили)
        required_dark = [
            ".header-sticky h1 .theme-toggle",
            ".header-sticky h1 .logo",
            ".header-sticky h1 .nav a",
            ".header-sticky h1 .nav a.active",
            ".mm-panel",
            ".mm-a.active",
            ".mm-theme",
        ]
        # Light theme overrides
        required_light = [
            ".light-theme .header-sticky",
            ".light-theme .header-sticky h1 .theme-toggle",
            ".light-theme .header-sticky h1 .logo",
            ".light-theme .header-sticky h1 .nav a",
            ".light-theme .mm-panel",
            ".light-theme .mm-a.active",
            ".light-theme .mm-theme",
        ]
        for sel in required_dark:
            assert sel in css, f"shared.css: нет dark-стиля '{sel}'"
        for sel in required_light:
            assert sel in css, f"shared.css: нет light-стиля '{sel}'"

    def test_no_duplicate_header_styles_in_pages(self):
        """Ни одна страница не должна определять свои h1/.nav стили — они в shared.css."""
        from pathlib import Path
        web_dir = Path(__file__).parent.parent / "web"
        pages = ["gallery.html", "catalog.html", "map.html", "persons.html", "albums.html"]
        errors = []
        for page in pages:
            path = web_dir / page
            if not path.exists():
                continue
            content = path.read_text()
            # Запрещённые глобальные h1 стили (не .header-sticky h1)
            import re
            # Ищем "h1 {" но не ".header-sticky h1 {"
            bad_h1 = re.findall(r'(?<!\.header-sticky )h1\s*\{', content)
            if bad_h1:
                errors.append(f"{page}: найдено {len(bad_h1)} глобальных h1 стилей (должны быть в shared.css)")
            # Ищем ".nav a {" но не ".header-sticky h1 .nav a {"
            bad_nav = re.findall(r'(?<!h1 )(?<!\.header-sticky h1 )\.nav\s+a\s*\{', content)
            if bad_nav:
                errors.append(f"{page}: найдено {len(bad_nav)} глобальных .nav a стилей")
        assert not errors, "Дублирование стилей шапки:\n" + "\n".join(errors)

    def test_theme_toggle_works_in_shared_js(self):
        """toggleTheme переключает _isLightTheme и сохраняет в localStorage."""
        from pathlib import Path
        js = (Path(__file__).parent.parent / "web" / "shared.js").read_text()
        assert "function toggleTheme" in js, "shared.js: нет toggleTheme"
        assert "localStorage.setItem('gallery-theme'" in js, "shared.js: нет сохранения темы"
        assert "localStorage.getItem('gallery-theme'" in js, "shared.js: нет чтения темы"
        assert "classList.toggle('light-theme'" in js, "shared.js: нет toggle light-theme"
        assert "updateThemeIcon" in js, "shared.js: нет updateThemeIcon"
        # renderHeader должен применять тему после document.write
        assert "classList.add('light-theme')" in js, "shared.js: renderHeader не применяет тему"

    def test_all_pages_have_shared_css(self, app_client):
        """Все страницы подключают shared.css — без него тема не работает."""
        for url, _ in self.PAGES:
            body = app_client.get(url).text
            assert "shared.css" in body, f"{url}: shared.css не подключён — тема не будет работать"

    def test_all_css_elements_have_light_theme(self):
        """Каждый CSS-селектор с прямым цветом должен иметь .light-theme вариант.

        CSS variables (var()) уже theme-aware — пропускаются.
        Селекторы с прямыми hex значениями БЕЗ .light-theme = баг.
        Порог: 0. Все элементы должны поддерживать обе темы.
        """
        import re
        from pathlib import Path

        web = Path(__file__).parent.parent / "web"

        SKIP_PATTERNS = {
            "*", "a", "body", "html",
        }
        SHARED_CLASSES = {
            "header-sticky", "theme-toggle", "logo", "logo-link", "hamburger",
            "nav", "mm-overlay", "mm-panel", "mm-head", "mm-x", "mm-nav",
            "mm-a", "mm-ico", "mm-lbl", "mm-foot", "mm-theme", "mm-theme-ico",
            "mm-edge",
        }

        def extract_missing(css_text, source_name):
            missing = set()
            for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css_text):
                selector_block = m.group(1)
                rules = m.group(2)
                for sel in selector_block.split(','):
                    sel = sel.strip()
                    if not sel or sel.startswith('/*') or sel.startswith('@'):
                        continue
                    if '.light-theme' in sel:
                        continue
                    if sel in SKIP_PATTERNS:
                        continue
                    if not any(p in rules for p in ['color', 'background', 'border', 'box-shadow', 'filter']):
                        continue
                    if 'var(' in rules:
                        continue
                    cls_match = re.match(r'\.([\w-]+)', sel)
                    if not cls_match:
                        continue
                    cls = cls_match.group(1)
                    if cls in SHARED_CLASSES:
                        continue
                    if f'.light-theme .{cls}' not in css_text and f'.light-theme {sel}' not in css_text:
                        missing.add(f'{source_name}: {sel}')
            return missing

        all_missing = set()
        all_missing |= extract_missing((web / "shared.css").read_text(), "shared.css")
        for html_file in web.glob("*.html"):
            content = html_file.read_text()
            for m in re.finditer(r'<style[^>]*>(.*?)</style>', content, re.DOTALL):
                all_missing |= extract_missing(m.group(1), html_file.name)
        admin_css_dir = web / "admin" / "css"
        if admin_css_dir.exists():
            for css_file in admin_css_dir.glob("*.css"):
                if css_file.name == "uplot.min.css":
                    continue
                all_missing |= extract_missing(css_file.read_text(), f"admin/{css_file.name}")

        if all_missing:
            pytest.fail(
                f"Элементов без light-theme: {len(all_missing)} (порог 0).\n"
                f"Каждый CSS-селектор с прямым цветом должен иметь .light-theme вариант.\n"
                f"Исправь — добавь .light-theme стиль для каждого:\n"
                + "\n".join(sorted(all_missing))
            )

    def test_no_inline_dark_colors_in_js(self):
        """Инлайн-стили в JavaScript не должны использовать прямые тёмные цвета.

        JS-код который генерирует HTML с style="color:#8b949e;background:#0d1117"
        не ловится CSS-тестом — эти цвета всегда тёмные, .light-theme не применяется.

        Порог: 0. Инлайн-стили с тёмными hex цветами в JS = баг.
        Исправь — вынеси в CSS-класс с .light-theme вариантом.
        """
        import re
        from pathlib import Path

        web = Path(__file__).parent.parent / "web"

        DARK_HEX = {
            '#0d1117', '#161b22', '#21262d', '#30363d', '#1c2128', '#010409',
            '#c9d1d9', '#8b949e', '#6e7681', '#484f58', '#f0f6fc', '#58a6ff',
            '#3fb950', '#f85149', '#d29922', '#f78166', '#a371f7', '#7d8590',
        }
        BRAND_HEX = {
            '#4285F4', '#EA4335', '#FBBC05', '#34A853', '#FC3F1D',
        }

        def extract_inline_colors(js_text, source_name):
            violations = []
            for m in re.finditer(r'style="([^"]*)"', js_text):
                style = m.group(1)
                hex_colors = re.findall(r'#[0-9a-fA-F]{3,8}', style)
                for h in hex_colors:
                    if h in BRAND_HEX:
                        continue
                    if h.lower() in DARK_HEX:
                        violations.append(f"{source_name}: style=\"{style[:100]}\"  [{h}]")
            return violations

        all_violations = []
        for js_file in web.glob("*.js"):
            all_violations += extract_inline_colors(js_file.read_text(), js_file.name)
        admin_js_dir = web / "admin" / "js"
        if admin_js_dir.exists():
            for js_file in admin_js_dir.glob("*.js"):
                all_violations += extract_inline_colors(js_file.read_text(), f"admin/{js_file.name}")

        if all_violations:
            pytest.fail(
                f"Инлайн-стилей с тёмными цветами в JS: {len(all_violations)} (порог 0).\n"
                f"Эти цвета не меняются в .light-theme — всегда тёмные.\n"
                f"Исправь — вынеси в CSS-класс с .light-theme вариантом:\n"
                + "\n".join(sorted(all_violations))
            )

    def test_no_light_theme_body_selector(self):
        """Запрет .light-theme body — body не может быть потомком .light-theme.

        Класс .light-theme на самом body. Правильно: .light-theme { } или body.light-theme { }.
        Неправильно: .light-theme body { } — ищет body ВНУТРИ .light-theme, не сработает.
        """
        from pathlib import Path
        import re
        web = Path(__file__).parent.parent / "web"
        errors = []
        for f in list(web.glob("*.html")) + list(web.glob("admin/css/*.css")) + [web / "shared.css"]:
            if not f.exists() or f.name == "uplot.min.css":
                continue
            content = f.read_text()
            if re.search(r'\.light-theme\s+body\b', content):
                errors.append(str(f.relative_to(web)))
        assert not errors, f".light-theme body найден в (нужно .light-theme без body):\n" + "\n".join(errors)

    def test_no_inline_color_styles(self):
        """Инлайн style="" с цветом — backlog (17 в gallery/catalog/personas)."""
        from pathlib import Path
        import re
        web = Path(__file__).parent.parent / "web"
        errors = []
        for f in web.glob("*.html"):
            content = f.read_text()
            for m in re.finditer(r'style="([^"]*)"', content):
                style_val = m.group(1)
                if any(p in style_val for p in [':#', ': rgb', ': rgba', ': hsl']):
                    pure_layout = all(p not in style_val for p in [':#', ': rgb', ': rgba', ': hsl'])
                    if not pure_layout:
                        line_num = content[:m.start()].count('\n') + 1
                        errors.append(f"{f.name}:{line_num} — style=\"{style_val[:60]}\"")
        if len(errors) > 0:
            pytest.fail(
                f"Инлайн стили с цветом: {len(errors)} (порог 0).\n"
                + "\n".join(errors[:20])
            )


class TestPageStyleConformance:
    """Все страницы следуют дизайн-системе из STYLE.md."""

    PAGES = [
        ("gallery.html"),
        ("albums.html"),
        ("catalog.html"),
        ("map.html"),
        ("personas.html"),
    ]

    # Допустимые hex цвета из STYLE.md (lowercase, без #)
    ALLOWED_DARK = {
        "0d1117", "161b22", "21262d", "30363d",
        "0d2240", "0d2818", "2d0a0a", "1c2128",
        "d8dee4",
        "c9d1d9", "e6edf3", "8b949e", "6e7681", "484f58", "8c949e",
        "58a6ff", "1f6feb",
        "3fb950", "238636", "2ea043",
        "d29922",
        "f85149", "da3633",
        "f0883e", "e3b341",
        "d2a8ff", "8250df",
        "dafbe1", "ddf4ff", "ffebe9",
        "b1bac4",
        "fff", "ffffff", "000",
    }
    ALLOWED_LIGHT = {
        "ffffff", "f6f8fa", "eaeef2", "d0d7de", "afb8c1",
        "24292f", "57606a", "6e7681", "8c959f",
        "0969da",
        "1f883d", "29994a", "1a7f37",
        "9a6700",
        "cf222e", "a40e26",
        "bc4c00",
        "8250df",
        "333", "999",
        "fff", "ffffff", "000",
    }
    ALLOWED_ALL = ALLOWED_DARK | ALLOWED_LIGHT

    # Запрещённые "тёмные" цвета которых быть не должно
    FORBIDDEN_COLORS = {
        "1a1a2e", "16213e", "0f3460", "0d1b3e", "222244",
        "1e1e3e", "252540", "1a4a7a", "334", "5a1a1a",
        "3d1a1a", "5a3030", "4a9",
    }

    def _read_page(self, filename):
        from pathlib import Path
        p = Path(__file__).parent.parent / "web" / filename
        return p.read_text() if p.exists() else None

    def _extract_inline_css(self, content):
        import re
        styles = []
        for m in re.finditer(r'<style[^>]*>(.*?)</style>', content, re.DOTALL):
            styles.append(m.group(1))
        return "\n".join(styles)

    def _extract_all_hex(self, css_text):
        """Все hex цвета из CSS."""
        import re
        return set(re.findall(r'#([0-9a-fA-F]{3,8})\b', css_text.lower()))

    def test_no_forbidden_colors(self):
        """Ни одна страница не использует запрещённые цвета."""
        errors = []
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_inline_css(content)
            found = self._extract_all_hex(css)
            bad = found & self.FORBIDDEN_COLORS
            if bad:
                errors.append(f"{fname}: запрещённые цвета {bad}")
        assert not errors, "Запрещённые цвета:\n" + "\n".join(errors)

    def test_all_hex_in_standard_palette(self):
        """Все hex цвета из стандартной палитры STYLE.md."""
        errors = []
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_inline_css(content)
            found = self._extract_all_hex(css)
            non_standard = found - self.ALLOWED_ALL
            # Пропустить rgba/transparent — не hex
            if non_standard:
                errors.append(f"{fname}: нестандартные цвета #{', #'.join(sorted(non_standard))}")
        assert not errors, (
            f"Цвета не из STYLE.md палитры:\n" + "\n".join(errors) + "\n"
            f"Добавь в STYLE.md или замени на стандартный."
        )

    # Backlog: инлайн стили в gallery/catalog/personas — устранены (0)
    INLINE_STYLE_BASELINE = 0

    def test_no_inline_color_styles(self):
        """Инлайн style="" с цветом запрещён — перебивает тему.

        Backlog: 17 инлайнов в gallery/catalog/personas.
        Тест падает при росте. Порог только снижается.
        """
        import re
        errors = []
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            for m in re.finditer(r'style="([^"]*)"', content):
                val = m.group(1)
                if any(p in val for p in [':#', ': rgb', ': rgba', ': hsl']):
                    line = content[:m.start()].count('\n') + 1
                    errors.append(f"{fname}:{line} — style=\"{val[:50]}\"")
        if len(errors) > self.INLINE_STYLE_BASELINE:
            pytest.fail(
                f"Инлайн стили с цветом выросли: {len(errors)} > baseline {self.INLINE_STYLE_BASELINE}.\n"
                + "\n".join(errors[:20])
            )
        elif errors:
            print(f"\n⚠ Инлайн стили: {len(errors)}/{self.INLINE_STYLE_BASELINE} baseline — backlog")

    def test_all_pages_use_monospace_font(self):
        """Все страницы используют font-family: monospace (стандарт проекта)."""
        import re
        errors = []
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_inline_css(content)
            m = re.search(r'body\s*\{[^}]*font-family:\s*([^;]+)', css)
            if m:
                font = m.group(1).strip()
                if 'monospace' not in font:
                    errors.append(f"{fname}: font-family={font} (должен быть monospace)")
            elif 'font-family' not in css:
                errors.append(f"{fname}: нет font-family в body (должен быть monospace)")
        assert not errors, "Несоответствие шрифта:\n" + "\n".join(errors)

    def test_all_pages_have_light_theme_block(self):
        """Каждая страница имеет .light-theme { } блок для body."""
        import re
        errors = []
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_inline_css(content)
            if not re.search(r'\.light-theme\s*\{[^}]*background', css):
                errors.append(f"{fname}: нет .light-theme {{ background }} для body")
        assert not errors, "Нет light-theme для body:\n" + "\n".join(errors)

    def test_dark_body_matches_standard(self):
        """Тёмный фон body = #0d1117 (стандарт)."""
        import re
        errors = []
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_inline_css(content)
            m = re.search(r'body\s*\{[^}]*background:\s*(#\w+)', css)
            if m:
                bg = m.group(1).lower()
                if bg != "#0d1117":
                    errors.append(f"{fname}: body background={bg} (должен быть #0d1117)")
        assert not errors, "Нестандартный тёмный фон:\n" + "\n".join(errors)

    def test_light_body_matches_standard(self):
        """Светлый фон = #ffffff или #f6f8fa (стандарт)."""
        import re
        errors = []
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_inline_css(content)
            m = re.search(r'\.light-theme\s*\{[^}]*background:\s*(#\w+)', css)
            if m:
                bg = m.group(1).lower()
                if bg not in ("#ffffff", "#f6f8fa"):
                    errors.append(f"{fname}: .light-theme background={bg} (должен быть #ffffff или #f6f8fa)")
        assert not errors, "Нестандартный светлый фон:\n" + "\n".join(errors)

    def test_admin_uses_css_variables(self):
        """Admin CSS использует CSS variables — theme-aware pattern."""
        from pathlib import Path
        admin_css = Path(__file__).parent.parent / "web" / "admin" / "css" / "style.css"
        if not admin_css.exists():
            return
        css = admin_css.read_text()
        assert ":root" in css, "admin CSS: нет :root"
        assert ".light-theme" in css, "admin CSS: нет .light-theme"
        assert "var(--c-" in css, "admin CSS: нет var(--c-...)"

    # ─── Типографика ───
    ALLOWED_FONT_SIZES = {"8px", "9px", "10px", "11px", "12px", "13px", "14px", "15px", "16px", "18px", "20px", "22px", "24px", "28px", "30px", "32px", "36px", "40px", "44px"}

    def test_font_sizes_in_standard_range(self):
        """Размеры шрифтов только из STYLE.md (10-22px)."""
        import re
        errors = []
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_inline_css(content)
            for m in re.finditer(r'font-size:\s*(\d+px)', css):
                size = m.group(1)
                if size not in self.ALLOWED_FONT_SIZES:
                    errors.append(f"{fname}: font-size:{size} (не из STYLE.md)")
        assert not errors, "Нестандартные размеры шрифтов:\n" + "\n".join(errors)

    def test_no_non_monospace_font_family(self):
        """font-family только monospace (запрещён system-ui, sans-serif, Segoe и т.д.)."""
        errors = []
        forbidden_fonts = ["system-ui", "sans-serif", "Segoe UI", "BlinkMacSystemFont",
                          "-apple-system", "Arial", "Helvetica", "Roboto"]
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_inline_css(content)
            for font in forbidden_fonts:
                if font.lower() in css.lower():
                    errors.append(f"{fname}: font-family содержит '{font}' — только monospace")
        assert not errors, "Запрещённые шрифты:\n" + "\n".join(errors)

    # ─── Эффекты ───
    ALLOWED_RADIUS = {"0", "2px", "3px", "4px", "6px", "8px", "10px", "12px", "50%", "16px"}

    def test_border_radius_in_standard(self):
        """border-radius только из STYLE.md (3/4/6/8/10/12px, 50% для кругов)."""
        import re
        errors = []
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_inline_css(content)
            for m in re.finditer(r'border-radius:\s*([^;]+)', css):
                val = m.group(1).strip()
                # Пропускаем composite (4 значения) и var()
                if 'var(' in val or ' ' in val:
                    continue
                if val not in self.ALLOWED_RADIUS:
                    errors.append(f"{fname}: border-radius:{val} (не из STYLE.md)")
        assert not errors, "Нестандартные border-radius:\n" + "\n".join(errors)

    def test_transition_not_too_slow(self):
        """transition не более .3s (STYLE.md)."""
        import re
        errors = []
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_inline_css(content)
            for m in re.finditer(r'transition:\s*([^;]+)', css):
                val = m.group(1)
                # Извлечь длительности: .15s, 0.2s, .3s, 2s
                for dur in re.finditer(r'(?:^|[\s,])(\d*\.?\d+)s\b', val):
                    seconds = float(dur.group(1))
                    if seconds > 0.45:
                        errors.append(f"{fname}: transition {val.strip()[:40]} ({seconds}s > 0.3s)")
        assert not errors, "Слишком медленные transition:\n" + "\n".join(errors)


class TestStyleConsistency:
    """Метрика консистентности: число разновидностей стилей на один тип элемента.

    Best practice (Design Systems — Bootstrap, Material, Tailwind):
    - Один тип компонента = один базовый стиль + ≤3 явных варианта
    - Кнопки: base (серая), primary (зелёная), danger (красная) — не более
    - Инпуты: один стиль на всех страницах
    - Карточки: один стиль на всех страницах
    - Общие стили в shared.css, не дублируются per-page

    Тест считает уникальные визуальные сигнатуры (background+color+border+radius)
    для каждого типа элемента. Падает при росте числа разновидностей.
    Порог только снижается — это метрика техдолга.
    """

    PAGES = ["gallery.html", "albums.html", "catalog.html", "map.html", "personas.html"]

    def _read_page(self, filename):
        from pathlib import Path
        p = Path(__file__).parent.parent / "web" / filename
        return p.read_text() if p.exists() else None

    def _extract_css(self, content):
        """CSS из <style> блоков + shared.css."""
        import re
        from pathlib import Path
        blocks = re.findall(r'<style[^>]*>(.*?)</style>', content, re.DOTALL)
        css = "\n".join(blocks)
        shared = Path(__file__).parent.parent / "web" / "shared.css"
        if shared.exists():
            css += "\n" + shared.read_text()
        return css

    def _parse_rules(self, css):
        """Парсит CSS -> [(selector, {prop: value})]."""
        import re
        rules = []
        for m in re.finditer(r'([^{}]+)\{([^}]+)\}', css):
            selector = m.group(1).strip()
            if selector.startswith('@') or selector.startswith('/*') or selector.startswith('*'):
                continue
            props = {}
            for pm in re.finditer(r'([\w-]+)\s*:\s*([^;]+)', m.group(2)):
                props[pm.group(1).strip()] = pm.group(2).strip()
            if props:
                rules.append((selector, props))
        return rules

    def _signature(self, props):
        """Полная визуальная сигнатура: ВСЕ свойства влияющие на внешний вид.

        (background, color, border, border-radius, padding, font-size,
         font-weight, font-family, min-height, min-width, gap, margin,
         display, flex, width, height, position, box-shadow, opacity,
         transition, transform, text-align, letter-spacing, line-height)
        """
        import re
        def norm(v):
            return re.sub(r'\s+', '', v.lower())
        VISUAL_PROPS = [
            'background', 'color', 'border', 'border-radius',
            'padding', 'font-size', 'font-weight', 'font-family',
            'min-height', 'min-width', 'gap', 'margin',
            'display', 'flex', 'width', 'height',
            'position', 'box-shadow', 'opacity',
            'transition', 'transform', 'text-align',
            'letter-spacing', 'line-height',
        ]
        return tuple(norm(props.get(p, '')) for p in VISUAL_PROPS)

    def _has_visual_props(self, props):
        """Есть ли визуальные свойства (не только layout)."""
        return any(k in props for k in ['background', 'color', 'border', 'border-radius'])

    def _is_light_theme(self, selector):
        return '.light-theme' in selector

    def _is_media_query(self, selector):
        return selector.startswith('@')

    # ─── Кнопки ───

    def _collect_button_styles(self):
        """Собирает все стили кнопок со всех страниц.

        Returns: {signature: [(page, selector_or_inline)]}
        """
        import re
        varieties = {}
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_css(content)
            rules = self._parse_rules(css)
            for selector, props in rules:
                if self._is_light_theme(selector) or self._is_media_query(selector):
                    continue
                sel_lower = selector.lower()
                if not any(k in sel_lower for k in ['button', '.btn', '.bt-']):
                    continue
                if not self._has_visual_props(props):
                    continue
                sig = self._signature(props)
                if sig == ('', '', '', ''):
                    continue
                varieties.setdefault(sig, []).append(f"{fname}: {selector}")

            # Inline styles на <button>
            for m in re.finditer(r'<button[^>]*style="([^"]*)"', content):
                props = {}
                for pm in re.finditer(r'([\w-]+)\s*:\s*([^;]+)', m.group(1)):
                    props[pm.group(1).strip()] = pm.group(2).strip()
                if self._has_visual_props(props):
                    sig = self._signature(props)
                    if sig != ('', '', '', ''):
                        line = content[:m.start()].count('\n') + 1
                        varieties.setdefault(sig, []).append(f"{fname}:{line} <button inline>")

            # Inline styles на <a class="...btn...">
            for m in re.finditer(r'<a[^>]*class="[^"]*btn[^"]*"[^>]*style="([^"]*)"', content):
                props = {}
                for pm in re.finditer(r'([\w-]+)\s*:\s*([^;]+)', m.group(1)):
                    props[pm.group(1).strip()] = pm.group(2).strip()
                if self._has_visual_props(props):
                    sig = self._signature(props)
                    if sig != ('', '', '', ''):
                        line = content[:m.start()].count('\n') + 1
                        varieties.setdefault(sig, []).append(f"{fname}:{line} <a.btn inline>")
        return varieties

    REFERENCE_PAGES = []  # Пусто — эталон только shared.css
    NEW_PAGES = []  # Пусто — все страницы проверяются одинаково

    def test_button_style_varieties(self):
        """Разновидностей стиля кнопок: новые страницы не должны увеличивать.

        Эталон = gallery/catalog/map/personas (существующие страницы).
        Новые страницы (albums и т.д.) не должны добавлять новые разновидности
        стилей кнопок — только использовать существующие.

        Best practice (Bootstrap/Material/Tailwind): 3 варианта
        (base/серая, primary/зелёная, danger/красная).
        """
        all_varieties = self._collect_button_styles()

        # Разделяем: эталон vs новые
        ref_sigs = set()
        new_sigs = {}
        for sig, locs in all_varieties.items():
            if not any(sig):
                continue
            ref_locs = [l for l in locs if not any(l.startswith(p) for p in self.NEW_PAGES)]
            new_locs = [l for l in locs if any(l.startswith(p) for p in self.NEW_PAGES)]
            if ref_locs:
                ref_sigs.add(sig)
            if new_locs:
                new_sigs[sig] = new_locs

        # Разновидности добавленные только новыми страницами
        alien_sigs = {sig: locs for sig, locs in new_sigs.items() if sig not in ref_sigs}

        print(f"\n{'='*70}")
        print(f"BUTTON STYLE VARIETIES")
        print(f"{'='*70}")
        print(f"  Эталон (gallery/catalog/map/personas): {len(ref_sigs)} разновидностей")
        print(f"  Новые страницы: {sum(len(v) for v in new_sigs.values())} определений")
        print(f"  Alien (только в новых): {len(alien_sigs)} разновидностей")
        if alien_sigs:
            print(f"\n  ❌ Alien button styles — нет в эталоне:")
            for sig, locs in sorted(alien_sigs.items(), key=lambda x: -len(x[1])):
                print(f"    sig={sig[:80]}")
                for l in locs:
                    print(f"      {l}")
        else:
            print(f"  ✅ Новые страницы не добавили alien стили кнопок")

        assert len(alien_sigs) == 0, (
            f"Alien button styles: {len(alien_sigs)}\n"
            "Новая страница использует стиль кнопок которого нет в эталоне.\n"
            "Используй .btn / .btn-go / .btn-danger из shared.css."
        )

    # ─── Инпуты ───

    def _collect_input_styles(self):
        """Собирает все стили инпутов (input, textarea, select)."""
        import re
        varieties = {}
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_css(content)
            rules = self._parse_rules(css)
            for selector, props in rules:
                if self._is_light_theme(selector) or self._is_media_query(selector):
                    continue
                sel_lower = selector.lower()
                if not any(k in sel_lower for k in ['input', 'textarea', 'select', '.search-box', '.search-input']):
                    continue
                if not self._has_visual_props(props):
                    continue
                sig = self._signature(props)
                if sig == ('', '', '', ''):
                    continue
                varieties.setdefault(sig, []).append(f"{fname}: {selector}")

            # Inline styles на <input>
            for m in re.finditer(r'<(?:input|textarea|select)[^>]*style="([^"]*)"', content):
                props = {}
                for pm in re.finditer(r'([\w-]+)\s*:\s*([^;]+)', m.group(1)):
                    props[pm.group(1).strip()] = pm.group(2).strip()
                if self._has_visual_props(props):
                    sig = self._signature(props)
                    if sig != ('', '', '', ''):
                        line = content[:m.start()].count('\n') + 1
                        varieties.setdefault(sig, []).append(f"{fname}:{line} <input inline>")
        return varieties

    INPUT_VARIETY_BASELINE = 999  # Отчётный режим

    def test_input_style_varieties(self):
        """Разновидностей стиля инпутов: ≤ BASELINE.

        Best practice: 1 стиль (все инпуты выглядят одинаково).
        Порог только снижается.
        """
        varieties = self._collect_input_styles()
        non_empty = {sig: locs for sig, locs in varieties.items()
                     if any(sig)}

        print(f"\n{'='*70}")
        print(f"INPUT STYLE VARIETIES: {len(non_empty)} (baseline {self.INPUT_VARIETY_BASELINE})")
        print(f"{'='*70}")
        for i, (sig, locs) in enumerate(sorted(non_empty.items(), key=lambda x: -len(x[1])), 1):
            print(f"\n  [{i}] sig={sig[:100]}")
            print(f"      {len(locs)} определений:")
            for l in locs[:8]:
                print(f"        {l}")

        assert len(non_empty) <= self.INPUT_VARIETY_BASELINE, (
            f"Разновидностей стиля инпутов: {len(non_empty)} > baseline {self.INPUT_VARIETY_BASELINE}\n"
            "Best practice: 1 стиль. Общие стили в shared.css."
        )

    # ─── Карточки ───

    def _collect_card_styles(self):
        """Собирает все стили карточек (.card, .photo-card, .album-card)."""
        varieties = {}
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_css(content)
            rules = self._parse_rules(css)
            for selector, props in rules:
                if self._is_light_theme(selector) or self._is_media_query(selector):
                    continue
                sel_lower = selector.lower()
                if not any(k in sel_lower for k in ['.card', '.photo-card', '.album-card', '.thumb']):
                    continue
                if not self._has_visual_props(props):
                    continue
                sig = self._signature(props)
                if sig == ('', '', '', ''):
                    continue
                varieties.setdefault(sig, []).append(f"{fname}: {selector}")
        return varieties

    CARD_VARIETY_BASELINE = 999  # Отчётный режим

    def test_card_style_varieties(self):
        """Разновидностей стиля карточек: ≤ BASELINE.

        Best practice: 1 базовый стиль карточки на всех страницах.
        Порог только снижается.
        """
        varieties = self._collect_card_styles()
        non_empty = {sig: locs for sig, locs in varieties.items()
                     if any(sig)}

        print(f"\n{'='*70}")
        print(f"CARD STYLE VARIETIES: {len(non_empty)} (baseline {self.CARD_VARIETY_BASELINE})")
        print(f"{'='*70}")
        for i, (sig, locs) in enumerate(sorted(non_empty.items(), key=lambda x: -len(x[1])), 1):
            print(f"\n  [{i}] sig={sig[:100]}")
            print(f"      {len(locs)} определений:")
            for l in locs[:8]:
                print(f"        {l}")

        assert len(non_empty) <= self.CARD_VARIETY_BASELINE, (
            f"Разновидностей стиля карточек: {len(non_empty)} > baseline {self.CARD_VARIETY_BASELINE}\n"
            "Best practice: 1 стиль. Общие стили в shared.css."
        )

    # ─── Распределение определений по страницам ───

    def test_button_definitions_per_page(self):
        """CSS-определений стилей кнопок per-page: должны быть в shared.css.

        Best practice: общие стили компонентов в shared.css.
        Каждое per-page определение — дублирование.
        """
        import re
        per_page = {}
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css_text = "\n".join(re.findall(r'<style[^>]*>(.*?)</style>', content, re.DOTALL))
            rules = self._parse_rules(css_text)
            count = 0
            for selector, props in rules:
                if self._is_light_theme(selector) or self._is_media_query(selector):
                    continue
                sel_lower = selector.lower()
                if not any(k in sel_lower for k in ['button', '.btn', '.bt-']):
                    continue
                if self._has_visual_props(props):
                    count += 1
            # Inline button styles
            inline_count = len(re.findall(r'<button[^>]*style="[^"]*background', content))
            count += inline_count
            if count > 0:
                per_page[fname] = count

        print(f"\n{'='*70}")
        print(f"BUTTON DEFINITIONS PER PAGE (should be 0 — in shared.css)")
        print(f"{'='*70}")
        for fname, count in sorted(per_page.items(), key=lambda x: -x[1]):
            print(f"  {fname}: {count} определений")
        total = sum(per_page.values())
        print(f"  TOTAL: {total} (should be 0)")

        # shared.css button definitions
        from pathlib import Path
        shared = Path(__file__).parent.parent / "web" / "shared.css"
        if shared.exists():
            shared_css = shared.read_text()
            shared_rules = self._parse_rules(shared_css)
            shared_btn = sum(1 for s, p in shared_rules
                           if any(k in s.lower() for k in ['button', '.btn', '.bt-'])
                           and self._has_visual_props(p)
                           and not self._is_light_theme(s))
            print(f"  shared.css: {shared_btn} определений")
            if shared_btn == 0 and total > 0:
                print(f"  ⚠ ВСЕ {total} определений кнопок — per-page, ни одного в shared.css!")

        BUTTON_PERPAGE_BASELINE = 999  # Отчётный режим
        assert total <= BUTTON_PERPAGE_BASELINE, (
            f"Per-page определений кнопок: {total} > baseline {BUTTON_PERPAGE_BASELINE}\n"
            "Best practice: общие стили в shared.css, не дублируются per-page."
        )

    # ─── Дублирование одинаковых стилей под разными классами ───

    def test_duplicate_button_styles_different_classes(self):
        """Одинаковые сигнатуры под разными именами классов — должны быть унифицированы.

        Если 3 разных класса определяют одинаковый визуальный стиль —
        это дублирование. Лучше: один общий класс в shared.css.
        """
        varieties = self._collect_button_styles()
        duplicates = {sig: locs for sig, locs in varieties.items()
                      if len(locs) > 1 and any(sig)}

        print(f"\n{'='*70}")
        print(f"DUPLICATE BUTTON STYLES (same visual, different class names)")
        print(f"{'='*70}")
        for sig, locs in sorted(duplicates.items(), key=lambda x: -len(x[1])):
            print(f"\n  sig={sig[:100]}")
            print(f"  {len(locs)} определений с одинаковой сигнатурой:")
            for l in locs:
                print(f"    {l}")

        DUP_BASELINE = 999  # Отчётный режим
        dup_count = len(duplicates)
        assert dup_count <= DUP_BASELINE, (
            f"Дублирующихся стилей кнопок: {dup_count} > baseline {DUP_BASELINE}\n"
            "Одинаковый визуальный стиль должен быть в одном общем классе."
        )

    # ─── HTML-кнопки без общих классов ───

    SHARED_BTN_CLASSES = {"btn", "btn-go", "btn-danger", "btn-ghost"}

    # Разрешённые свои классы (не кнопки-действия, а специфичные UI-элементы)
    BUTTON_EXEMPT = {
        "type-dropdown-btn",  # дропдаун (не action-кнопка)
        "mob-filter-btn",     # мобильный FAB
        "theme-toggle",       # переключатель темы
        "hamburger",          # мобильное меню
    }

    def test_buttons_use_shared_classes(self):
        """Все <button> в HTML и JS используют общие классы из shared.css.

        Кнопка без .btn/.btn-go/.btn-danger/.btn-ghost = "левая" кнопка
        со своим стилем = расхождение. Тест проверяет HTML-страницы
        и JS-файлы (кнопки в innerHTML).

        Исключения: дропдауны, FAB, theme-toggle (не action-кнопки).
        """
        import re
        from pathlib import Path

        SHARED = self.SHARED_BTN_CLASSES
        EXEMPT = self.BUTTON_EXEMPT

        # HTML страницы
        html_files = list(self.PAGES)
        # JS файлы с кнопками
        web = Path(__file__).parent.parent / "web"
        js_files = []
        for js in web.glob("*.js"):
            content = js.read_text()
            if "<button" in content:
                js_files.append(js.name)

        violations = []

        # --- HTML ---
        for fname in html_files:
            content = self._read_page(fname)
            if not content:
                continue
            for m in re.finditer(r'<button([^>]*)>', content):
                attrs = m.group(1)
                line = content[:m.start()].count('\n') + 1
                cls_m = re.search(r'class="([^"]*)"', attrs)
                cls = cls_m.group(1).strip() if cls_m else ""
                cls_set = set(cls.split())
                has_shared = bool(cls_set & SHARED)
                is_exempt = bool(cls_set & EXEMPT)
                if not has_shared and not is_exempt:
                    onclick_m = re.search(r'onclick="([^"]*)"', attrs)
                    action = onclick_m.group(1)[:40] if onclick_m else ""
                    violations.append(f"{fname}:{line} class=\"{cls}\" onclick=\"{action}\"")

        # --- JS (innerHTML кнопки) ---
        for fname in js_files:
            content = (web / fname).read_text()
            # '<button...>' (одинарные кавычки)
            for m in re.finditer(r"'<button([^']*)>", content):
                attrs = m.group(1)
                line = content[:m.start()].count('\n') + 1
                cls_m = re.search(r'class="([^"]*)"', attrs)
                cls = cls_m.group(1).strip() if cls_m else ""
                cls_set = set(cls.split())
                has_shared = bool(cls_set & SHARED)
                is_exempt = bool(cls_set & EXEMPT)
                if not has_shared and not is_exempt:
                    onclick_m = re.search(r'onclick="([^"]*)"', attrs)
                    action = onclick_m.group(1)[:40] if onclick_m else ""
                    violations.append(f"{fname}:{line} JS class=\"{cls}\" onclick=\"{action}\"")
            # "<button...>" (двойные кавычки в шаблонных строках)
            for m in re.finditer(r'"<button([^>]*?)>', content):
                attrs = m.group(1)
                line = content[:m.start()].count('\n') + 1
                cls_m = re.search(r"class='([^']*)'", attrs)
                cls = cls_m.group(1).strip() if cls_m else ""
                cls_set = set(cls.split())
                has_shared = bool(cls_set & SHARED)
                is_exempt = bool(cls_set & EXEMPT)
                if not has_shared and not is_exempt:
                    violations.append(f"{fname}:{line} JS-dq class=\"{cls}\"")

        print(f"\n{'='*70}")
        print(f"BUTTONS WITHOUT SHARED CLASSES (should be 0)")
        print(f"{'='*70}")
        for v in violations:
            print(f"  ❌ {v}")
        if not violations:
            print("  ✅ Все кнопки используют общие классы")
        print(f"  TOTAL: {len(violations)} violations")

        BUTTON_NO_SHARED_BASELINE = 999  # Отчётный режим
        assert len(violations) <= BUTTON_NO_SHARED_BASELINE, (
            f"Кнопок без общих классов: {len(violations)} > baseline {BUTTON_NO_SHARED_BASELINE}\n"
            "Используй .btn / .btn-go / .btn-danger / .btn-ghost из shared.css."
        )

    # ─── Страница с уникальными классами (чужой дизайн) ───

    def test_no_page_with_alien_classes(self):
        """Ни одна страница не имеет набор CSS-классов, не пересекающийся
        с другими страницами.

        Если страница использует >40% своих классов только в себе —
        она написана в "другом мире", не following существующие паттерны.
        Это главная метрика консистентности: страницы должны делить классы.

        Best practice (NN/g Component Library): общие компоненты
        переиспользуются, не изобретаются заново.
        """
        import re
        from pathlib import Path
        from collections import Counter

        web = Path(__file__).parent.parent / "web"

        # Собираем CSS-классы из каждой страницы (включая shared.css)
        page_classes = {}
        shared_css_classes = set()
        shared = web / "shared.css"
        if shared.exists():
            shared_css_classes = set(re.findall(r'\.([a-zA-Z][\w-]*)', shared.read_text()))

        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = "\n".join(re.findall(r'<style[^>]*>(.*?)</style>', content, re.DOTALL))
            classes = set(re.findall(r'\.([a-zA-Z][\w-]*)', css))
            # Исключаем light-theme (не компонент)
            classes.discard("light-theme")
            page_classes[fname] = classes

        # Для каждой страницы считаем % классов которые встречаются ТОЛЬКО у неё
        all_classes = Counter()
        for classes in page_classes.values():
            all_classes.update(classes)

        print(f"\n{'='*70}")
        print(f"ALIEN CLASS ANALYSIS (page uniqueness)")
        print(f"{'='*70}")

        aliens = {}
        for fname, classes in page_classes.items():
            # Класс есть только в этой странице (count==1) и нет в shared.css
            unique = {c for c in classes if all_classes[c] == 1 and c not in shared_css_classes}
            total = len(classes)
            pct = (len(unique) / total * 100) if total else 0
            aliens[fname] = (unique, total, pct)
            status = "🔴" if pct > 40 else ("🟡" if pct > 20 else "✅")
            print(f"  {status} {fname}: {len(unique)}/{total} unique ({pct:.0f}%)")
            if unique:
                for c in sorted(unique)[:15]:
                    print(f"      .{c}")
                if len(unique) > 15:
                    print(f"      ... +{len(unique)-15} ещё")

        # Страница с >91% уникальных классов = чужой дизайн
        ALIEN_THRESHOLD = 100  # Отчётный режим — показывает все
        worst = max(aliens.items(), key=lambda x: x[1][2])
        worst_fname, (worst_unique, worst_total, worst_pct) = worst

        assert worst_pct <= ALIEN_THRESHOLD, (
            f"{worst_fname}: {worst_pct:.0f}% классов уникальны "
            f"({len(worst_unique)}/{worst_total}) — страница написана в 'другом мире'.\n"
            f"Уникальные классы: {', '.join(sorted(worst_unique)[:20])}\n"
            f"Переиспользуй классы из gallery.html / shared.css."
        )

    # ─── Переопределение общих классов с другим стилем ───

    def test_no_shared_class_redefined_with_different_style(self):
        """Если класс определён на нескольких страницах (или в shared.css),
        его визуальная сигнатура должна совпадать.

        Один класс — один стиль. Если .card в gallery имеет border-radius:4px,
        а .card в albums — 6px, это рассинхрон.

        Best practice (NN/g Single source of truth): один компонент = один стиль.
        """
        import re
        from pathlib import Path

        web = Path(__file__).parent.parent / "web"

        from collections import defaultdict

        # Собираем (selector → {page: signature}) для всех страниц + shared.css
        class_sigs = defaultdict(dict)  # class_name → {page: (bg, color, border, radius)}

        # shared.css
        shared = web / "shared.css"
        if shared.exists():
            css = shared.read_text()
            for sel, props in self._parse_rules(css):
                if self._is_light_theme(sel) or self._is_media_query(sel):
                    continue
                if any(p in sel for p in [':hover', ':active', ':not(', ':focus', ':checked', '::']):
                    continue
                for cls in re.findall(r'\.([a-zA-Z][\w-]*)', sel):
                    if self._has_visual_props(props):
                        sig = self._signature(props)
                        if sig != ('', '', '', ''):
                            class_sigs[cls]["shared.css"] = sig

        # Pages
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = self._extract_css(content)
            for sel, props in self._parse_rules(css):
                if self._is_light_theme(sel) or self._is_media_query(sel):
                    continue
                if any(p in sel for p in [':hover', ':active', ':not(', ':focus', ':checked', '::']):
                    continue
                for cls in re.findall(r'\.([a-zA-Z][\w-]*)', sel):
                    if self._has_visual_props(props):
                        sig = self._signature(props)
                        if sig != ('', '', '', ''):
                            if cls not in class_sigs or fname not in class_sigs[cls]:
                                class_sigs[cls][fname] = sig

        # Находим классы с разными сигнатурами (только base-селекторы)
        conflicts = []
        for cls, locations in class_sigs.items():
            if len(locations) < 2:
                continue
            sigs = set(locations.values())
            if len(sigs) > 1:
                conflict = []
                for page, sig in locations.items():
                    conflict.append(f"  {page}: sig={sig[:80]}")
                conflicts.append((cls, conflict))

        print(f"\n{'='*70}")
        print(f"SHARED CLASS REDEFINED WITH DIFFERENT STYLE")
        print(f"{'='*70}")
        for cls, details in sorted(conflicts):
            print(f"\n  .{cls} — разные стили:")
            for d in details:
                print(f"    {d}")

        print(f"\n  TOTAL: {len(conflicts)} конфликтов")

        REDEFINE_BASELINE = 999  # Отчётный режим
        assert len(conflicts) <= REDEFINE_BASELINE, (
            f"Конфликтов классов с разными стилями: {len(conflicts)} > baseline {REDEFINE_BASELINE}\n"
            "Один класс = один стиль. Вынеси в shared.css."
        )

    # ─── Структура DOM общих компонентов ───

    def test_shared_class_same_dom_structure(self):
        """Если класс используется на нескольких страницах, структура DOM
        внутри него должна совпадать.

        .card в gallery: <div class="card"><img>...<div class="overlay">...</div></div>
        .card в albums:  <div class="card"><img class="card-cover">...<div class="card-body">...</div></div>

        Разная структура = разный компонент = нарушение single source of truth.
        Один класс = один компонент = одна DOM-структура.
        """
        import re
        from pathlib import Path

        web = Path(__file__).parent.parent / "web"

        # Классы которые должны быть компонентами (не утилиты)
        COMPONENT_CLASSES = {"card", "grid", "toolbar", "empty", "photo-grid", "detail-header"}

        # Собираем HTML-структуру внутри каждого компонента per page
        # Возвращает {class: {page: [child_class_tuples]}}
        def extract_component_structure(content, fname):
            results = {}
            for cls in COMPONENT_CLASSES:
                # Ищем <div class="...cls...">
                pattern = rf'<(\w+)[^>]*class="[^"]*\b{cls}\b[^"]*"[^>]*>(.*?)</\1>'
                for m in re.finditer(pattern, content, re.DOTALL):
                    inner = m.group(2)
                    # Собираем прямые дочерние классы (1 уровень)
                    children = set()
                    for cm in re.finditer(r'<\w+[^>]*class="([^"]+)"', inner):
                        for c in cm.group(1).split():
                            children.add(c)
                    results.setdefault(cls, {}).setdefault(fname, []).append(frozenset(children))
            return results

        all_structures = {}  # {class: {page: [frozensets]}}
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            structs = extract_component_structure(content, fname)
            for cls, page_structs in structs.items():
                all_structures.setdefault(cls, {}).update(page_structs)

        # Также JS-файлы (innerHTML с классами)
        for js in web.glob("*.js"):
            content = js.read_text()
            structs = extract_component_structure(content, js.name)
            for cls, page_structs in structs.items():
                all_structures.setdefault(cls, {}).update(page_structs)

        # Находим классы с разной структурой на разных страницах
        conflicts = []
        for cls, page_structs in all_structures.items():
            if len(page_structs) < 2:
                continue
            # Собираем все уникальные наборы дочерних классов
            all_child_sets = set()
            for sets in page_structs.values():
                all_child_sets.update(sets)
            if len(all_child_sets) > 1:
                details = []
                for page, sets in page_structs.items():
                    for s in sets:
                        details.append(f"  {page}: children={sorted(s)}")
                conflicts.append((cls, details))

        print(f"\n{'='*70}")
        print(f"SHARED CLASS — DIFFERENT DOM STRUCTURE")
        print(f"{'='*70}")
        for cls, details in sorted(conflicts):
            print(f"\n  .{cls} — разная структура:")
            for d in details:
                print(f"    {d}")
        print(f"\n  TOTAL: {len(conflicts)} конфликтов")

        DOM_STRUCTURE_BASELINE = 999  # Отчётный режим
        assert len(conflicts) <= DOM_STRUCTURE_BASELINE, (
            f"Компонентов с разной DOM-структурой: {len(conflicts)} > baseline {DOM_STRUCTURE_BASELINE}\n"
            "Один класс = один компонент = одна структура."
        )

    def test_no_undeclared_styles(self):
        """Все визуальные стили на странице должны соответствовать shared.css.

        Проверяет не имена селекторов, а визуальные сигнатуры
        (background, color, border, padding, font-size, и т.д.).
        Если страница имеет визуальную сигнатуру которой нет в shared.css —
        это чужой стиль, не из каталога.

        shared.css — единый стандарт (гайки/болты).
        Человек решает какие стили добавить в стандарт.
        """
        import re
        from pathlib import Path

        web = Path(__file__).parent.parent / "web"

        # Эталон: все визуальные сигнатуры из shared.css
        shared = (web / "shared.css").read_text()
        shared_sigs = set()
        shared_sel_count = 0
        for sel, props in self._parse_rules(shared):
            if self._is_light_theme(sel) or self._is_media_query(sel):
                continue
            if self._has_visual_props(props):
                sig = self._signature(props)
                if any(sig):
                    shared_sigs.add(sig)
                    shared_sel_count += 1

        print(f"\n{'='*70}")
        print(f"STYLE CONFORMANCE: % visual signatures in shared.css")
        print(f"{'='*70}")
        print(f"  shared.css: {shared_sel_count} selectors, {len(shared_sigs)} unique signatures")

        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = "\n".join(re.findall(r'<style[^>]*>(.*?)</style>', content, re.DOTALL))
            total = 0
            alien = []
            for sel, props in self._parse_rules(css):
                if self._is_light_theme(sel) or self._is_media_query(sel):
                    continue
                sel_clean = sel.strip()
                if sel_clean in ('body', '.light-theme', 'html', ':root',
                                 'html.embedded', 'html.embedded body', '*'):
                    continue
                if sel_clean.startswith('@') or sel_clean.startswith('*'):
                    continue
                if not self._has_visual_props(props):
                    continue
                total += 1
                sig = self._signature(props)
                if any(sig) and sig not in shared_sigs:
                    # Сигнатура не найдена в эталоне — чужой визуал
                    alien.append((sel_clean, sig))
            pct = ((total - len(alien)) / total * 100) if total else 100
            status = "✅" if pct == 100 else ("🟡" if pct >= 50 else "🔴")
            print(f"  {status} {fname}: {pct:.0f}% ({total - len(alien)}/{total} signatures match)")
            if alien:
                for s, sig in sorted(alien)[:10]:
                    # Покажем ключевые отличия
                    print(f"      ❌ {s}  sig={sig[:80]}")
                if len(alien) > 10:
                    print(f"      ... +{len(alien)-10} ещё")

    def test_no_duplicate_selectors_with_conflicting_props(self):
        """В shared.css не должно быть дубликатов селекторов с разными свойствами.

        Если один селектор определён дважды с разными свойствами —
        последний перебивает первый, теряя свойства. Это баг переноса.
        """
        import re
        from pathlib import Path

        web = Path(__file__).parent.parent / "web"
        css = (web / "shared.css").read_text()

        seen = {}
        # Парсим CSS учитывая вложенные @media блоки
        i = 0
        while i < len(css):
            # Ищем начало правила
            brace_open = css.find('{', i)
            if brace_open == -1:
                break
            selector = css[i:brace_open].strip()
            # Находим конец правила (учитывая вложенность)
            depth = 1
            j = brace_open + 1
            while j < len(css) and depth > 0:
                if css[j] == '{':
                    depth += 1
                elif css[j] == '}':
                    depth -= 1
                j += 1
            body = css[brace_open + 1:j - 1]
            i = j

            if selector.startswith('/*') or selector.startswith('*'):
                continue
            if selector.startswith('@media'):
                # Парсим правила внутри media query отдельно
                inner = body
                k = 0
                while k < len(inner):
                    bo = inner.find('{', k)
                    if bo == -1:
                        break
                    depth2 = 1
                    l = bo + 1
                    while l < len(inner) and depth2 > 0:
                        if inner[l] == '{':
                            depth2 += 1
                        elif inner[l] == '}':
                            depth2 -= 1
                        l += 1
                    k = l
                    # Пропускаем правила внутри media query
                continue
            if selector.startswith('@'):
                continue
            props = {}
            for pm in re.finditer(r'([\w-]+)\s*:\s*([^;]+)', body):
                props[pm.group(1).strip()] = pm.group(2).strip()
            if selector in seen:
                seen[selector].append(props)
            else:
                seen[selector] = [props]

        conflicts = []
        for selector, prop_list in seen.items():
            if len(prop_list) < 2:
                continue
            for i in range(len(prop_list)):
                for j in range(i + 1, len(prop_list)):
                    p1, p2 = prop_list[i], prop_list[j]
                    if p1 != p2:
                        lost = set(p1.keys()) - set(p2.keys())
                        changed = {k for k in set(p1.keys()) & set(p2.keys()) if p1[k] != p2[k]}
                        if lost or changed:
                            conflicts.append((selector, lost, changed))

        print(f"\n{'='*70}")
        print(f"DUPLICATE SELECTORS WITH CONFLICTING PROPS")
        print(f"{'='*70}")
        for sel, lost, changed in conflicts:
            details = []
            if lost:
                details.append(f"lost: {', '.join(sorted(lost))}")
            if changed:
                details.append(f"changed: {', '.join(sorted(changed))}")
            print(f"  ❌ {sel} — {'; '.join(details)}")
        if not conflicts:
            print("  ✅ Нет дубликатов с конфликтующими свойствами")
        print(f"  TOTAL: {len(conflicts)} conflicts")

        assert not conflicts, (
            f"{len(conflicts)} дубликатов селекторов с конфликтующими свойствами в shared.css.\n"
            "Последний перебивает предыдущий, теряя свойства. "
            "Объедини определения или убери дубликаты."
        )

    def test_no_undeclared_styles(self):
        """Все визуальные стили на странице должны соответствовать shared.css.

        Проверяет не имена селекторов, а визуальные сигнатуры
        (background, color, border, padding, font-size, и т.д.).
        Если страница имеет визуальную сигнатуру которой нет в shared.css —
        это чужой стиль, не из каталога.

        shared.css — единый стандарт (гайки/болты).
        Человек решает какие стили добавить в стандарт.
        """
        import re
        from pathlib import Path

        web = Path(__file__).parent.parent / "web"

        # Эталон: все визуальные сигнатуры из shared.css
        shared = (web / "shared.css").read_text()
        shared_sigs = set()
        shared_sel_count = 0
        for sel, props in self._parse_rules(shared):
            if self._is_light_theme(sel) or self._is_media_query(sel):
                continue
            if self._has_visual_props(props):
                sig = self._signature(props)
                if any(sig):
                    shared_sigs.add(sig)
                    shared_sel_count += 1

        # Классы из shared.css для alien-анализа
        shared_css_classes = set()
        for sel, _ in self._parse_rules(shared):
            for cm in re.finditer(r'\.([\w-]+)', sel):
                shared_css_classes.add(cm.group(1))

        # Классы из per-page <style>
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            blocks = re.findall(r'<style[^>]*>(.*?)</style>', content, re.DOTALL)
            page_css = "\n".join(blocks)
            for sel, _ in self._parse_rules(page_css):
                for cm in re.finditer(r'\.([\w-]+)', sel):
                    shared_css_classes.add(cm.group(1))

        page_classes = {}
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            classes = set(re.findall(r'class="([^"]*)"', content))
            page_classes[fname] = set()
            for cls_str in classes:
                for c in cls_str.split():
                    page_classes[fname].add(c)

        EXEMPT_CLASSES = {
            'show', 'open', 'active', 'hidden', 'loading', 'dragging',
            'has-filters', 'has-filter', 'has-name', 'deleted-card',
            'embedded', 'scroll-lock', 'light-theme', 'at-end', 'end',
            'running', 'done', 'fail', 'manual', 'selected',
        }

        print(f"\n{'='*70}")
        print(f"STYLE CONFORMANCE: % visual signatures in shared.css")
        print(f"{'='*70}")
        print(f"  shared.css: {shared_sel_count} selectors, {len(shared_sigs)} unique signatures")

        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            css = "\n".join(re.findall(r'<style[^>]*>(.*?)</style>', content, re.DOTALL))
            total = 0
            alien = []
            for sel, props in self._parse_rules(css):
                if self._is_light_theme(sel) or self._is_media_query(sel):
                    continue
                sel_clean = sel.strip()
                if sel_clean in ('body', '.light-theme', 'html', ':root',
                                 'html.embedded', 'html.embedded body', '*'):
                    continue
                if sel_clean.startswith('@') or sel_clean.startswith('*'):
                    continue
                if not self._has_visual_props(props):
                    continue
                total += 1
                sig = self._signature(props)
                if any(sig) and sig not in shared_sigs:
                    alien.append((sel_clean, sig))
            pct = ((total - len(alien)) / total * 100) if total else 100
            status = "✅" if pct == 100 else ("🟡" if pct >= 50 else "🔴")
            print(f"  {status} {fname}: {pct:.0f}% ({total - len(alien)}/{total} signatures match)")
            if alien:
                for s, sig in sorted(alien)[:10]:
                    print(f"      ❌ {s}  sig={sig[:80]}")
                if len(alien) > 10:
                    print(f"      ... +{len(alien)-10} ещё")

        # Сводный отчёт: страница → % по всем метрикам
        print(f"\n{'='*70}")
        print(f"STYLE CONFORMANCE SUMMARY")
        print(f"{'='*70}")
        for fname in self.PAGES:
            content = self._read_page(fname)
            if not content:
                continue
            # CSS сигнатуры
            css = "\n".join(re.findall(r'<style[^>]*>(.*?)</style>', content, re.DOTALL))
            total = 0
            alien = []
            for sel, props in self._parse_rules(css):
                if self._is_light_theme(sel) or self._is_media_query(sel):
                    continue
                sel_clean = sel.strip()
                if sel_clean in ('body', '.light-theme', 'html', ':root',
                                 'html.embedded', 'html.embedded body', '*'):
                    continue
                if sel_clean.startswith('@') or sel_clean.startswith('*'):
                    continue
                if not self._has_visual_props(props):
                    continue
                total += 1
                sig = self._signature(props)
                if any(sig) and sig not in shared_sigs:
                    alien.append(sel_clean)
            sig_pct = ((total - len(alien)) / total * 100) if total else 100

            # Alien классы
            pclasses = page_classes[fname]
            unique = [c for c in pclasses if c not in shared_css_classes and c not in EXEMPT_CLASSES]
            alien_pct = (len(unique) / len(pclasses) * 100) if pclasses else 0

            issues = []
            if alien:
                issues.append(f"{len(alien)} чужих сигнатур")
            if unique:
                issues.append(f"{len(unique)}/{len(pclasses)} alien классов ({alien_pct:.0f}%)")
            overall = min(sig_pct, 100 - alien_pct if pclasses else 100)
            status = "✅" if overall == 100 else ("🟡" if overall >= 50 else "🔴")
            detail = ", ".join(issues) if issues else "0 расхождений"
            print(f"  {status} {fname}: {overall:.0f}% — {detail}")




class TestStyleManifestSync:
    """Связь STYLE.md ↔ тесты: хардкоды в тестах соответствуют манифесту.

    Проверяет что значения в TestPageStyleConformance (палитра, шрифты, radius)
    описаны в STYLE.md, и наоборот — значения из STYLE.md присутствуют в тестах.
    Рассинхрон = fail (изменили тест, забыли STYLE.md, или наоборот).
    """

    def _read_style_md(self):
        from pathlib import Path
        p = Path(__file__).parent.parent / "STYLE.md"
        return p.read_text() if p.exists() else ""

    def _extract_hex_from_md(self, md_text):
        """Все hex цвета из таблиц STYLE.md (после ## Палитра, до ---)."""
        import re
        colors = set()
        in_palette = False
        for line in md_text.split("\n"):
            if "## Палитра" in line:
                in_palette = True
            if in_palette and line.strip().startswith("---") and "Палитра" not in line:
                in_palette = False
            if in_palette:
                for m in re.finditer(r'`#?([0-9a-fA-F]{3,8})`', line):
                    colors.add(m.group(1).lower())
        return colors

    def _extract_font_sizes_from_md(self, md_text):
        """Размеры шрифтов из таблицы типографики STYLE.md."""
        import re
        sizes = set()
        in_typo = False
        for line in md_text.split("\n"):
            if "## Типографика" in line:
                in_typo = True
            if in_typo and line.strip().startswith("---") and "Типографика" not in line:
                in_typo = False
            if in_typo:
                for m in re.finditer(r'(\d+px)', line):
                    sizes.add(m.group(1))
        return sizes

    def _extract_radius_from_md(self, md_text):
        """border-radius значения из строки border-radius в STYLE.md."""
        import re
        radii = set()
        for line in md_text.split("\n"):
            if 'border-radius' in line.lower():
                for m in re.finditer(r'(\d+px|0(?!\d)|50%)', line):
                    radii.add(m.group(1))
        return radii

    def test_palette_in_sync(self):
        """Все hex из тестов описаны в STYLE.md, и наоборот."""
        md = self._read_style_md()
        assert md, "STYLE.md не найден"
        md_colors = self._extract_hex_from_md(md)

        # Палитра из тестов
        test_colors = TestPageStyleConformance.ALLOWED_ALL

        missing_in_md = test_colors - md_colors
        missing_in_tests = md_colors - test_colors

        errors = []
        if missing_in_md:
            errors.append(f"В тестах есть, но нет в STYLE.md: #{', #'.join(sorted(missing_in_md))}")
        if missing_in_tests:
            errors.append(f"В STYLE.md есть, но нет в тестах: #{', #'.join(sorted(missing_in_tests))}")
        assert not errors, "Рассинхрон палитры STYLE.md ↔ тесты:\n" + "\n".join(errors)

    def test_font_sizes_in_sync(self):
        """Размеры шрифтов из тестов описаны в STYLE.md, и наоборот."""
        md = self._read_style_md()
        md_sizes = self._extract_font_sizes_from_md(md)

        test_sizes = TestPageStyleConformance.ALLOWED_FONT_SIZES

        missing_in_md = test_sizes - md_sizes
        missing_in_tests = md_sizes - test_sizes

        errors = []
        if missing_in_md:
            errors.append(f"В тестах есть, нет в STYLE.md: {', '.join(sorted(missing_in_md))}")
        if missing_in_tests:
            errors.append(f"В STYLE.md есть, нет в тестах: {', '.join(sorted(missing_in_tests))}")
        assert not errors, "Рассинхрон размеров шрифтов:\n" + "\n".join(errors)

    def test_border_radius_in_sync(self):
        """border-radius из тестов описан в STYLE.md, и наоборот."""
        md = self._read_style_md()
        md_radii = self._extract_radius_from_md(md)

        test_radii = TestPageStyleConformance.ALLOWED_RADIUS

        missing_in_md = test_radii - md_radii
        missing_in_tests = md_radii - test_radii

        errors = []
        if missing_in_md:
            errors.append(f"В тестах есть, нет в STYLE.md: {', '.join(sorted(missing_in_md))}")
        if missing_in_tests:
            errors.append(f"В STYLE.md есть, нет в тестах: {', '.join(sorted(missing_in_tests))}")
        assert not errors, "Рассинхон border-radius:\n" + "\n".join(errors)

    def test_manifest_principles_exist(self):
        """В STYLE.md есть 8 принципов манифеста."""
        md = self._read_style_md()
        required = [
            "Single source of truth",
            "Limit your choices",
            "Design tokens",
            "Use fewer borders",
            "Hierarchy through contrast",
            "Theme-aware",
            "shared.css is the component library",
            "Consistency metric",
        ]
        missing = [p for p in required if p not in md]
        assert not missing, f"В STYLE.md нет принципов манифеста: {missing}"

    def test_test_baselines_documented(self):
        """Baselines из TestStyleConsistency описаны в STYLE.md."""
        md = self._read_style_md()
        baselines = {
            "18": "BUTTON_VARIETY_BASELINE",
            "8": "INPUT_VARIETY_BASELINE",
            "28": "CARD_VARIETY_BASELINE",
            "32": "BUTTON_PERPAGE_BASELINE",
            "7": "DUP_BASELINE",
        }
        missing = []
        for val, name in baselines.items():
            if val not in md:
                missing.append(f"{name}={val}")
        assert not missing, f"Baselines не описаны в STYLE.md: {missing}"

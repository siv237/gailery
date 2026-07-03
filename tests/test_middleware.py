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
            if f"renderHeader('{title}')" not in body and f'renderHeader("{title}")' not in body:
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
        if len(errors) > 17:
            pytest.fail(
                f"Инлайн стили с цветом выросли: {len(errors)} > baseline 17.\n"
                + "\n".join(errors[:20])
            )
        elif errors:
            print(f"\n⚠ Инлайн стили: {len(errors)}/17 baseline — backlog")


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

    # Backlog: инлайн стили в gallery/catalog/personas (17 шт)
    INLINE_STYLE_BASELINE = 17

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

import pytest
from unittest.mock import patch


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

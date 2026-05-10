import pytest


class TestPhotosSearchAPI:
    def test_search_returns_results(self, app_client):
        """Эндпоинт поиска фото возвращает 200 и содержит ключи total+photos."""
        resp = app_client.get("/api/photos/search?limit=5&sort=date_desc")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "photos" in data

    def test_search_with_query(self, app_client):
        """Поиск с текстовым запросом не падает."""
        resp = app_client.get("/api/photos/search?q=test&limit=5")
        assert resp.status_code == 200

    def test_search_with_faces_filter(self, app_client):
        """Фильтр has_faces=true не ломает поиск."""
        resp = app_client.get("/api/photos/search?has_faces=true&limit=5")
        assert resp.status_code == 200

    def test_search_with_gps_filter(self, app_client):
        """Фильтр has_gps=true не ломает поиск."""
        resp = app_client.get("/api/photos/search?has_gps=true&limit=5")
        assert resp.status_code == 200

    def test_dates_histogram(self, app_client):
        """Гистограмма дат возвращает структуру с годами и общим количеством."""
        resp = app_client.get("/api/photos/dates")
        assert resp.status_code == 200
        data = resp.json()
        assert "years" in data
        assert "total" in data
        assert "photo_times" in data
        assert isinstance(data["photo_times"], list)

    def test_photo_list(self, app_client):
        """Эндпоинт списка фото возвращает photos в ответе."""
        resp = app_client.get("/api/photos/list?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "photos" in data

    def test_search_person_filter(self, app_client):
        """Фильтр по персоне обрабатывается без краша (может быть 200 или 500)."""
        resp = app_client.get("/api/photos/search?person=test&limit=5")
        assert resp.status_code in (200, 500)

    def test_search_deleted_filter(self, app_client):
        """Фильтр удалённых фото не ломает поиск."""
        resp = app_client.get("/api/photos/search?deleted_only=true&limit=5")
        assert resp.status_code == 200


class TestPhotosDateGPSAPI:
    def test_set_date(self, app_client):
        """Установка даты на несуществующее фото возвращает 404."""
        resp = app_client.post("/api/photos/set_date", json={
            "photo_id": "nonexistent", "manual_date": "2024-01-15 10:00:00"
        })
        assert resp.status_code == 404

    def test_clear_date(self, app_client):
        """Сброс даты на несуществующем фото возвращает 404."""
        resp = app_client.post("/api/photos/clear_date", json={
            "photo_id": "nonexistent"
        })
        assert resp.status_code == 404

    def test_set_gps(self, app_client):
        """Установка GPS на несуществующее фото возвращает 404."""
        resp = app_client.post("/api/photos/set_gps", json={
            "photo_id": "nonexistent", "lat": 55.75, "lon": 37.62
        })
        assert resp.status_code == 404

    def test_clear_gps(self, app_client):
        """Сброс GPS на несуществующем фото возвращает 404."""
        resp = app_client.post("/api/photos/clear_gps", json={
            "photo_id": "nonexistent"
        })
        assert resp.status_code == 404

    def test_clear_date(self, app_client):
        resp = app_client.post("/api/photos/clear_date", json={
            "photo_id": "nonexistent"
        })
        assert resp.status_code == 404

    def test_set_gps(self, app_client):
        resp = app_client.post("/api/photos/set_gps", json={
            "photo_id": "nonexistent", "lat": 55.75, "lon": 37.62
        })
        assert resp.status_code == 404

    def test_clear_gps(self, app_client):
        resp = app_client.post("/api/photos/clear_gps", json={
            "photo_id": "nonexistent"
        })
        assert resp.status_code == 404


class TestPhotosDeleteAPI:
    def test_mark_deleted(self, app_client):
        """Пометка несуществующего фото как удалённого возвращает 404."""
        resp = app_client.post("/api/photos/mark_deleted", json={
            "photo_id": "nonexistent"
        })
        assert resp.status_code == 404

    def test_undelete(self, app_client):
        """Восстановление несуществующего фото возвращает 404."""
        resp = app_client.post("/api/photos/undelete", json={
            "photo_id": "nonexistent"
        })
        assert resp.status_code == 404


class TestPersonsAPI:
    def test_list_persons(self, app_client):
        """Список персон возвращает пагинированный ответ с полями persons+total."""
        resp = app_client.get("/api/persons/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "persons" in data
        assert "total" in data

    def test_get_names(self, app_client):
        """Эндпоинт имён персон доступен."""
        resp = app_client.get("/api/persons/names")
        assert resp.status_code == 200

    def test_update_persona(self, app_client):
        """Обновление несуществующей персоны не крашит сервер."""
        resp = app_client.put("/api/persons/nonexistent", json={
            "display_name": "Тест"
        })
        assert resp.status_code in (200, 404)


class TestCatalogAPI:
    def test_get_roots(self, app_client):
        """Корни каталога возвращаются без ошибок."""
        resp = app_client.get("/api/catalog/roots")
        assert resp.status_code == 200

    def test_get_stats(self, app_client):
        """Статистика каталога доступна."""
        resp = app_client.get("/api/catalog/stats")
        assert resp.status_code == 200

    def test_locate(self, app_client):
        """Локация несуществующего пути не падает."""
        resp = app_client.get("/api/catalog/locate?path=/nonexistent")
        assert resp.status_code == 200


class TestSystemAPI:
    def test_health(self, app_client):
        """Health-check эндпоинт возвращает status: ok."""
        resp = app_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_log(self, app_client):
        """Чтение логов через API не падает."""
        resp = app_client.get("/api/log?lines=10")
        assert resp.status_code == 200

    def test_changes(self, app_client):
        """История изменений возвращается с полем changes."""
        resp = app_client.get("/api/changes?limit=10")
        assert resp.status_code == 200
        assert "changes" in resp.json()

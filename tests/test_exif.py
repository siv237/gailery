"""test_exif.py — юнит-тесты логики назначения дат (resolve_date) в exif.py.

TERTIARY: чистые функции, БД не трогаем.

Логика (когда EXIF/creation_time в файле нет):
- дата из папки — только ПОЛНАЯ (год+месяц+день: 2026/07/28); время папка
  не хранит → время берётся из имени файла;
- папка неполная (2026/07) → дата+время из имени файла (видеорегистратор
  EMER260712-130023-002964.MOV → 12.07.2026 13:00:23);
- ничего не нашлось → mtime.
"""
import pytest

from exif import resolve_date, _match_filename_datetime, _extract_folder_full_ymd


class TestMatchFilenameDatetime:
    def test_dashcam_emer(self):
        assert _match_filename_datetime("EMER260712-130023-002964.MOV") == (2026, 7, 12, 13, 0, 23)

    def test_dashcam_mer_ile(self):
        assert _match_filename_datetime("MER260723-172650-003089.MOV") == (2026, 7, 23, 17, 26, 50)
        assert _match_filename_datetime("ILE260727-163105-003206.MOV") == (2026, 7, 27, 16, 31, 5)

    def test_full_year_datetime(self):
        assert _match_filename_datetime("20260712_130023.MOV") == (2026, 7, 12, 13, 0, 23)

    def test_compact_14_digits(self):
        assert _match_filename_datetime("lv_0_20260719171750.mp4") == (2026, 7, 19, 17, 17, 50)

    def test_invalid_month_rejected(self):
        # ABC123456-789012: mo=34 невалиден
        assert _match_filename_datetime("ABC123456-789012.MOV") is None

    def test_no_date_in_name(self):
        assert _match_filename_datetime("DSC04335.JPG") is None
        assert _match_filename_datetime("video.mp4") is None


class TestExtractFolderFullYmd:
    def test_triplet_full(self):
        assert _extract_folder_full_ymd("/photos/2026/07/28/video.MOV") == (2026, 7, 28)

    def test_dotted_folder(self):
        assert _extract_folder_full_ymd("/photos/2026.07.28/video.MOV") == (2026, 7, 28)

    def test_year_month_only_is_incomplete(self):
        # 2026/07 — только год+месяц, дата неполная
        assert _extract_folder_full_ymd("/photos/2026/07/video.MOV") is None

    def test_named_folder_no_date(self):
        assert _extract_folder_full_ymd("/photos/отпуск/видео.MOV") is None


class TestResolveDate:
    def test_dashcam_in_year_month_folder(self):
        """Главный кейс: регистратор в папке 2026/07 → дата+время из имени."""
        r, conflict = resolve_date(
            None, "/mnt/Foto/2026/07/отпуск/Видеорегистратор/EMER260712-130023-002964.MOV")
        assert r == "2026-07-12 13:00:23"
        assert conflict is False

    def test_full_folder_date_no_time_in_name(self):
        """Полная папка 2026/07/28 + имя без даты → дата из папки, полночь."""
        r, _ = resolve_date(None, "/photos/2026/07/28/clip.mp4")
        assert r == "2026-07-28 00:00:00"

    def test_full_folder_date_time_from_name(self):
        """Полная папка дала дату, но не время → время из имени файла."""
        r, _ = resolve_date(None, "/photos/2026/07/28/EMER260728-130023-000001.MOV")
        assert r == "2026-07-28 13:00:23"

    def test_img_name_date_kept(self):
        """IMG_20260715 без EXIF в неполной папке — дата из имени (старое поведение)."""
        r, _ = resolve_date(None, "/photos/2026/07/IMG_20260715.JPG")
        assert r == "2026-07-15 00:00:00"

    def test_fallback_mtime(self):
        """Ничего нет → mtime."""
        import os
        mt = 1752333600  # 12.07.2026 ~18:20 (+10)
        r, _ = resolve_date(None, "/photos/clip.mp4", mtime=mt)
        assert r is not None and r != "2026-07-01 00:00:00"

    def test_exif_wins_over_all(self):
        r, conflict = resolve_date("2026:07:20 08:56:48", "/photos/2026/07/EMER260712-130023.MOV")
        assert r == "2026-07-20 08:56:48"
        assert conflict is False

    def test_jan1_midnight_exif_treated_as_missing(self):
        """01.01 00:00:00 в EXIF = отсутствие даты → идём по папкам/имени."""
        r, _ = resolve_date("2026:01:01 00:00:00",
                            "/photos/2026/07/EMER260712-130023-000001.MOV")
        assert r == "2026-07-12 13:00:23"


class TestVideoBranch:
    def test_uppercase_mov_treated_as_video(self, monkeypatch):
        """.MOV заглавными — видео-ветка (баг: path.endswith регистрозависим,
        .MOV шёл по ветке фото: без date_tz, duration, метаданных)."""
        import exif
        import video_metadata
        monkeypatch.setattr(video_metadata, "extract_metadata", lambda p: {
            "duration_seconds": 60.26, "width": 1920, "height": 1080,
            "codec": "h264", "gps": None, "raw": None,
            "creation_time": "", "utc_offset": ""})
        stats = {"gps_found": 0, "with_data": 0, "empty": 0, "processed": 0}
        updates, _ = exif._process_exif_result(
            "pid", "/x/2026/07/EMER260712-130023-002964.MOV", None, False, stats)
        assert updates.get("media_type") == "video"
        assert updates.get("duration_seconds") == 60.26
        assert updates.get("date") == "2026-07-12 13:00:23"
        assert updates.get("date_tz") == "local"
        assert updates.get("date_utc") == "2026-07-12 13:00:23"

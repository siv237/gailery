"""Тесты для system_helpers.py — чистые unit-тесты без GPU/MQTT."""
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestDeterminePipelineStep:
    def _setup(self, tmp_path):
        flag_dir = str(tmp_path / "flags")
        os.makedirs(flag_dir, exist_ok=True)
        return flag_dir, MagicMock()

    def test_idle_no_flags(self, tmp_path):
        """Нет флагов — шаг idle."""
        from system_helpers import _determine_pipeline_step
        flag_dir, mq = self._setup(tmp_path)
        mq.get_current_step.return_value = "idle"
        step, details, started, pl_started = _determine_pipeline_step(flag_dir, mq, {})
        assert step == "idle"
        assert details == ""

    def test_mqtt_step_overrides_flags(self, tmp_path):
        """MQTT шаг приоритетнее флагов."""
        from system_helpers import _determine_pipeline_step
        flag_dir, mq = self._setup(tmp_path)
        mq.get_current_step.return_value = "faces"
        step, details, _, _ = _determine_pipeline_step(flag_dir, mq, {})
        assert step == "faces"
        assert "FACES" in details

    def test_flag_describe(self, tmp_path):
        """Флаг describe определяет шаг."""
        from system_helpers import _determine_pipeline_step
        flag_dir, mq = self._setup(tmp_path)
        mq.get_current_step.return_value = "idle"
        Path(flag_dir, "describe").touch()
        step, details, _, _ = _determine_pipeline_step(flag_dir, mq, {})
        assert step == "describe"
        assert details == "DESCRIBE"

    def test_flag_embed(self, tmp_path):
        """Флаг embed определяет шаг."""
        from system_helpers import _determine_pipeline_step
        flag_dir, mq = self._setup(tmp_path)
        mq.get_current_step.return_value = "idle"
        Path(flag_dir, "embed").touch()
        step, details, _, _ = _determine_pipeline_step(flag_dir, mq, {})
        assert step == "embed"
        assert details == "EMBED"

    def test_flag_faces(self, tmp_path):
        """Флаг faces определяет шаг."""
        from system_helpers import _determine_pipeline_step
        flag_dir, mq = self._setup(tmp_path)
        mq.get_current_step.return_value = "idle"
        Path(flag_dir, "faces").touch()
        step, details, _, _ = _determine_pipeline_step(flag_dir, mq, {})
        assert step == "faces"
        assert details == "FACES"

    def test_flag_exif(self, tmp_path):
        """Флаг exif определяет шаг."""
        from system_helpers import _determine_pipeline_step
        flag_dir, mq = self._setup(tmp_path)
        mq.get_current_step.return_value = "idle"
        Path(flag_dir, "exif").touch()
        step, details, _, _ = _determine_pipeline_step(flag_dir, mq, {})
        assert step == "exif"
        assert details == "EXIF"

    def test_flag_pipeline(self, tmp_path):
        """Флаг pipeline определяет шаг."""
        from system_helpers import _determine_pipeline_step
        flag_dir, mq = self._setup(tmp_path)
        mq.get_current_step.return_value = "idle"
        Path(flag_dir, "pipeline").touch()
        step, details, _, pl_started = _determine_pipeline_step(flag_dir, mq, {})
        assert step == "pipeline"
        assert details == "PIPELINE"

    def test_no_mq(self, tmp_path):
        """Работа без MQTT (mq=None)."""
        from system_helpers import _determine_pipeline_step
        flag_dir = str(tmp_path / "flags")
        os.makedirs(flag_dir, exist_ok=True)
        Path(flag_dir, "embed").touch()
        step, details, _, _ = _determine_pipeline_step(flag_dir, None, {})
        assert step == "embed"


class TestGetGitInfo:
    def test_returns_commit_and_date(self):
        """Git info возвращает commit hash и date в реальном репо."""
        from system_helpers import _get_git_info
        commit, date = _get_git_info()
        # В реальном окружении — должны быть
        if commit:
            assert len(commit) >= 7
        if date:
            assert len(date) >= 8


class TestReadLogInfo:
    def test_empty_log(self, tmp_path):
        """Чтение несуществующего лога возвращает пустые структуры."""
        from system_helpers import _read_log_info
        progress, faces_phase, faces_detail = _read_log_info(str(tmp_path / "nonexistent.log"))
        assert progress == {}
        assert faces_phase == ""
        assert faces_detail == ""

    def test_log_with_tags(self, tmp_path):
        """Чтение лога с тегами извлекает progress."""
        from system_helpers import _read_log_info
        log_path = tmp_path / "test.log"
        log_path.write_text("[DESCRIBE] Processing batch 1\n[EMBED] Embedding photos\n")
        progress, faces_phase, faces_detail = _read_log_info(str(log_path))
        assert "describe" in progress
        assert "embed" in progress

    def test_log_faces_detecting(self, tmp_path):
        """Лог с [FACES] detecting определяет фазу."""
        from system_helpers import _read_log_info
        log_path = tmp_path / "faces.log"
        log_path.write_text("[FACES] detecting batch 5...\n")
        _, faces_phase, faces_detail = _read_log_info(str(log_path))
        assert faces_phase == "detecting"

    def test_log_faces_clustering(self, tmp_path):
        """Лог с Running DBSCAN определяет фазу clustering."""
        from system_helpers import _read_log_info
        log_path = tmp_path / "cluster.log"
        log_path.write_text("[FACES] Running DBSCAN on 100 vectors\n")
        _, faces_phase, faces_detail = _read_log_info(str(log_path))
        assert faces_phase == "clustering"
        assert faces_detail == "DBSCAN"

    def test_log_faces_done(self, tmp_path):
        """Лог с Clustering done определяет фазу done."""
        from system_helpers import _read_log_info
        log_path = tmp_path / "done.log"
        log_path.write_text("[FACES] Clustering done\n")
        _, faces_phase, _ = _read_log_info(str(log_path))
        assert faces_phase == "done"

    def test_log_faces_loading(self, tmp_path):
        """Лог с InsightFace loaded определяет фазу loading."""
        from system_helpers import _read_log_info
        log_path = tmp_path / "load.log"
        log_path.write_text("[FACES] InsightFace loaded successfully\n")
        _, faces_phase, faces_detail = _read_log_info(str(log_path))
        assert faces_phase == "loading"
        assert faces_detail == "InsightFace"


class TestCollectDisks:
    def test_returns_list(self):
        """_collect_disks возвращает список дисков."""
        from system_helpers import _collect_disks
        disks = _collect_disks()
        assert isinstance(disks, list)

    def test_disk_structure(self):
        """Каждый диск имеет нужные поля."""
        from system_helpers import _collect_disks
        disks = _collect_disks()
        for d in disks:
            assert "mount" in d
            assert "total_gib" in d
            assert "used_gib" in d
            assert "free_gib" in d
            assert "percent" in d


class TestCollectGpuProcesses:
    def test_returns_list(self):
        """_collect_gpu_processes возвращает список."""
        from system_helpers import _collect_gpu_processes
        procs = _collect_gpu_processes()
        assert isinstance(procs, list)


class TestCollectTopProcs:
    def test_returns_list(self):
        """_collect_top_procs возвращает список процессов."""
        from system_helpers import _collect_top_procs
        procs = _collect_top_procs()
        assert isinstance(procs, list)
        assert len(procs) <= 8

    def test_proc_structure(self):
        """Каждый процесс имеет pid, name, mem_pct, cpu_pct."""
        from system_helpers import _collect_top_procs
        procs = _collect_top_procs()
        for p in procs:
            assert "pid" in p
            assert "name" in p
            assert "mem_pct" in p
            assert "cpu_pct" in p


class TestCollectPipelineStats:
    def test_stats_empty_db(self, db):
        """_collect_pipeline_stats на пустой БД возвращает нули."""
        from system_helpers import _collect_pipeline_stats
        stats = _collect_pipeline_stats(db)
        assert stats["cf_total"] == 0
        assert stats["cf_canonical"] == 0
        assert stats["p_alive"] == 0
        assert stats["f_total"] == 0
        assert stats["pct_described"] == 0

    def test_stats_with_data(self, db_with_photos):
        """_collect_pipeline_stats с данными возвращает ненулевые счётчики."""
        from system_helpers import _collect_pipeline_stats
        db = db_with_photos
        db.update_catalog_file_by_path("/photos/2024/img1.jpg", described=1)
        stats = _collect_pipeline_stats(db)
        assert stats["cf_total"] >= 3
        assert stats["cf_canonical"] >= 3
        assert stats["p_alive"] >= 3

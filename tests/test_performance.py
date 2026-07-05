"""
Performance tests against the REAL production database.
These measure actual response times and FAIL when performance regresses.

Thresholds are generous (2x current measured times) to avoid flaky failures,
but tight enough to catch regressions like the 5s get_status() disaster.

Run: ./run_tests.sh tests/test_performance.py
     or:  pytest tests/test_performance.py -v --tb=short
"""
import time
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


BUDGETS = {
    "get_status": 3.0,
    "search_60": 1.5,
    "search_60_faces": 0.01,
    "dates_histogram": 1.5,
    "count_photos": 0.05,
    "get_all_faces": 2.0,
    "get_all_personas": 0.2,
    "targeted_faces_60": 0.05,
    "api_health": 0.5,
    "api_gallery_page": 0.5,
    "api_status": 3.0,
    "api_search_60": 2.0,
    "api_dates": 2.0,
    "api_config": 0.5,
    "api_log": 2.0,
    "api_status_concurrent_3": 6.0,
    "api_search_concurrent_3": 8.0,
}


REAL_DB = Path(__file__).resolve().parent.parent / "data" / "gallery.db"


@pytest.fixture(scope="module")
def db():
    from database import DatabaseManager
    if not REAL_DB.exists():
        pytest.skip(f"Real DB not found: {REAL_DB}")
    manager = DatabaseManager(db_path=REAL_DB, read_only=True)
    yield manager
    manager.sqlite.close()


@pytest.fixture(scope="module")
def http():
    import urllib.request
    return urllib.request


def _timed(label, fn, *args, **kwargs):
    t0 = time.time()
    result = fn(*args, **kwargs)
    elapsed = time.time() - t0
    budget = BUDGETS.get(label, 999)
    status = "OK" if elapsed <= budget else "SLOW"
    return elapsed, budget, status, result


class TestDatabasePerformance:
    """Direct DB method timing — measures SQLite query speed."""

    def test_get_status(self, db):
        elapsed, budget, status, _ = _timed("get_status", db.get_status)
        assert status == "OK", (
            f"\n  get_status() took {elapsed:.3f}s (budget {budget}s)"
            f"\n  HINT: remove expensive JOINs with catalog_files, use simple COUNT on photos table"
        )
        print(f"  [PERF] get_status: {elapsed:.3f}s (budget {budget}s) [{status}]")

    def test_search_60(self, db):
        elapsed, budget, status, (total, photos) = _timed(
            "search_60", db.search_photos, limit=60, sort="date_desc"
        )
        assert status == "OK", (
            f"\n  search_photos(limit=60) took {elapsed:.3f}s (budget {budget}s)"
            f"\n  HINT: check search_photos() SQL — avoid get_all_faces(), use targeted face query by content_hash"
        )
        assert len(photos) > 0, "search should return photos"
        print(f"  [PERF] search_60: {elapsed:.3f}s ({total} total, {len(photos)} returned) [{status}]")

    def test_search_60_with_face_enrichment(self, db):
        total, photos = db.search_photos(limit=60, sort="date_desc")
        hashes = [p.get("content_hash", "") for p in photos if p.get("content_hash")]

        elapsed, budget, status, _ = _timed(
            "search_60_faces",
            lambda: db.sqlite.execute(
                f"SELECT face_id, content_hash, persona_id FROM faces WHERE content_hash IN ({','.join('?' * len(hashes))})",
                hashes
            ).fetchall()
        )
        assert status == "OK", (
            f"\n  targeted face query for {len(hashes)} photos took {elapsed:.3f}s (budget {budget}s)"
            f"\n  HINT: ensure idx_faces_content_hash exists: CREATE INDEX idx_faces_content_hash ON faces(content_hash)"
        )
        print(f"  [PERF] targeted_faces({len(hashes)}): {elapsed:.3f}s [{status}]")

    def test_date_histogram(self, db):
        elapsed, budget, status, _ = _timed("dates_histogram", db.get_date_histogram)
        assert status == "OK", (
            f"\n  get_date_histogram() took {elapsed:.3f}s (budget {budget}s)"
            f"\n  HINT: add index on COALESCE(manual_date, date), filter deleted=0"
        )
        print(f"  [PERF] date_histogram: {elapsed:.3f}s [{status}]")

    def test_count_photos(self, db):
        elapsed, budget, status, _ = _timed("count_photos", db.count_photos)
        assert status == "OK", (
            f"\n  count_photos() took {elapsed:.3f}s (budget {budget}s)"
            f"\n  This should be instant — SQLite COUNT(*) on indexed table"
        )
        print(f"  [PERF] count_photos: {elapsed:.3f}s [{status}]")

    def test_get_all_faces_baseline(self, db):
        elapsed, budget, status, faces = _timed("get_all_faces", db.get_all_faces)
        assert status == "OK", (
            f"\n  get_all_faces() took {elapsed:.3f}s (budget {budget}s)"
            f"\n  WARNING: this loads ALL {len(faces)} faces into memory"
            f"\n  NEVER call this from API endpoints — use targeted query by content_hash instead"
        )
        print(f"  [PERF] get_all_faces: {elapsed:.3f}s ({len(faces)} rows) [{status}]")

    def test_get_all_personas_baseline(self, db):
        elapsed, budget, status, personas = _timed("get_all_personas", db.get_all_personas)
        assert status == "OK", (
            f"\n  get_all_personas() took {elapsed:.3f}s (budget {budget}s)"
            f"\n  WARNING: this loads ALL {len(personas)} personas into memory"
            f"\n  NEVER call this from per-request API endpoints"
        )
        print(f"  [PERF] get_all_personas: {elapsed:.3f}s ({len(personas)} rows) [{status}]")

    def test_targeted_vs_all_faces(self, db):
        total, photos = db.search_photos(limit=60, sort="date_desc")
        hashes = [p.get("content_hash", "") for p in photos if p.get("content_hash")]

        t0 = time.time()
        ph = ",".join("?" * len(hashes))
        targeted = db.sqlite.execute(
            f"SELECT face_id, content_hash, persona_id FROM faces WHERE content_hash IN ({ph})",
            hashes
        ).fetchall()
        targeted_t = time.time() - t0

        t0 = time.time()
        all_f = db.get_all_faces()
        all_t = time.time() - t0

        speedup = all_t / max(targeted_t, 0.001)
        assert targeted_t < 0.1, (
            f"\n  targeted_faces took {targeted_t:.3f}s — should be <0.1s"
            f"\n  Check idx_faces_content_hash"
        )
        assert speedup > 50, (
            f"\n  targeted_faces is only {speedup:.0f}x faster than get_all_faces()"
            f"\n  Expected 100x+ speedup for 60-photo request vs 188K faces"
            f"\n  targeted: {targeted_t:.3f}s ({len(targeted)} rows) vs all: {all_t:.3f}s ({len(all_f)} rows)"
        )
        print(f"  [PERF] targeted vs all: {targeted_t:.4f}s vs {all_t:.3f}s = {speedup:.0f}x speedup")


class TestAPIPerformance:
    """HTTP endpoint timing — measures full request-response cycle."""

    BASE = "http://localhost:8000"

    @pytest.fixture(autouse=True)
    def _check_server(self):
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.BASE}/health", timeout=3)
        except Exception:
            pytest.skip("uvicorn not running on :8000 — start with: systemctl start gailery")

    def _get(self, path, budget_key):
        import urllib.request
        url = f"{self.BASE}{path}"
        t0 = time.time()
        try:
            resp = urllib.request.urlopen(url, timeout=30)
            code = resp.getcode()
            body = resp.read()
        except Exception as e:
            elapsed = time.time() - t0
            raise AssertionError(f"Request to {url} failed after {elapsed:.1f}s: {e}")
        elapsed = time.time() - t0
        budget = BUDGETS[budget_key]
        assert code < 400, f"HTTP {code} for {url}"
        return elapsed, budget, len(body)

    def test_health(self):
        elapsed, budget, size = self._get("/health", "api_health")
        status = "OK" if elapsed <= budget else "SLOW"
        assert status == "OK", f"health took {elapsed:.3f}s (budget {budget}s)"
        print(f"  [PERF] /health: {elapsed:.3f}s [{status}]")

    def test_gallery_page(self):
        elapsed, budget, size = self._get("/gallery", "api_gallery_page")
        status = "OK" if elapsed <= budget else "SLOW"
        assert status == "OK", f"gallery page took {elapsed:.3f}s (budget {budget}s)"
        print(f"  [PERF] /gallery: {elapsed:.3f}s ({size//1024}KB) [{status}]")

    def test_api_status(self):
        elapsed, budget, size = self._get("/api/status", "api_status")
        status = "OK" if elapsed <= budget else "SLOW"
        assert status == "OK", (
            f"\n  /api/status took {elapsed:.3f}s (budget {budget}s)"
            f"\n  HINT: get_status() must run in executor, not block event loop"
            f"\n  Was 5s+ when blocking — caused 100% CPU and unresponsive server"
        )
        print(f"  [PERF] /api/status: {elapsed:.3f}s [{status}]")

    def test_api_status_cached(self):
        import urllib.request
        url = f"{self.BASE}/api/status"
        first_t0 = time.time()
        urllib.request.urlopen(url, timeout=15).read()
        first_t = time.time() - first_t0
        cached_t0 = time.time()
        urllib.request.urlopen(url, timeout=15).read()
        cached_t = time.time() - cached_t0
        assert cached_t < 0.5, (
            f"\n  Second /api/status took {cached_t:.3f}s — should be cached (<0.5s)"
            f"\n  First: {first_t:.3f}s, cached: {cached_t:.3f}s"
            f"\n  HINT: check _STATUS_TTL cache in main.py"
        )
        print(f"  [PERF] /api/status cached: {cached_t:.4f}s (first: {first_t:.3f}s)")

    def test_api_search_60(self):
        elapsed, budget, size = self._get("/api/photos/search?limit=60&sort=date_desc", "api_search_60")
        status = "OK" if elapsed <= budget else "SLOW"
        assert status == "OK", (
            f"\n  /api/photos/search?limit=60 took {elapsed:.3f}s (budget {budget}s)"
            f"\n  HINT: must use targeted face query by content_hash, NOT get_all_faces()"
            f"\n  get_all_faces() = 1.1s + get_all_personas() = 0.08s = 1.2s WASTE"
            f"\n  targeted SQL by content_hash for 60 photos = 0.001s"
        )
        print(f"  [PERF] /api/photos/search?limit=60: {elapsed:.3f}s ({size//1024}KB) [{status}]")

    def test_api_dates(self):
        elapsed, budget, size = self._get("/api/photos/dates", "api_dates")
        status = "OK" if elapsed <= budget else "SLOW"
        assert status == "OK", f"/api/photos/dates took {elapsed:.3f}s (budget {budget}s)"
        print(f"  [PERF] /api/photos/dates: {elapsed:.3f}s [{status}]")

    def test_api_config(self):
        elapsed, budget, size = self._get("/api/config", "api_config")
        status = "OK" if elapsed <= budget else "SLOW"
        assert status == "OK", f"/api/config took {elapsed:.3f}s (budget {budget}s)"
        print(f"  [PERF] /api/config: {elapsed:.3f}s [{status}]")

    def test_api_log(self):
        elapsed, budget, size = self._get("/api/log?lines=50", "api_log")
        status = "OK" if elapsed <= budget else "SLOW"
        assert status == "OK", (
            f"\n  /api/log took {elapsed:.3f}s (budget {budget}s)"
            f"\n  HINT: must run file reading in executor — 53MB log file blocks event loop"
        )
        print(f"  [PERF] /api/log?lines=50: {elapsed:.3f}s ({size//1024}KB) [{status}]")

    def test_api_status_no_event_loop_block(self):
        import urllib.request
        import concurrent.futures

        def fetch(path):
            t0 = time.time()
            resp = urllib.request.urlopen(f"{self.BASE}{path}", timeout=15)
            resp.read()
            return time.time() - t0

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            f_status = pool.submit(fetch, "/api/status")
            f_health = pool.submit(fetch, "/health")
            f_gallery = pool.submit(fetch, "/gallery")

            t_status = f_status.result()
            t_health = f_health.result()
            t_gallery = f_gallery.result()

        assert t_health < 1.0, (
            f"\n  /health took {t_health:.3f}s while /api/status was running"
            f"\n  This means /api/status is BLOCKING the event loop!"
            f"\n  HINT: run get_status() and log reading in run_in_executor()"
            f"\n  100% CPU / unresponsive server was caused by this exact bug"
        )
        assert t_gallery < 1.0, (
            f"\n  /gallery took {t_gallery:.3f}s while /api/status was running"
            f"\n  Event loop should NOT be blocked by /api/status"
        )
        print(f"  [PERF] concurrent: status={t_status:.3f}s health={t_health:.3f}s gallery={t_gallery:.3f}s")

    def test_api_concurrent_status_polling(self):
        import urllib.request
        import concurrent.futures
        url = f"{self.BASE}/api/status"
        N = 3

        def fetch_status():
            t0 = time.time()
            urllib.request.urlopen(url, timeout=15).read()
            return time.time() - t0

        with concurrent.futures.ThreadPoolExecutor(max_workers=N) as pool:
            futures = [pool.submit(fetch_status) for _ in range(N)]
            times = [f.result() for f in futures]

        total = sum(times)
        max_t = max(times)
        budget = BUDGETS["api_status_concurrent_3"]
        assert total <= budget, (
            f"\n  {N}x concurrent /api/status: total={total:.3f}s max={max_t:.3f}s (budget {budget}s)"
            f"\n  HINT: /api/status must not block event loop — use run_in_executor + caching"
            f"\n  Browser polls /api/status every 2-5s; blocking = 100% CPU death spiral"
        )
        print(f"  [PERF] {N}x concurrent status: total={total:.3f}s max={max_t:.3f}s [{('OK' if total<=budget else 'SLOW')}]")

    def test_api_concurrent_search(self):
        import urllib.request
        import concurrent.futures
        N = 3

        def fetch_search():
            t0 = time.time()
            urllib.request.urlopen(
                f"{self.BASE}/api/photos/search?limit=60&sort=date_desc", timeout=15
            ).read()
            return time.time() - t0

        with concurrent.futures.ThreadPoolExecutor(max_workers=N) as pool:
            futures = [pool.submit(fetch_search) for _ in range(N)]
            times = [f.result() for f in futures]

        total = sum(times)
        max_t = max(times)
        budget = BUDGETS["api_search_concurrent_3"]
        assert total <= budget, (
            f"\n  {N}x concurrent search: total={total:.3f}s max={max_t:.3f}s (budget {budget}s)"
            f"\n  HINT: face queries must be targeted by content_hash, not get_all_faces()"
        )
        print(f"  [PERF] {N}x concurrent search: total={total:.3f}s max={max_t:.3f}s [{('OK' if total<=budget else 'SLOW')}]")


class TestDatabaseIndexCoverage:
    """Verify critical indexes exist for performance-critical queries."""

    def test_faces_content_hash_index(self, db):
        indexes = db.sqlite.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='faces'"
        ).fetchall()
        names = [r[0] for r in indexes]
        assert "idx_faces_content_hash" in names, (
            f"\n  Missing idx_faces_content_hash on faces table!"
            f"\n  Without this, targeted face queries do full table scan (188K rows)"
            f"\n  Fix: CREATE INDEX idx_faces_content_hash ON faces(content_hash)"
        )

    def test_catalog_files_abs_path_index(self, db):
        indexes = db.sqlite.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='catalog_files'"
        ).fetchall()
        names = [r[0] for r in indexes]
        assert "idx_catalog_abs" in names, (
            f"\n  Missing idx_catalog_abs on catalog_files!"
            f"\n  photos.path → catalog_files.abs_path JOIN is used everywhere"
        )

    def test_catalog_files_content_hash_index(self, db):
        indexes = db.sqlite.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='catalog_files'"
        ).fetchall()
        names = [r[0] for r in indexes]
        assert "idx_catalog_hash" in names, (
            f"\n  Missing idx_catalog_hash on catalog_files!"
            f"\n  content_hash lookups are the primary join key"
        )

    def test_photos_root_id_index(self, db):
        indexes = db.sqlite.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='photos'"
        ).fetchall()
        names = [r[0] for r in indexes]
        assert "idx_photos_root_id" in names, (
            f"\n  Missing idx_photos_root_id on photos!"
            f"\n  get_status() filters by root_id — without index, full scan on 83K rows"
        )

    def test_photos_deleted_index(self, db):
        indexes = db.sqlite.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='photos'"
        ).fetchall()
        names = [r[0] for r in indexes]
        has_deleted_idx = any("deleted" in n.lower() for n in names)
        if not has_deleted_idx:
            idx_list = ", ".join(names)
            print(f"  [WARN] No index on photos.deleted — every query filters deleted=0. Current indexes: {idx_list}")

    def test_photos_effective_date_index(self, db):
        indexes = db.sqlite.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='photos'"
        ).fetchall()
        names = [r[0] for r in indexes]
        assert "idx_photos_effective_date" in names, (
            f"\n  Missing idx_photos_effective_date!"
            f"\n  Sorting by COALESCE(manual_date, date) without index = filesort on 83K rows"
        )

    def test_query_plan_faces_by_content_hash(self, db):
        plan_rows = db.sqlite.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM faces WHERE content_hash = 'test'"
        ).fetchall()
        plan_str = " ".join(str(list(r)) for r in plan_rows)
        assert "idx_faces_content_hash" in plan_str or "COVERING INDEX" in plan_str, (
            f"\n  faces WHERE content_hash=? does NOT use index!"
            f"\n  Plan: {plan_str}"
            f"\n  Fix: CREATE INDEX idx_faces_content_hash ON faces(content_hash)"
        )
        print(f"  [PERF] faces by content_hash: {plan_str}")

    def test_query_plan_status_photos_root(self, db):
        plan = db.sqlite.execute(
            "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM photos WHERE deleted = 0 AND root_id IN ('r1')"
        ).fetchall()
        plan_str = " | ".join(str(r) for r in plan)
        uses_idx = "idx_photos_root_id" in plan_str or "INDEX" in plan_str
        if not uses_idx:
            print(f"  [WARN] status COUNT by root_id uses no index: {plan_str}")


class TestAntipatternDetection:
    """Detect known performance antipatterns in API code."""

    def test_search_endpoint_no_get_all_faces(self):
        code = Path(__file__).parent.parent / "src" / "api" / "photos.py"
        content = code.read_text()
        assert "get_all_faces()" not in content.split("def search_photos")[1].split("def ")[0], (
            f"\n  /api/photos/search still calls get_all_faces()!"
            f"\n  get_all_faces() = 1.1s, targeted SQL by content_hash = 0.001s"
            f"\n  Fix: replace with SELECT ... FROM faces WHERE content_hash IN (?)"
        )

    def test_list_endpoint_no_get_all_faces(self):
        code = Path(__file__).parent.parent / "src" / "api" / "photos.py"
        content = code.read_text()
        list_func = content.split("def list_photos")
        if len(list_func) > 1:
            func_body = list_func[1].split("def ")[0]
            assert "get_all_faces()" not in func_body, (
                f"\n  /api/photos/list still calls get_all_faces()!"
                f"\n  Replace with targeted SQL by content_hash"
            )

    def test_semantic_search_no_get_all_faces(self):
        code = Path(__file__).parent.parent / "src" / "api" / "photos.py"
        content = code.read_text()
        sem_func = content.split("def semantic_search")
        if len(sem_func) > 1:
            func_body = sem_func[1].split("def ")[0]
            assert "get_all_faces()" not in func_body, (
                f"\n  /api/photos/semantic_search still calls get_all_faces()!"
                f"\n  Replace with targeted SQL by content_hash"
            )

    def test_status_endpoint_runs_in_executor(self):
        code = Path(__file__).parent.parent / "src" / "main.py"
        content = code.read_text()
        assert "run_in_executor" in content.split('async def get_status')[1].split("\n    @app")[0] or \
               "run_in_executor" in content.split('async def get_status')[1].split("def _compute_status")[0], (
            f"\n  /api/status does NOT run get_status() in executor!"
            f"\n  This blocks the event loop — caused 100% CPU / unresponsive server"
            f"\n  Fix: status = await loop.run_in_executor(None, _compute_status)"
        )

    def test_log_reading_in_executor(self):
        code = Path(__file__).parent.parent / "src" / "main.py"
        content = code.read_text()
        log_section = content.split("async def get_log")[1].split("\n@app")[0]
        assert "run_in_executor" in log_section, (
            f"\n  /api/log does NOT run file reading in executor!"
            f"\n  53MB log file read blocks event loop"
            f"\n  Fix: all_lines = await loop.run_in_executor(None, _read_tail)"
        )

    def test_no_db_get_status_in_main_thread(self):
        code = Path(__file__).parent.parent / "src" / "main.py"
        content = code.read_text()
        status_func = content.split('def get_status():')[1].split("def ")[0]
        direct = "db.get_status()" in status_func and "run_in_executor" not in status_func.split("db.get_status")[0]
        assert not direct, (
            f"\n  db.get_status() called directly in async handler!"
            f"\n  This is a BLOCKING call (~2s) that freezes the event loop"
        )

    def test_status_cache_ttl_not_zero(self):
        code = Path(__file__).parent.parent / "src" / "main.py"
        content = code.read_text()
        for line in content.split("\n"):
            if "_STATUS_TTL" in line and "=" in line and not line.strip().startswith("#"):
                val = line.split("=")[1].strip().rstrip(",")
                try:
                    ttl = int(val)
                    assert ttl >= 5, (
                        f"\n  _STATUS_TTL = {ttl}s — too low!"
                        f"\n  Browser polls every 2-5s; TTL<5 means almost every request hits DB"
                        f"\n  Recommended: 10s"
                    )
                except ValueError:
                    pass


class TestScaleBaseline:
    """Document current DB scale so performance budgets stay realistic."""

    def test_record_counts(self, db):
        photos = db.sqlite.execute("SELECT COUNT(*) FROM photos WHERE deleted=0").fetchone()[0]
        catalog = db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE is_canonical=1 AND deleted=0").fetchone()[0]
        faces = db.sqlite.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
        personas = db.sqlite.execute("SELECT COUNT(*) FROM personas").fetchone()[0]

        print(f"\n  [SCALE] photos={photos} catalog={catalog} faces={faces} personas={personas}")

        assert photos > 1000, "Performance tests need realistic data (1K+ photos)"
        assert faces > 10000, "Performance tests need realistic data (10K+ faces)"

        if faces > 500000:
            print(f"  [WARN] {faces} faces — budgets may need adjustment")
        if photos > 200000:
            print(f"  [WARN] {photos} photos — budgets may need adjustment")

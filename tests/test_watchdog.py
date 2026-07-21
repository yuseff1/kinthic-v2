import pytest
import pytest_asyncio
import tempfile
import os
from silex_engine.storage.database import Database
from scripts.watchdog import probe_db_health, trigger_recovery_alert, WatchdogSupervisor


@pytest_asyncio.fixture
async def temp_db():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        db_path = tmp.name
    db = Database(db_path)
    await db.connect()
    yield db, db_path
    await db.close()
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_watchdog_probe_db_health(temp_db):
    db, db_path = temp_db
    ok = await probe_db_health(db=db)
    assert ok is True

    ok_by_path = await probe_db_health(db_path=db_path)
    assert ok_by_path is True


@pytest.mark.asyncio
async def test_watchdog_trigger_recovery_alert(temp_db):
    db, db_path = temp_db
    success = await trigger_recovery_alert("Gateway un-responsive", db=db)
    assert success is True

    rows = await db.fetch_all("SELECT * FROM notifications WHERE type = 'watchdog'")
    assert len(rows) == 1
    assert "Gateway un-responsive" in rows[0]["message"]
    assert rows[0]["delivered"] == 0


@pytest.mark.asyncio
async def test_watchdog_supervisor_failure_threshold(temp_db):
    _, db_path = temp_db
    supervisor = WatchdogSupervisor(max_failures=2, db_path=db_path)

    # First check (Gateway un-responsive because server isn't running on port 8000 in unit tests)
    res = await supervisor.run_single_check()
    assert res["healthy"] is False
    assert supervisor.consecutive_failures == 1

    # Second check (reaches max_failures=2, triggers alert and resets counter)
    res2 = await supervisor.run_single_check()
    assert res2["healthy"] is False
    assert supervisor.consecutive_failures == 0

import pytest
import pytest_asyncio
import tempfile
import os
from silex_engine.storage.database import Database
from silex_core.services.briefing import BriefingService


@pytest_asyncio.fixture
async def temp_db():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        db_path = tmp.name
    db = Database(db_path)
    await db.connect()
    yield db
    await db.close()
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_briefing_service_generate_and_queue(temp_db):
    service = BriefingService(db=temp_db)

    # 1. Test generate_briefing on fresh database
    report = await service.generate_briefing()
    assert "Kinthic Daily Briefing" in report
    assert "Active Memories:" in report
    assert "Knowledge Graph:" in report
    assert "Active Goals & Autonomous Jobs:" in report

    # 2. Add synthetic goal and memory to DB
    await temp_db.execute(
        "INSERT INTO goals (id, description, status, priority, created_at, updated_at) VALUES ('g1', 'Grow X audience to 10k', 'active', 'high', '2026-07-21', '2026-07-21')"
    )

    report_with_data = await service.generate_briefing()
    assert "Grow X audience to 10k" in report_with_data

    # 3. Test queue_briefing_notification
    queued_report = await service.queue_briefing_notification()
    assert "Kinthic Daily Briefing" in queued_report

    rows = await temp_db.fetch_all("SELECT * FROM notifications WHERE type = 'briefing'")
    assert len(rows) == 1
    assert rows[0]["delivered"] == 0
    assert "Grow X audience to 10k" in rows[0]["message"]

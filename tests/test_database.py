import pytest
from sqlalchemy import func, select

from mlwrap.db.models import InferenceLog, ModelEvent
from mlwrap.db.session import Database


@pytest.fixture
def sqlite_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'mlwrap.db'}"


async def test_inferences_are_persisted(make_client, sqlite_url) -> None:
    async with make_client(
        database_url=sqlite_url, db_auto_create=True, persist_payloads=True
    ) as client:
        await client.post("/api/v1/models/sum/predict", json={"values": [1, 2]})
        await client.post("/api/v1/models/boom/predict", json={})

        database: Database = client.app.state.database
        async with database.session() as session:
            rows = (await session.execute(select(InferenceLog))).scalars().all()
            events = (await session.execute(select(ModelEvent))).scalars().all()

    by_model = {row.model_name: row for row in rows}
    assert by_model["sum"].status == "ok"
    assert by_model["sum"].latency_ms >= 0
    assert by_model["sum"].payload == {"values": [1.0, 2.0]}
    assert by_model["sum"].result == {"total": 3.0, "count": 2}
    assert by_model["sum"].principal == "anonymous"
    assert by_model["boom"].status == "error"
    assert "prediction_failed" in by_model["boom"].error

    assert {(event.model_name, event.event) for event in events} >= {("sum", "load")}


async def test_history_appears_in_model_metrics(make_client, sqlite_url) -> None:
    async with make_client(database_url=sqlite_url, db_auto_create=True) as client:
        for _ in range(3):
            await client.post("/api/v1/models/sum/predict", json={"values": [1]})

        response = await client.get("/api/v1/models/sum/metrics")
        history = response.json()["history"]

    assert history["total"] == 3
    assert history["errors"] == 0
    assert history["error_rate"] == 0.0
    assert history["window"] == 3
    assert history["latency_ms"]["p95"] is not None
    assert history["last_at"] is not None


async def test_payloads_are_not_stored_by_default(make_client, sqlite_url) -> None:
    async with make_client(database_url=sqlite_url, db_auto_create=True) as client:
        await client.post("/api/v1/models/sum/predict", json={"values": [1]})

        database: Database = client.app.state.database
        async with database.session() as session:
            row = (await session.execute(select(InferenceLog))).scalars().one()
            assert row.payload is None
            assert row.result is None


async def test_persistence_can_be_disabled(make_client, sqlite_url) -> None:
    async with make_client(
        database_url=sqlite_url, db_auto_create=True, persist_inferences=False
    ) as client:
        await client.post("/api/v1/models/sum/predict", json={"values": [1]})

        database: Database = client.app.state.database
        async with database.session() as session:
            total = (await session.execute(select(func.count(InferenceLog.id)))).scalar()
            assert total == 0


async def test_ready_check_reports_database(make_client, sqlite_url) -> None:
    async with make_client(database_url=sqlite_url, db_auto_create=True) as client:
        checks = (await client.get("/health/ready")).json()["checks"]
        assert checks["database"] == "ok"

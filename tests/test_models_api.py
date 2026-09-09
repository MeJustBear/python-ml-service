async def test_list_models(client) -> None:
    response = await client.get("/api/v1/models")
    assert response.status_code == 200
    by_name = {item["name"]: item for item in response.json()}
    assert set(by_name) == {"sum", "free", "broken", "boom", "slow"}
    assert by_name["sum"]["state"] == "unloaded"
    assert by_name["sum"]["requires_load"] is True
    assert by_name["sum"]["has_metrics"] is True
    assert by_name["free"]["requires_load"] is False


async def test_load_and_unload(client) -> None:
    loaded = await client.post("/api/v1/models/sum/load")
    assert loaded.status_code == 200
    assert loaded.json()["state"] == "ready"
    assert loaded.json()["loaded_at"] is not None

    reloaded = await client.post("/api/v1/models/sum/load", params={"force": True})
    assert reloaded.json()["state"] == "ready"

    unloaded = await client.post("/api/v1/models/sum/unload")
    assert unloaded.json()["state"] == "unloaded"
    assert unloaded.json()["loaded_at"] is None


async def test_predict_autoloads_model(client) -> None:
    response = await client.post("/api/v1/models/sum/predict", json={"values": [1, 2, 3.5]})
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "sum"
    assert body["version"] == "2.0.0"
    assert body["result"] == {"total": 6.5, "count": 3}
    assert body["latency_ms"] >= 0
    assert body["request_id"] == response.headers["X-Request-Id"]

    assert (await client.get("/api/v1/models/sum")).json()["state"] == "ready"


async def test_predict_without_autoload_requires_explicit_load(make_client) -> None:
    async with make_client(auto_load=False) as client:
        response = await client.post("/api/v1/models/sum/predict", json={"values": [1]})
        assert response.status_code == 409
        assert response.json()["error"] == "model_not_loaded"

        await client.post("/api/v1/models/sum/load")
        assert (
            await client.post("/api/v1/models/sum/predict", json={"values": [1]})
        ).status_code == 200


async def test_model_config_reaches_loader(make_client) -> None:
    async with make_client(models_config={"sum": {"scale": 10}}) as client:
        response = await client.post("/api/v1/models/sum/predict", json={"values": [1, 2]})
        assert response.json()["result"]["total"] == 30.0


async def test_batch_predict(client) -> None:
    response = await client.post(
        "/api/v1/models/sum/predict/batch",
        json=[{"values": [1, 1]}, {"values": [2, 2]}],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert [item["total"] for item in body["results"]] == [2.0, 4.0]


async def test_invalid_payload_returns_422(client) -> None:
    response = await client.post("/api/v1/models/sum/predict", json={"values": "nope"})
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_payload"
    assert response.json()["details"]["errors"]


async def test_free_form_model_accepts_any_json(client) -> None:
    response = await client.post("/api/v1/models/free/predict", json={"whatever": [1, 2]})
    assert response.status_code == 200
    assert response.json()["result"] == {"echo": {"whatever": [1, 2]}}


async def test_load_failure_is_reported(client) -> None:
    response = await client.post("/api/v1/models/broken/load")
    assert response.status_code == 503
    assert response.json()["error"] == "model_load_failed"

    info = (await client.get("/api/v1/models/broken")).json()
    assert info["state"] == "failed"
    assert "артефакт не найден" in info["error"]

    ready = await client.get("/health/ready")
    assert ready.json()["status"] == "degraded"
    assert "broken" in ready.json()["checks"]["models"]


async def test_prediction_error_is_reported(client) -> None:
    response = await client.post("/api/v1/models/boom/predict", json={})
    assert response.status_code == 500
    assert response.json()["error"] == "prediction_failed"

    info = (await client.get("/api/v1/models/boom")).json()
    assert info["error_count"] == 1


async def test_prediction_timeout(make_client) -> None:
    async with make_client(predict_timeout_seconds=0.05) as client:
        response = await client.post("/api/v1/models/slow/predict", json={})
        assert response.status_code == 504
        assert response.json()["error"] == "prediction_timeout"


async def test_unknown_model_returns_404(client) -> None:
    for method, url in [
        ("GET", "/api/v1/models/ghost"),
        ("POST", "/api/v1/models/ghost/load"),
        ("POST", "/api/v1/models/ghost/predict"),
        ("GET", "/api/v1/models/ghost/schema"),
    ]:
        response = await client.request(method, url, json={})
        assert response.status_code == 404, url
        assert response.json()["error"] == "model_not_found"


async def test_model_schema_endpoint(client) -> None:
    response = await client.get("/api/v1/models/sum/schema")
    assert response.status_code == 200
    body = response.json()
    assert body["input_schema"]["properties"]["values"]["type"] == "array"
    assert body["output_schema"]["properties"]["total"]["type"] == "number"


async def test_model_metrics_endpoint(client) -> None:
    await client.post("/api/v1/models/sum/predict", json={"values": [1]})
    response = await client.get("/api/v1/models/sum/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "ready"
    assert body["runtime"]["predict_count"] == 1
    assert body["custom"] == {"calls": 1.0, "scale": 1.0}
    assert body["history"] is None


async def test_service_info_and_health(client) -> None:
    info = (await client.get("/")).json()
    assert info["auth_mode"] == "none"
    assert "sum" in info["models"]

    assert (await client.get("/health/live")).json()["status"] == "ok"
    ready = (await client.get("/health/ready")).json()
    assert ready["checks"]["database"] == "disabled"

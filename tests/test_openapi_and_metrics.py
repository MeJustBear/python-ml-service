async def test_typed_routes_are_generated_per_model(client) -> None:
    paths = client.app.openapi()["paths"]

    assert "/api/v1/models/sum/predict" in paths
    assert "/api/v1/models/sum/predict/batch" in paths
    assert "/api/v1/models/{model_name}/predict" in paths

    request_body = paths["/api/v1/models/sum/predict"]["post"]["requestBody"]
    schema_ref = request_body["content"]["application/json"]["schema"]["$ref"]
    assert schema_ref.endswith("/SumRequest")

    response_ref = paths["/api/v1/models/sum/predict"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    assert "SumResponse" in response_ref

    batch_body = paths["/api/v1/models/sum/predict/batch"]["post"]["requestBody"]
    assert batch_body["content"]["application/json"]["schema"]["type"] == "array"


async def test_free_form_model_has_object_body(client) -> None:
    paths = client.app.openapi()["paths"]
    body = paths["/api/v1/models/free/predict"]["post"]["requestBody"]
    assert body["content"]["application/json"]["schema"]["type"] == "object"


async def test_prometheus_endpoint_exposes_model_metrics(client) -> None:
    await client.post("/api/v1/models/sum/predict", json={"values": [1, 2]})
    await client.post("/api/v1/models/boom/predict", json={})

    response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    text = response.text

    assert 'mlwrap_predict_total{model="sum",status="ok"}' in text
    assert 'mlwrap_predict_total{model="boom",status="error"}' in text
    assert 'mlwrap_model_loaded{model="sum"} 1.0' in text
    assert 'mlwrap_model_custom_metric{metric="calls",model="sum"}' in text
    assert "mlwrap_predict_latency_seconds_bucket" in text
    assert "mlwrap_http_requests_total" in text
    assert "mlwrap_app_info" in text


async def test_metrics_can_be_protected(make_client) -> None:
    async with make_client(
        metrics_protected=True, auth_mode="basic", auth_users={"u": "p"}
    ) as client:
        assert (await client.get("/metrics")).status_code == 401
        assert (await client.get("/metrics", auth=("u", "p"))).status_code == 200


async def test_metrics_can_be_disabled(make_client) -> None:
    async with make_client(metrics_enabled=False) as client:
        assert (await client.get("/metrics")).status_code == 404
        assert (await client.get("/")).json()["metrics_url"] is None

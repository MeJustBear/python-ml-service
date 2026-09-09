import base64

import pytest

from mlwrap.config import AuthMode, Settings
from mlwrap.errors import ConfigurationError
from mlwrap.security import build_auth_provider, hash_password
from mlwrap.security.users import UserStore

USERS = {"alice": "wonderland"}
SECRET = "test-secret-not-shorter-than-32-bytes"


async def test_none_mode_allows_anonymous(client) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json() == {"subject": "anonymous", "auth_mode": "none", "claims": {}}


async def test_basic_mode_requires_credentials(make_client) -> None:
    async with make_client(auth_mode="basic", auth_users=USERS) as client:
        assert (await client.get("/api/v1/models")).status_code == 401

        token = base64.b64encode(b"alice:wonderland").decode()
        response = await client.get("/api/v1/models", headers={"Authorization": f"Basic {token}"})
        assert response.status_code == 200

        bad = base64.b64encode(b"alice:wrong").decode()
        assert (
            await client.get("/api/v1/models", headers={"Authorization": f"Basic {bad}"})
        ).status_code == 401


async def test_basic_mode_accepts_bcrypt_hash(make_client) -> None:
    users = {"bob": hash_password("s3cret")}
    async with make_client(auth_mode="basic", auth_users=users) as client:
        token = base64.b64encode(b"bob:s3cret").decode()
        response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Basic {token}"})
        assert response.status_code == 200
        assert response.json()["subject"] == "bob"


async def test_jwt_mode_full_flow(make_client) -> None:
    async with make_client(auth_mode="jwt", auth_users=USERS, jwt_secret=SECRET) as client:
        assert (await client.get("/api/v1/models")).status_code == 401

        rejected = await client.post(
            "/api/v1/auth/token", data={"username": "alice", "password": "nope"}
        )
        assert rejected.status_code == 401

        issued = await client.post(
            "/api/v1/auth/token", data={"username": "alice", "password": "wonderland"}
        )
        assert issued.status_code == 200
        body = issued.json()
        assert body["token_type"] == "bearer" and body["expires_in"] > 0

        headers = {"Authorization": f"Bearer {body['access_token']}"}
        me = await client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["subject"] == "alice"
        assert me.json()["auth_mode"] == "jwt"

        assert (
            await client.get("/api/v1/models", headers={"Authorization": "Bearer garbage"})
        ).status_code == 401


async def test_jwt_predict_is_protected(make_client) -> None:
    async with make_client(auth_mode="jwt", auth_users=USERS, jwt_secret=SECRET) as client:
        anonymous = await client.post("/api/v1/models/sum/predict", json={"values": [1, 2]})
        assert anonymous.status_code == 401

        issued = await client.post(
            "/api/v1/auth/token", data={"username": "alice", "password": "wonderland"}
        )
        headers = {"Authorization": f"Bearer {issued.json()['access_token']}"}
        allowed = await client.post(
            "/api/v1/models/sum/predict", json={"values": [1, 2]}, headers=headers
        )
        assert allowed.status_code == 200
        assert allowed.json()["result"] == {"total": 3.0, "count": 2}


def test_token_endpoint_absent_without_jwt(client) -> None:
    paths = client.app.openapi()["paths"]
    assert "/api/v1/auth/token" not in paths


async def test_jwt_adds_token_endpoint(make_client) -> None:
    async with make_client(auth_mode="jwt", auth_users=USERS, jwt_secret=SECRET) as client:
        assert "/api/v1/auth/token" in client.app.openapi()["paths"]


def test_settings_reject_incomplete_auth_config() -> None:
    with pytest.raises(ValueError, match="MLWRAP_AUTH_USERS"):
        Settings(_env_file=None, auth_mode="basic", auth_users={})

    with pytest.raises(ValueError, match="MLWRAP_JWT_SECRET"):
        Settings(_env_file=None, auth_mode="jwt", auth_users=USERS, jwt_secret=None)


def test_provider_factory_requires_users() -> None:
    settings = Settings(_env_file=None, auth_mode="none")
    object.__setattr__(settings, "auth_mode", AuthMode.BASIC)
    with pytest.raises(ConfigurationError):
        build_auth_provider(settings)


def test_user_store_rejects_unknown_user() -> None:
    store = UserStore(USERS)
    assert store.verify("alice", "wonderland") is True
    assert store.verify("alice", "other") is False
    assert store.verify("ghost", "any") is False
    assert len(store) == 1

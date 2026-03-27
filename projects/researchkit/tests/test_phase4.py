"""Phase 4 测试：JWT 认证 + 用户系统"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ─── 测试用 SQLite 数据库（StaticPool 确保单一内存连接） ──────────────────────

@pytest.fixture
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 所有连接复用同一内存数据库连接
    )
    from web.backend.database import Base
    from web.backend import models  # noqa: F401 — 触发模型注册
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    store_file = tmp_path / "tasks.json"
    store_file.write_text("{}", encoding="utf-8")
    import web.backend.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_STORE_FILE", store_file)
    return store_file


@pytest_asyncio.fixture
async def client(tmp_store, test_engine, monkeypatch):
    from web.backend.main import app
    from web.backend import database as db_mod

    TestSessionLocal = sessionmaker(bind=test_engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_mod.get_db] = override_get_db

    from web.backend.main import store
    store.__init__(tmp_store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────

async def register_and_login(client, email="test@example.com", username="testuser", password="password123"):
    await client.post("/api/auth/register", json={
        "email": email, "username": username, "password": password
    })
    form_data = f"username={email}&password={password}"
    resp = await client.post("/api/auth/token", content=form_data,
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
    return resp.json()


# ─── 注册测试 ─────────────────────────────────────────────────────────────────

async def test_register_success(client):
    resp = await client.post("/api/auth/register", json={
        "email": "user@example.com",
        "username": "user1",
        "password": "securepass123"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "user@example.com"
    assert data["username"] == "user1"
    assert "hashed_password" not in data
    assert data["is_active"] is True


async def test_register_duplicate_email(client):
    body = {"email": "dup@example.com", "username": "user1", "password": "password123"}
    await client.post("/api/auth/register", json=body)
    body2 = {"email": "dup@example.com", "username": "user2", "password": "password456"}
    resp = await client.post("/api/auth/register", json=body2)
    assert resp.status_code == 409
    assert "邮箱" in resp.json()["detail"]


async def test_register_duplicate_username(client):
    await client.post("/api/auth/register", json={
        "email": "a@example.com", "username": "sameuser", "password": "password123"
    })
    resp = await client.post("/api/auth/register", json={
        "email": "b@example.com", "username": "sameuser", "password": "password123"
    })
    assert resp.status_code == 409
    assert "用户名" in resp.json()["detail"]


async def test_register_short_password(client):
    resp = await client.post("/api/auth/register", json={
        "email": "short@example.com", "username": "shortpwd", "password": "1234567"
    })
    assert resp.status_code == 422


# ─── 登录测试 ─────────────────────────────────────────────────────────────────

async def test_login_success(client):
    tokens = await register_and_login(client)
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"


async def test_login_wrong_password(client):
    await client.post("/api/auth/register", json={
        "email": "wp@example.com", "username": "wpuser", "password": "correctpass"
    })
    form = "username=wp@example.com&password=wrongpass"
    resp = await client.post("/api/auth/token", content=form,
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert resp.status_code == 401


async def test_login_with_username(client):
    """支持用用户名登录"""
    await client.post("/api/auth/register", json={
        "email": "un@example.com", "username": "loginuser", "password": "pass12345"
    })
    form = "username=loginuser&password=pass12345"
    resp = await client.post("/api/auth/token", content=form,
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert resp.status_code == 200


# ─── /me 测试 ─────────────────────────────────────────────────────────────────

async def test_me_authenticated(client):
    tokens = await register_and_login(client)
    resp = await client.get("/api/auth/me",
                            headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@example.com"


async def test_me_unauthenticated(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


# ─── Token 刷新测试 ───────────────────────────────────────────────────────────

async def test_refresh_token(client):
    tokens = await register_and_login(client)
    resp = await client.post("/api/auth/refresh",
                             json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert "access_token" in new_tokens
    assert new_tokens["token_type"] == "bearer"
    # Token 必须是有效的 JWT（3段 base64）
    parts = new_tokens["access_token"].split(".")
    assert len(parts) == 3


async def test_refresh_invalid_token(client):
    resp = await client.post("/api/auth/refresh", json={"refresh_token": "invalid.token.here"})
    assert resp.status_code == 401


# ─── 数据隔离测试 ─────────────────────────────────────────────────────────────

async def test_task_data_isolation(client):
    """不同用户只能看到自己的任务"""
    # 用户 A 创建任务
    tokens_a = await register_and_login(client, "a@example.com", "usera", "passwordA123")
    headers_a = {"Authorization": f"Bearer {tokens_a['access_token']}"}
    await client.post("/api/tasks", json={"name": "A的任务", "topic": "A主题"}, headers=headers_a)

    # 用户 B 创建任务
    tokens_b = await register_and_login(client, "b@example.com", "userb", "passwordB123")
    headers_b = {"Authorization": f"Bearer {tokens_b['access_token']}"}
    await client.post("/api/tasks", json={"name": "B的任务", "topic": "B主题"}, headers=headers_b)

    # A 只看到自己的任务
    resp_a = await client.get("/api/tasks", headers=headers_a)
    tasks_a = resp_a.json()
    assert all(t["name"] == "A的任务" for t in tasks_a)

    # B 只看到自己的任务
    resp_b = await client.get("/api/tasks", headers=headers_b)
    tasks_b = resp_b.json()
    assert all(t["name"] == "B的任务" for t in tasks_b)


# ─── Auth 工具函数单元测试 ────────────────────────────────────────────────────

class TestAuthUtils:
    def test_hash_and_verify_password(self):
        from web.backend.auth import hash_password, verify_password
        hashed = hash_password("mypassword123")
        assert verify_password("mypassword123", hashed)
        assert not verify_password("wrongpassword", hashed)

    def test_create_and_decode_access_token(self):
        from web.backend.auth import create_access_token, decode_token
        token = create_access_token({"sub": "42"})
        payload = decode_token(token)
        assert payload["sub"] == "42"
        assert payload["type"] == "access"

    def test_create_and_decode_refresh_token(self):
        from web.backend.auth import create_refresh_token, decode_token
        token = create_refresh_token({"sub": "7"})
        payload = decode_token(token)
        assert payload["sub"] == "7"
        assert payload["type"] == "refresh"

    def test_invalid_token_raises(self):
        from web.backend.auth import decode_token
        from jose import JWTError
        with pytest.raises(JWTError):
            decode_token("totally.invalid.token")

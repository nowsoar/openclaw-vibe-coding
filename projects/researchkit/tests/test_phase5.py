"""Phase 5 测试：定时任务 / 通知推送 / 插件生态"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ─── 调度器单元测试 ───────────────────────────────────────────────────────────

@pytest.fixture
def sched(tmp_path, monkeypatch):
    """隔离的 ResearchScheduler 实例，使用临时 schedules.json。"""
    import web.backend.scheduler as sched_mod
    monkeypatch.setattr(sched_mod, "_SCHEDULE_FILE", tmp_path / "schedules.json")
    from web.backend.scheduler import ResearchScheduler
    s = ResearchScheduler()
    s.start()
    yield s
    s.shutdown(wait=False)


def test_scheduler_starts(sched):
    assert sched._scheduler.running


def test_add_and_list_task(sched):
    result = sched.add_task(
        task_id="t1",
        task_config={"name": "测试", "topic": "AI"},
        cron_expr="0 8 * * *",
    )
    assert result["task_id"] == "t1"
    assert result["cron_expr"] == "0 8 * * *"
    assert result["next_run"] is not None

    tasks = sched.list_tasks()
    assert any(t["task_id"] == "t1" for t in tasks)


def test_add_task_persists_to_file(sched, tmp_path):
    sched.add_task("persist_test", {"topic": "X"}, "0 0 * * *")
    schedule_file = tmp_path / "schedules.json"
    assert schedule_file.exists()
    data = json.loads(schedule_file.read_text(encoding="utf-8"))
    assert "persist_test" in data


def test_remove_task(sched):
    sched.add_task("to_remove", {"topic": "Y"}, "30 9 * * 1")
    assert sched.get_task("to_remove") is not None
    removed = sched.remove_task("to_remove")
    assert removed is True
    assert sched.get_task("to_remove") is None


def test_remove_nonexistent_task(sched):
    result = sched.remove_task("does_not_exist")
    assert result is False


def test_invalid_cron_raises(sched):
    with pytest.raises(ValueError, match="cron"):
        sched.add_task("bad_cron", {}, "0 8 * *")  # 只有4个字段


def test_trigger_now_unknown_task(sched):
    with pytest.raises(ValueError, match="未找到"):
        sched.trigger_now("ghost_task")


def test_trigger_now_calls_callback(sched):
    called: list = []

    def fake_run(task_id, task_config, incremental):
        called.append((task_id, incremental))
        return "# report"

    sched._run_callback = fake_run
    sched.add_task("cb_task", {"topic": "Z"}, "0 0 1 1 *")
    sched.trigger_now("cb_task")
    assert len(called) == 1
    assert called[0][0] == "cb_task"


def test_pause_and_resume(sched):
    sched.add_task("pausable", {"topic": "T"}, "0 12 * * *")
    sched.pause_task("pausable")
    sched.resume_task("pausable")


def test_restore_schedules(tmp_path, monkeypatch):
    """进程重启后恢复定时任务。"""
    import web.backend.scheduler as sched_mod
    monkeypatch.setattr(sched_mod, "_SCHEDULE_FILE", tmp_path / "schedules.json")
    from web.backend.scheduler import ResearchScheduler

    s1 = ResearchScheduler()
    s1.start()
    s1.add_task("restore_task", {"topic": "R"}, "0 7 * * *")
    s1.shutdown(wait=False)

    s2 = ResearchScheduler()
    s2.start()
    try:
        tasks = s2.list_tasks()
        assert any(t["task_id"] == "restore_task" for t in tasks)
    finally:
        s2.shutdown(wait=False)


# ─── 通知服务测试 ─────────────────────────────────────────────────────────────

def test_notification_empty_config():
    from web.backend.notifications import NotificationService
    svc = NotificationService({})
    svc.send("标题", "正文")  # 不应抛出


def test_notification_feishu_webhook(monkeypatch):
    from web.backend.notifications import NotificationService

    posted = {}

    def fake_urlopen(req, timeout=None):
        posted["url"] = req.full_url
        posted["data"] = json.loads(req.data)
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.status = 200
        return resp

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    svc = NotificationService({"feishu_webhook": "https://example.com/hook"})
    svc.send("测试通知", "内容", "# 报告")
    assert posted["url"] == "https://example.com/hook"
    assert posted["data"]["msg_type"] == "interactive"


def test_notification_webhook(monkeypatch):
    from web.backend.notifications import NotificationService

    posted = {}

    def fake_urlopen(req, timeout=None):
        posted["payload"] = json.loads(req.data)
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.status = 200
        return resp

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    svc = NotificationService({"webhook": "https://example.com/notify"})
    svc.send("标题2", "正文2")
    assert posted["payload"]["title"] == "标题2"


def test_notification_failure_does_not_raise(monkeypatch):
    """单个渠道失败不应影响其他渠道或抛出异常。"""
    from web.backend.notifications import NotificationService

    def broken_urlopen(req, timeout=None):
        raise ConnectionError("网络不通")

    monkeypatch.setattr("urllib.request.urlopen", broken_urlopen)
    svc = NotificationService({
        "feishu_webhook": "https://broken.example.com/hook",
        "webhook": "https://broken2.example.com/notify",
    })
    svc.send("fail title", "fail body")  # 不应抛出


# ─── 插件注册表测试 ───────────────────────────────────────────────────────────

def test_builtin_sources_registered():
    from researchkit.plugins import PluginType, list_plugins
    sources = list_plugins(PluginType.SOURCE)
    assert "wechat" in sources
    assert "rss" in sources
    assert "web" in sources


def test_builtin_processors_registered():
    from researchkit.plugins import PluginType, list_plugins
    procs = list_plugins(PluginType.PROCESSOR)
    assert "keyword_filter" in procs
    assert "deduplicator" in procs
    assert "ai_summarize" in procs


def test_builtin_outputs_registered():
    from researchkit.plugins import PluginType, list_plugins
    outputs = list_plugins(PluginType.OUTPUT)
    assert "markdown" in outputs


def test_register_plugin_decorator():
    from researchkit.plugins import PluginType, register_plugin, get_plugin

    @register_plugin(PluginType.SOURCE, "test_custom_source_xyz")
    class DummySource:
        pass

    cls = get_plugin(PluginType.SOURCE, "test_custom_source_xyz")
    assert cls is DummySource


def test_get_unknown_plugin_returns_none():
    from researchkit.plugins import PluginType, get_plugin
    assert get_plugin(PluginType.SOURCE, "definitely_not_exist_xyz") is None


# ─── API 定时任务路由测试 ─────────────────────────────────────────────────────

@pytest.fixture
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from web.backend.database import Base
    from web.backend import models  # noqa
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


@pytest.fixture
def mock_scheduler(tmp_path, monkeypatch):
    """替换 main.py 中的 _scheduler 为临时调度器实例。"""
    import web.backend.scheduler as sched_mod
    monkeypatch.setattr(sched_mod, "_SCHEDULE_FILE", tmp_path / "schedules.json")
    from web.backend.scheduler import ResearchScheduler
    s = ResearchScheduler()
    s.start()
    import web.backend.main as main_mod
    monkeypatch.setattr(main_mod, "_scheduler", s)
    yield s
    s.shutdown(wait=False)


@pytest_asyncio.fixture
async def client(tmp_store, test_engine, mock_scheduler, monkeypatch):
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_schedules_empty(client):
    resp = await client.get("/api/schedules")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_and_list_schedule(client):
    body = {
        "task_id": "api_task",
        "task_config": {"name": "API测试", "topic": "测试"},
        "cron_expr": "0 9 * * *",
        "incremental": False,
    }
    resp = await client.post("/api/schedules", json=body)
    assert resp.status_code == 201
    data = resp.json()
    assert data["task_id"] == "api_task"
    assert data["cron_expr"] == "0 9 * * *"

    list_resp = await client.get("/api/schedules")
    assert any(t["task_id"] == "api_task" for t in list_resp.json())


@pytest.mark.asyncio
async def test_create_schedule_invalid_cron(client):
    body = {
        "task_id": "bad_cron",
        "task_config": {},
        "cron_expr": "* * * *",  # 4字段，无效
    }
    resp = await client.post("/api/schedules", json=body)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_schedule(client):
    body = {
        "task_id": "get_me",
        "task_config": {"topic": "X"},
        "cron_expr": "0 10 * * *",
    }
    await client.post("/api/schedules", json=body)
    resp = await client.get("/api/schedules/get_me")
    assert resp.status_code == 200
    assert resp.json()["task_id"] == "get_me"


@pytest.mark.asyncio
async def test_get_schedule_not_found(client):
    resp = await client.get("/api/schedules/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_schedule(client):
    body = {"task_id": "del_me", "task_config": {}, "cron_expr": "0 11 * * *"}
    await client.post("/api/schedules", json=body)
    resp = await client.delete("/api/schedules/del_me")
    assert resp.status_code == 204
    get_resp = await client.get("/api/schedules/del_me")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_list_plugins_endpoint(client):
    resp = await client.get("/api/plugins")
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data
    assert "processors" in data
    assert "outputs" in data
    assert "wechat" in data["sources"]
    assert "markdown" in data["outputs"]

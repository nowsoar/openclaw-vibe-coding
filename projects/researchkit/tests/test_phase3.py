"""Phase 3 测试：FastAPI 后端 API"""
import json
import pytest
import pytest_asyncio
from pathlib import Path
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    """使用临时文件作为存储"""
    store_file = tmp_path / "tasks.json"
    store_file.write_text("{}", encoding="utf-8")
    import web.backend.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_STORE_FILE", store_file)
    return store_file


@pytest_asyncio.fixture
async def client(tmp_store):
    from web.backend.main import app, store
    store.__init__(tmp_store)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_tasks_empty(client):
    resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_task(client):
    body = {
        "name": "测试调研",
        "topic": "AI工具",
        "query": "研究AI工具市场",
        "keywords": ["AI", "GPT"],
        "time_range_days": 30,
        "sources_config": {"rss": {"enabled": True}},
        "pipeline_config": [{"step": "keyword_filter"}],
        "output_config": {"template": "trend_report", "format": "markdown"}
    }
    resp = await client.post("/api/tasks", json=body)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "测试调研"
    assert data["topic"] == "AI工具"
    assert data["status"] == "pending"
    assert "id" in data
    assert data["article_count"] == 0


@pytest.mark.asyncio
async def test_get_task(client):
    # 先创建
    create_resp = await client.post("/api/tasks", json={
        "name": "测试", "topic": "测试主题"
    })
    task_id = create_resp.json()["id"]

    # 再获取
    resp = await client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == task_id


@pytest.mark.asyncio
async def test_get_task_not_found(client):
    resp = await client.get("/api/tasks/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_task(client):
    create_resp = await client.post("/api/tasks", json={"name": "删除测试", "topic": "主题"})
    task_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/tasks/{task_id}")
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/tasks/{task_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_not_found(client):
    resp = await client.delete("/api/tasks/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_tasks_returns_multiple(client):
    for i in range(3):
        await client.post("/api/tasks", json={"name": f"任务{i}", "topic": f"主题{i}"})
    resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_run_task_already_running(client):
    create_resp = await client.post("/api/tasks", json={"name": "并发测试", "topic": "主题"})
    task_id = create_resp.json()["id"]

    # 将状态设为 running
    from web.backend.main import store
    store.update_task(task_id, {"status": "running"})

    resp = await client.post(f"/api/tasks/{task_id}/run")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_report_not_found(client):
    create_resp = await client.post("/api/tasks", json={"name": "报告测试", "topic": "主题"})
    task_id = create_resp.json()["id"]
    resp = await client.get(f"/api/tasks/{task_id}/report")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_report_with_file(client, tmp_path):
    create_resp = await client.post("/api/tasks", json={"name": "报告测试", "topic": "主题"})
    task_id = create_resp.json()["id"]

    # 创建假报告文件
    report_file = tmp_path / "report.md"
    report_file.write_text("# 测试报告\n\n内容", encoding="utf-8")

    from web.backend.main import store
    store.update_task(task_id, {"status": "done", "report_path": str(report_file)})

    resp = await client.get(f"/api/tasks/{task_id}/report")
    assert resp.status_code == 200
    assert resp.json()["content"] == "# 测试报告\n\n内容"


@pytest.mark.asyncio
async def test_list_templates(client):
    resp = await client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    # 应该至少有一些模板
    assert isinstance(data, list)
    if data:
        assert "id" in data[0]
        assert "name" in data[0]


@pytest.mark.asyncio
async def test_get_sources(client):
    resp = await client.get("/api/sources")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    source_names = [s["name"] for s in data]
    assert "rss" in source_names


# ─── TaskStore 单元测试 ────────────────────────────────────────────────────────

class TestTaskStore:
    def test_create_and_get(self, tmp_path):
        from web.backend.storage import TaskStore
        from web.backend.schemas import TaskCreate
        store = TaskStore(store_file=tmp_path / "tasks.json")
        body = TaskCreate(name="测试", topic="主题")
        task = store.create_task(body)
        assert task["name"] == "测试"
        assert task["status"] == "pending"

        got = store.get_task(task["id"])
        assert got is not None
        assert got["id"] == task["id"]

    def test_update_task(self, tmp_path):
        from web.backend.storage import TaskStore
        from web.backend.schemas import TaskCreate
        store = TaskStore(store_file=tmp_path / "tasks.json")
        task = store.create_task(TaskCreate(name="更新测试", topic="主题"))
        updated = store.update_task(task["id"], {"status": "running"})
        assert updated["status"] == "running"

    def test_delete_task(self, tmp_path):
        from web.backend.storage import TaskStore
        from web.backend.schemas import TaskCreate
        store = TaskStore(store_file=tmp_path / "tasks.json")
        task = store.create_task(TaskCreate(name="删除测试", topic="主题"))
        assert store.delete_task(task["id"])
        assert store.get_task(task["id"]) is None
        assert not store.delete_task(task["id"])  # 重复删除

    def test_list_sorted_by_created_at(self, tmp_path):
        from web.backend.storage import TaskStore
        from web.backend.schemas import TaskCreate
        store = TaskStore(store_file=tmp_path / "tasks.json")
        for name in ["A", "B", "C"]:
            store.create_task(TaskCreate(name=name, topic="主题"))
        tasks = store.list_tasks()
        assert len(tasks) == 3
        # 最新在前（created_at 降序）
        assert tasks[0]["name"] == "C"

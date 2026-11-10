import re

from httpx import AsyncClient

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


async def create_sample(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/entries",
        json={
            "kind": "expense",
            "content": "午饭 32 元",
            "occurredAt": "2026-11-09T12:30:00.000+08:00",
            "amount": 32,
            "category": "餐饮",
            "title": "工作日午餐",
            "tags": ["工作餐"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_entry_returns_201_and_contract(client: AsyncClient):
    body = await create_sample(client)

    assert body["kind"] == "expense"
    assert body["content"] == "午饭 32 元"
    assert body["amount"] == 32.0
    assert body["category"] == "餐饮"
    assert body["source"] == "manual"
    assert body["occurredAt"] == "2026-11-09T04:30:00.000Z"
    assert ISO_Z.match(body["createdAt"])
    assert ISO_Z.match(body["updatedAt"])


async def test_patch_keeps_omitted_fields_and_clears_explicit_null(client: AsyncClient):
    created = await create_sample(client)
    entry_id = created["id"]

    patched = await client.patch(f"/api/entries/{entry_id}", json={"content": "晚饭 32 元"})
    assert patched.status_code == 200
    body = patched.json()
    assert body["content"] == "晚饭 32 元"
    assert body["title"] == "工作日午餐"
    assert body["amount"] == 32.0
    assert body["category"] == "餐饮"

    cleared = await client.patch(
        f"/api/entries/{entry_id}",
        json={"title": None, "amount": None, "category": None},
    )
    assert cleared.status_code == 200
    body = cleared.json()
    assert body["title"] is None
    assert body["amount"] is None
    assert body["category"] is None
    assert body["content"] == "晚饭 32 元"


async def test_patch_rejects_null_for_non_nullable_fields(client: AsyncClient):
    created = await create_sample(client)

    response = await client.patch(f"/api/entries/{created['id']}", json={"occurredAt": None})
    assert response.status_code == 400
    assert response.json()["error"] == "参数不合法"

    response = await client.patch(f"/api/entries/{created['id']}", json={"tags": None})
    assert response.status_code == 400


async def test_validation_error_format(client: AsyncClient):
    response = await client.post("/api/entries", json={})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "参数不合法"
    assert "content" in body["detail"]


async def test_delete_returns_204_then_404(client: AsyncClient):
    created = await create_sample(client)

    deleted = await client.delete(f"/api/entries/{created['id']}")
    assert deleted.status_code == 204
    assert deleted.content == b""

    again = await client.delete(f"/api/entries/{created['id']}")
    assert again.status_code == 404
    assert again.json() == {"error": "记录不存在"}


async def test_stats_missing_range_returns_400(client: AsyncClient):
    response = await client.get("/api/stats")
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "参数不合法"
    assert "from" in body["detail"] or "to" in body["detail"]


async def test_write_is_visible_immediately_after_response(client: AsyncClient):
    """写路由必须在返回响应前 commit，客户端紧接着的 GET 不能读到旧数据。"""
    created = await create_sample(client)
    entry_id = created["id"]

    listing = await client.get("/api/entries")
    assert any(item["id"] == entry_id for item in listing.json()["items"])

    patched = await client.patch(f"/api/entries/{entry_id}", json={"content": "更新后内容"})
    assert patched.status_code == 200
    detail = await client.get(f"/api/entries/{entry_id}")
    assert detail.json()["content"] == "更新后内容"

    deleted = await client.delete(f"/api/entries/{entry_id}")
    assert deleted.status_code == 204
    missing = await client.get(f"/api/entries/{entry_id}")
    assert missing.status_code == 404

import httpx

from muc_notice_engine.config import Settings
from muc_notice_engine.core.auth import NOTICE_API_URL, MucAuthService


def _service(tmp_path) -> MucAuthService:
    return MucAuthService(
        Settings(
            data_dir=tmp_path,
            db_path=tmp_path / "t.db",
            muc_username="u",
            muc_password="p",
        )
    )


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )


async def test_login_follows_redirect_when_cas_session_valid(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "ca.muc.edu.cn" in str(request.url):
            return httpx.Response(
                302,
                headers={"Location": "https://my.muc.edu.cn/user/simpleSSOLogin?ticket=x"},
            )
        if "simpleSSOLogin" in str(request.url):
            return httpx.Response(200, text="<html>portal</html>")
        if str(request.url) == NOTICE_API_URL:
            return httpx.Response(200, json={"state": True, "datas": {"tables": []}})
        return httpx.Response(404)

    service = _service(tmp_path)
    client = _client(handler)
    assert await service._do_login(client) is True
    await client.aclose()


async def test_verify_rejects_invalid_comsys_session(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="error_comsys_session_invalid")

    service = _service(tmp_path)
    client = _client(handler)
    assert await service._verify_login(client) is False
    await client.aclose()

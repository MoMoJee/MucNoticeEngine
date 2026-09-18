"""MUC 统一身份认证（SM2 国密加密登录 + Cookie 持久化）。

移植自 astrbot_plugin_MUC_Notices/auth_service.py，去掉 AstrBot 依赖，
路径改为由 Settings 提供。
"""

from __future__ import annotations

import base64
import json
import logging
import re
import stat
from pathlib import Path

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)

# 兜底公钥：仅在页面中未能解析出实时公钥时使用。CAS 服务端会不定期轮换该公钥，
# 正常流程下应始终优先使用从登录页面动态提取到的公钥。
MUC_SM2_PUBLIC_KEY_FALLBACK = (
    "BMgXvoCLbC9cF8JAS/bv6Gd82+K+fFC2nRi7QJO3GvDkx0iLBmqDMpQUBxjC3yTfXN83cPVZRplPDsvr92K4omA="
)
LOGIN_PAGE_URL = "https://ca.muc.edu.cn/zfca/login"
PORTAL_SERVICE = "https://my.muc.edu.cn/user/simpleSSOLogin"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
NOTICE_API_URL = "https://my.muc.edu.cn/comsys-portal-notice-web/getNoticeByPage"
AJAX_HEADERS = {
    "User-Agent": USER_AGENT,
    "Origin": "https://my.muc.edu.cn",
    "Referer": "https://my.muc.edu.cn/page/11",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}


class MucAuthService:
    """负责登录、复用 Cookie，并向 fetcher 提供已认证的 httpx client。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: httpx.AsyncClient | None = None
        self._cookies_loaded = False
        self._login_success = False

    @property
    def username(self) -> str:
        return str(self.settings.muc_username).strip()

    @property
    def password(self) -> str:
        return str(self.settings.muc_password).strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.username and self.password)

    @property
    def cookie_file_path(self) -> Path:
        return self.settings.data_dir / "muc_cookies.json"

    async def ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                follow_redirects=False,
                timeout=self.settings.request_timeout_seconds,
            )
        return self._client

    def invalidate(self) -> None:
        """标记登录态失效；下次 get_authenticated_client() 会重新登录。"""
        self._login_success = False

    async def get_authenticated_client(self) -> httpx.AsyncClient | None:
        client = await self.ensure_client()

        if not self.is_configured:
            return None

        if self._login_success:
            return client

        if not self._cookies_loaded:
            if await self._load_cookies():
                if await self._verify_login(client):
                    logger.info("[AUTH] 缓存 Cookie 有效，直接复用。")
                    self._login_success = True
                    self._cookies_loaded = True
                    return client
                logger.info("[AUTH] 缓存 Cookie 已过期，重新登录。")
            self._cookies_loaded = True

        if await self._do_login(client):
            await self._save_cookies(client)
            self._login_success = True
            return client

        logger.warning("[AUTH] 登录失败，请检查账号密码配置。")
        return None

    async def _do_login(self, client: httpx.AsyncClient) -> bool:
        try:
            login_url = f"{LOGIN_PAGE_URL}?service={httpx.URL(PORTAL_SERVICE)}"
            resp = await client.get(
                login_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            resp.raise_for_status()

            html = resp.text
            m = re.search(r'name="flowId"\s+value="([^"]+)"', html)
            if not m:
                logger.error("[AUTH] 未找到 flowId")
                return False
            flow_id = m.group(1)

            pk_match = re.search(r'"publicKey"\s*:\s*"([^"]+)"', html)
            sm2_public_key = (
                pk_match.group(1) if pk_match else MUC_SM2_PUBLIC_KEY_FALLBACK
            )
            if not pk_match:
                logger.warning("[AUTH] 未解析到 SM2 公钥，使用兜底公钥（可能已过期）。")

            encrypted_password = await self._sm2_encrypt(self.password, sm2_public_key)

            resp = await client.post(
                login_url,
                data={
                    "username": self.username,
                    "password": encrypted_password,
                    "loginType": "username_password",
                    "flowId": flow_id,
                    "captcha": "",
                    "delegator": "",
                    "tokenCode": "",
                    "continue": "",
                    "asserts": "",
                    "submit": "登录",
                    "pageFrom": "",
                },
                headers={
                    "Referer": login_url,
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

            ru = resp.headers.get("Location", "")
            max_redirects = 10
            while ru and max_redirects > 0:
                if ru.startswith("/"):
                    ru = f"{resp.url.scheme}://{resp.url.netloc}{ru}"
                resp = await client.get(ru, follow_redirects=False)
                ru = resp.headers.get("Location", "")
                max_redirects -= 1

            if "my.muc.edu.cn" in str(resp.url) and resp.status_code == 200:
                if await self._verify_login(client):
                    logger.info("[AUTH] 登录成功！")
                    return True
                logger.warning("[AUTH] 落回门户页但会话校验未通过（登录实际失败）。")
                return False

            logger.warning(
                "[AUTH] 登录异常，最终 URL=%s，状态码=%s", resp.url, resp.status_code
            )
            return False

        except Exception as exc:  # noqa: BLE001
            logger.error("[AUTH] 登录异常：%s", exc)
            return False

    async def _sm2_encrypt(self, plaintext: str, public_key_b64: str) -> str:
        try:
            from gmssl.sm2 import CryptSM2

            pubkey_bytes = base64.b64decode(public_key_b64)
            if len(pubkey_bytes) == 65 and pubkey_bytes[0] == 0x04:
                x_hex = pubkey_bytes[1:33].hex()
                y_hex = pubkey_bytes[33:65].hex()
                sm2 = CryptSM2("placeholder", x_hex + y_hex, mode=1)
                encrypted = sm2.encrypt(plaintext.encode("utf-8"))
                return base64.b64encode(encrypted).decode("ascii")
        except ImportError:
            logger.warning("[AUTH] gmssl 未安装，退回明文密码（不推荐）。")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[AUTH] SM2 加密失败: %s，退回明文密码。", exc)
        return plaintext

    async def _verify_login(self, client: httpx.AsyncClient) -> bool:
        try:
            resp = await client.post(
                NOTICE_API_URL,
                data={"currentPage": 1, "pageSize": 1, "type": 5},
                headers=AJAX_HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("state") is not False:
                    return True
            return False
        except Exception:  # noqa: BLE001
            return False

    async def _save_cookies(self, client: httpx.AsyncClient) -> None:
        try:
            cookies_data = [
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path or "/",
                }
                for cookie in client.cookies.jar
            ]
            if not cookies_data:
                logger.warning("[AUTH] 无 Cookie 可保存")
                return

            self.cookie_file_path.parent.mkdir(parents=True, exist_ok=True)
            self.cookie_file_path.write_text(
                json.dumps(cookies_data, ensure_ascii=False), encoding="utf-8"
            )
            try:
                self.cookie_file_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            except Exception as perm_exc:  # noqa: BLE001
                logger.warning("[AUTH] 设置 Cookie 文件权限失败: %s", perm_exc)
            logger.info("[AUTH] %d 个 Cookie 已保存", len(cookies_data))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[AUTH] 保存 Cookie 失败: %s", exc)

    async def _load_cookies(self) -> bool:
        if not self.cookie_file_path.exists():
            return False
        try:
            cookies_data = json.loads(
                self.cookie_file_path.read_text(encoding="utf-8")
            )
            client = await self.ensure_client()
            for c in cookies_data:
                client.cookies.set(
                    name=c["name"],
                    value=c["value"],
                    domain=c.get("domain", ""),
                    path=c.get("path", "/"),
                )
            logger.info("[AUTH] 从文件加载了 %d 个 Cookie", len(cookies_data))
            return bool(cookies_data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[AUTH] 加载 Cookie 失败: %s", exc)
            return False

    async def fetch_portal_notices(self, type_id: int = 5) -> list[dict]:
        """通过门户 API 获取通知（外部调用）。"""
        client = await self.get_authenticated_client()
        if client is None:
            return []
        try:
            resp = await client.post(
                NOTICE_API_URL,
                data={"currentPage": 1, "pageSize": 10, "type": type_id},
                headers=AJAX_HEADERS,
            )
            data = resp.json()
            return data.get("datas", {}).get("tables", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("[AUTH] 获取门户通知失败: %s", exc)
            return []

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            self._login_success = False
            self._cookies_loaded = False

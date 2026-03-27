"""微信公众号数据源"""
import json
import logging
import subprocess
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .base import BaseSource
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)

_API_URL = (
    "https://mp.weixin.qq.com/cgi-bin/appmsgpublish"
    "?sub=list&begin=0&count=10&query="
    "&fakeid={fakeid}&type=101_1&free_publish_type=1&sub_action=list_ex"
    "&token={token}&lang=zh_CN&f=json&ajax=1"
)


class WeChatSource(BaseSource):
    """微信公众号数据源，通过 appmsgpublish API 抓取"""

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self._auth: dict | None = None

    def _load_auth(self) -> dict:
        if self._auth:
            return self._auth
        auth_file = Path(self.config.get("auth", "~/.researchkit/wechat-auth.json")).expanduser()
        if not auth_file.exists():
            raise FileNotFoundError(f"微信认证文件不存在：{auth_file}")
        with open(auth_file, encoding="utf-8") as f:
            self._auth = json.load(f)
        return self._auth

    def _get_articles(self, biz: str, cookie: str, token: str) -> list:
        fakeid = urllib.parse.quote(biz, safe="")
        url = _API_URL.format(fakeid=fakeid, token=token)
        result = subprocess.run(
            ["curl", "-s", url,
             "-H", "accept: */*",
             "-b", cookie,
             "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
             "-H", "x-requested-with: XMLHttpRequest"],
            capture_output=True, text=True, timeout=15,
        )
        try:
            data = json.loads(result.stdout)
        except Exception:
            return []

        if data.get("base_resp", {}).get("ret") != 0:
            logger.warning(f"微信 API 返回异常（Token 可能已过期）：{data.get('base_resp')}")
            return []

        publish_page = json.loads(data.get("publish_page", "{}"))
        articles = []
        for item in publish_page.get("publish_list", []):
            pinfo = json.loads(item.get("publish_info", "{}"))
            sent_t = (pinfo.get("sent_info") or {}).get("time", 0)
            for msg in (pinfo.get("appmsgex") or []):
                if msg.get("is_deleted"):
                    continue
                ts = msg.get("update_time", 0) or sent_t or msg.get("create_time", 0)
                articles.append({
                    "title": msg.get("title", ""),
                    "url": msg.get("link", ""),
                    "ts": ts,
                    "digest": msg.get("digest", ""),
                })
        return articles

    def fetch(self, context: ResearchContext, since: datetime, limit: int = 50) -> list:
        try:
            auth = self._load_auth()
        except FileNotFoundError as e:
            logger.error(str(e))
            return []

        cookie = auth.get("cookie", "")
        token = auth.get("token", "")
        accounts = self.config.get("accounts", [])
        results = []
        since_ts = int(since.timestamp()) if since else 0

        for acc in accounts:
            biz = acc.get("biz", "")
            acc_name = acc.get("name", biz)
            if not biz:
                continue
            try:
                raw = self._get_articles(biz, cookie, token)
                for a in raw:
                    if a["ts"] < since_ts:
                        continue
                    pub_dt = datetime.fromtimestamp(a["ts"], tz=timezone.utc) if a["ts"] else None
                    article = Article(
                        title=a["title"],
                        url=a["url"],
                        source_type="wechat",
                        source_name=acc_name,
                        summary=a["digest"],
                        published_at=pub_dt,
                    )
                    if article.title and article.url:
                        results.append(article)
                time.sleep(0.3)  # 礼貌性延迟
            except Exception as e:
                logger.warning(f"抓取公众号 {acc_name} 失败: {e}")

        results.sort(key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return results[:limit]

    def health_check(self) -> tuple:
        try:
            auth = self._load_auth()
            from datetime import date
            updated = auth.get("updated_at", "")
            if updated:
                days = (date.today() - date.fromisoformat(updated[:10])).days
                if days >= 7:
                    return False, f"微信 Token 已 {days} 天未更新，请刷新"
            return True, f"已配置 {len(self.config.get('accounts', []))} 个公众号"
        except FileNotFoundError as e:
            return False, str(e)

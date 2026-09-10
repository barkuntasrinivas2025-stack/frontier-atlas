from __future__ import annotations
import asyncio
from urllib.parse import urlparse
import aiohttp

class GitHubMetricsClient:
    def __init__(self, token: str | None = None, concurrency: int = 5, timeout_seconds: int = 20):
        self.token = token or ""
        self.semaphore = asyncio.Semaphore(concurrency)
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    @staticmethod
    def parse_repo(url: str) -> tuple[str, str] | None:
        p = urlparse(url.strip())
        if p.netloc.lower() not in {"github.com", "www.github.com"}: return None
        parts = [x for x in p.path.split("/") if x]
        return (parts[0], parts[1].removesuffix(".git")) if len(parts) >= 2 else None

    async def get_repo(self, url: str, session: aiohttp.ClientSession | None = None) -> dict[str, object] | None:
        parsed = self.parse_repo(url)
        if not parsed: return None
        api = f"https://api.github.com/repos/{parsed[0]}/{parsed[1]}"
        headers = {"Accept":"application/vnd.github+json", "User-Agent":"FrontierAtlas/1.0"}
        if self.token: headers["Authorization"] = f"Bearer {self.token}"
        own = session is None
        s = session or aiohttp.ClientSession(timeout=self.timeout)
        try:
            async with self.semaphore:
                for attempt in range(4):
                    try:
                        async with s.get(api, headers=headers) as r:
                            if r.status == 200:
                                d = await r.json()
                                return {"url": d.get("html_url", url), "stars": int(d.get("stargazers_count", 0)), "forks": int(d.get("forks_count", 0)), "updated_at": d.get("updated_at")}
                            if r.status in {403,429}:
                                ra = r.headers.get("Retry-After")
                                await asyncio.sleep(float(ra) if ra else min(2 ** attempt, 20) + 0.25); continue
                            if r.status == 404: return None
                            if r.status >= 500:
                                await asyncio.sleep(min(2 ** attempt, 20) + 0.25); continue
                            return None
                    except (aiohttp.ClientError, asyncio.TimeoutError):
                        if attempt == 3: return None
                        await asyncio.sleep(min(2 ** attempt, 20) + 0.25)
            return None
        finally:
            if own: await s.close()

    async def enrich_urls(self, urls: list[str]) -> dict[str, dict[str, object] | None]:
        async with aiohttp.ClientSession(timeout=self.timeout) as s:
            values = await asyncio.gather(*(self.get_repo(u, s) for u in urls))
        return dict(zip(urls, values))

async def github_repo_metrics(url, token=None, session=None):
    return await GitHubMetricsClient(token=token).get_repo(url, session)

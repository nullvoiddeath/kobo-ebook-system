import aiohttp

_TIMEOUT = aiohttp.ClientTimeout(total=60)


async def fetch_json(url: str, params: dict | None = None) -> dict | list:
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()


async def fetch_text(url: str) -> str:
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.text()

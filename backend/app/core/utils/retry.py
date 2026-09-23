import asyncio

import httpx

TRANSIENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError)


async def retry_async(fn, *, attempts: int = 3, base_delay: float = 0.5, retry_on=TRANSIENT, sleep=asyncio.sleep):
    last: Exception | None = None
    for i in range(attempts):
        try:
            return await fn()
        except retry_on as e:
            last = e
            if i < attempts - 1:
                await sleep(base_delay * (2 ** i))
    raise last

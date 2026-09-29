"""Async fixture for parser testing."""

import asyncio


async def fetch_data(url: str) -> dict:
    """Fetch data asynchronously."""
    await asyncio.sleep(0)
    return {}


async def process_batch(items: list) -> list:
    results = []
    for item in items:
        result = await fetch_data(str(item))
        results.append(result)
    return results


class AsyncService:
    """Service with async methods."""

    async def process(self, data: dict) -> None:
        """Process data asynchronously."""
        result = await fetch_data("http://example.com")
        return result

    async def batch(self, items: list) -> list:
        return await process_batch(items)

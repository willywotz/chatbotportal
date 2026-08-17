import asyncio

from fastmcp import Client


async def main() -> None:
    async with Client("https://chatbotportal.opdc.ai.in.th/mcp") as client:
        print(await client.call_tool("list_agency"))


if __name__ == "__main__":
    asyncio.run(main())

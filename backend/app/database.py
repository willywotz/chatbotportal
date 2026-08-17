from tortoise import Tortoise
from app.config import TORTOISE_ORM
from aerich import Command

async def init_db() -> None:
    async with Command(tortoise_config=TORTOISE_ORM) as command:
        await command.upgrade()

    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas(safe=True)

    from app.services.llm.seed import seed_llm_defaults
    await seed_llm_defaults()

async def close_db() -> None:
    await Tortoise.close_connections()
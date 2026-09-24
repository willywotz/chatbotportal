def test_langchain_stack_importable():
    import langchain_core
    from langchain.chat_models import init_chat_model
    from langchain_core.callbacks import get_usage_metadata_callback
    from langchain_core.rate_limiters import BaseRateLimiter
    import langchain_openai
    assert callable(init_chat_model)
    assert tuple(int(p) for p in langchain_core.__version__.split(".")[:3]) >= (0, 3, 49)

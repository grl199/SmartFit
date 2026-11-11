from functools import lru_cache

from openai import OpenAI

from .vault import get_openai_api_key


@lru_cache
def get_client() -> OpenAI:
    return OpenAI(api_key=get_openai_api_key())

from main import RequestManager
from tenacity import retry


async def test_cache_and_retry(redis_connection, clean_redis) -> None:
    @RequestManager(service_name='test', redis_connection=redis_connection, request_retryer=retry,)
    async def request_to_integrator():
        pass

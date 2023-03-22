# Принцип работы библиотеки

1) [Удаление кэша по сроку жизни](#ttlinvalidator)
2) [Стратегия фонового обновления кэша](#backgroundupdater)
3) [Ретраер](#retry)
4) [Ограничитель_запросов](#ratelimiter)

## TTLInvalidator

| Плюсы                                                           | Минусы                                                                                      |
|-----------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| Самая простая реализации с точки  зрения разработки и понимания | негибкая стратегия                                                                          |
|                                                                 | Не все данные можно так кэшировать                                                          |
|                                                                 | проблематично во время тестирования,  так придется либо ждать либо вручную удалять значения |

### Пример
```
from lk_request_manager import RequestManager
from lk_request_manager.ttl_strategy import TTLInvalidator


@RequestManager(
    cache_strategy=TTLInvalidator(
        cache_service=BaseCacheControlService(redis_connection=redis_connection),
    ),
    service_name='lk_simi',
    service_version='1.70.0',
    integration='simi',
    integration_method='getHtml'
)
async def example_integration_method(*args, **kwargs):
    pass
```
---
Либо же делать инициализацию на старте приложения, а
затем переиспользовать декоратор
```
from lk_request_manager import RequestManager
from lk_request_manager.ttl_strategy import TTLInvalidator


ttl_cache_strategy = RequestManager(
    cache_strategy=TTLInvalidator(
        cache_service=BaseCacheControlService(redis_connection=redis_connection),
    ),
    service_name='lk_simi',
    service_version='1.70.0',
    integration='simi',
    integration_method='getHtml'
)
```
```

@ttl_cache_strategy
async def example_integrator():
    pass
```


## BackgroundUpdater

Идеально подходит для сценариев, когда для
ускорения прогрузки страницы допустимо показать не самые свежие данные
(не больше чем срок жизни кэша), а затем обновить их

Также как и кэш работающий по TTL увеличивает доступность системы,
но при этом обладает более высокой согласованностью данных гораздо лучше

Согласованность будет лучше, так как обновление данных будет происходить чаще


| Плюсы                                                                   | Минусы                                                      |
|-------------------------------------------------------------------------|-------------------------------------------------------------|
| можно кэшировать даже те данные, которые часто обновляются              | Более сложная реализация                                    |
| практически гарантирует что следующее получение кэша будет самым свежим | требуются доработки на фронте, чтобы перезапрашивать данные |
|                                                                         |                                                             |

### Схематичный принцип работы

````mermaid
flowchart LR

    subgraph Кэш_есть[Получение данных, когда кэша нет]
    Сервис1[Сервис]--> Кэш1[Кэш]

    end
    Сервис1[Сервис]-..->|фоновая задача| Ограничитель_запросов



    subgraph Кэш_есть2[Обновление кэша]

    Ограничитель_запросов -->Ретраер
    Ретраер --> Интегратор[(Интегратор)]


    end


    subgraph  Кэша_нет[Получение данных когда нет кэша]
    Сервис2[Сервис] ----> Ретраер


    end
````
### Пример

```
from lk_request_manager import RequestManager
from lk_request_manager.ttl_strategy import BackgroundUpdater

background_update_cache_strategy = RequestManager(
    cache_strategy=BackgroundUpdater(
        cache_service=BaseCacheControlService(redis_connection=redis_connection),
        redis_connection=redis_connection,
    ),
    service_name='lk_simi',
    service_version='1.70.0',
    integration='simi',
    integration_method='getHtml'
)

@background_update_cache_strategy
async def example_integrator():
    pass
```

## Retry

Опционально есть возможность добавить повторные попытки

Под капотом используется библиотека tenacity


```
cache_strategy=BackgroundUpdater(
    cache_service=BaseCacheControlService(redis_connection=redis_connection),
    redis_connection=redis_connection,
    use_retry=True
),
```

чтобы конфигурировать повторные попытки(ограничить число, увеличивать время по геометрической прогрессии и тд)
можно прокидывать аргументы через kwargs


#### Например
```
from tenacity import retry_if_exception_type

cache_strategy=BackgroundUpdater(
    cache_service=BaseCacheControlService(redis_connection=redis_connection),
    redis_connection=redis_connection,
    use_retry=True,
    retry=retry_if_exception_type(IOError)
),
```

## RateLimiter

Также есть возможность добавить ограничитель запросов
необходим, чтобы снизить нагрузку на интеграторов, что наиболее актуально при фоновом обновление кэша

```
cache_strategy=BackgroundUpdater(
    cache_service=BaseCacheControlService(redis_connection=redis_connection),
    redis_connection=redis_connection,
    rate_limiter=SlidingWindowRateLimiter
),
```

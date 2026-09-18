import pytest

from researchos.saas.rate_limit import FixedWindowRateLimiter, SupabaseRateLimiter


class Response:
    def __init__(self, data):
        self.data = data


class RpcQuery:
    def __init__(self, response):
        self.response = response
        self.name = None
        self.params = None

    def execute(self):
        return self.response


class Client:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return RpcQuery(Response(next(self.values)))


def test_fixed_window_rate_limiter_enforces_limit() -> None:
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=60)

    assert limiter.allow("key") is True
    assert limiter.allow("key") is True
    assert limiter.allow("key") is False


def test_supabase_rate_limiter_calls_atomic_rpc() -> None:
    client = Client([True, True, False])
    limiter = SupabaseRateLimiter(client, limit=2, window_seconds=60)

    assert limiter.allow("principal") is True
    assert limiter.allow("principal") is True
    assert limiter.allow("principal") is False
    assert client.calls == [
        ("consume_api_rate_limit", {
            "p_rate_key": "principal",
            "p_limit": 2,
            "p_window_seconds": 60,
        }),
        ("consume_api_rate_limit", {
            "p_rate_key": "principal",
            "p_limit": 2,
            "p_window_seconds": 60,
        }),
        ("consume_api_rate_limit", {
            "p_rate_key": "principal",
            "p_limit": 2,
            "p_window_seconds": 60,
        }),
    ]


def test_rate_limiters_reject_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        FixedWindowRateLimiter(limit=0, window_seconds=60)
    with pytest.raises(ValueError):
        SupabaseRateLimiter(Client([]), limit=120, window_seconds=0)

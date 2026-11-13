"""U9: RemoteModel, the orchestrator's stand-in for the model, with a fake AI server.

httpx.MockTransport answers in memory, so no server, socket or file is involved.
"""
import json

import httpx
import numpy as np
import pandas as pd
import pytest

from ashaway.services.orchestrator import ModelUnavailable, RemoteModel

INFO = {"version": "v-test", "features": ["a", "b"], "medium_from": 0.2, "high_from": 0.5}


def fake_ai(seen):
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/model":
            return httpx.Response(200, json=INFO)
        rows = json.loads(request.content)["rows"]
        return httpx.Response(200, json={"model_version": "v-test", "probabilities": [r["a"] / 10 for r in rows]})
    return handle


def test_U9_sends_only_the_model_features_and_reads_the_probabilities():
    seen = []
    model = RemoteModel(httpx.Client(base_url="http://ai", transport=httpx.MockTransport(fake_ai(seen))), "req-1")
    rows = pd.DataFrame({"date": ["2023-07-18", "2023-07-19"], "b": [2.0, 4.0], "a": [3.0, 7.0]})
    p = model.predict(rows)
    np.testing.assert_allclose(p, [0.3, 0.7])
    sent = json.loads(seen[-1].content)["rows"]
    assert sent == [{"a": 3.0, "b": 2.0}, {"a": 7.0, "b": 4.0}]  # model features only, in model order
    assert all(r.headers["X-Request-ID"] == "req-1" for r in seen)


def test_U9_model_description_is_fetched_once_per_request():
    seen = []
    model = RemoteModel(httpx.Client(base_url="http://ai", transport=httpx.MockTransport(fake_ai(seen))))
    assert (model.version, model.medium_from, model.high_from) == ("v-test", 0.2, 0.5)
    assert [r.url.path for r in seen] == ["/model"]
    assert model.calls == 1


def unreachable(request):
    raise httpx.ConnectError("connection refused", request=request)


@pytest.mark.parametrize("transport", [
    httpx.MockTransport(unreachable),
    httpx.MockTransport(lambda r: httpx.Response(500, text="Internal Server Error")),
])
def test_U9_an_unreachable_or_failing_ai_server_raises_model_unavailable(transport):
    model = RemoteModel(httpx.Client(base_url="http://ai", transport=transport))
    with pytest.raises(ModelUnavailable):
        model.predict(pd.DataFrame({"a": [1.0], "b": [1.0]}))

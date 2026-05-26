"""Reranker 客户端测试"""

from unittest.mock import MagicMock, patch

import httpx

from src.retrieval.reranker import RerankerClient, RerankResult


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


class TestRerankerClientNormalCall:
    """正常调用 rerank API → 返回按 relevance_score 降序的结果"""

    def test_returns_results_in_api_order(self):
        client = RerankerClient(api_url="http://fake/v1/rerank", model="bge-reranker-large")

        api_response = {
            "id": "rerank-001",
            "results": [
                {"index": 1, "relevance_score": 0.95},
                {"index": 0, "relevance_score": 0.72},
                {"index": 2, "relevance_score": 0.31},
            ],
            "model": "bge-reranker-large",
        }

        with patch.object(httpx.Client, "post", return_value=_mock_response(api_response)):
            results = client.rerank(query="测试问题", documents=["a", "b", "c"], top_n=3)

        assert len(results) == 3
        assert results[0] == RerankResult(index=1, relevance_score=0.95)
        assert results[1] == RerankResult(index=0, relevance_score=0.72)
        assert results[2] == RerankResult(index=2, relevance_score=0.31)


class TestRerankerClientEmptyDocuments:
    """传入空 documents → 直接返回空列表，不发请求"""

    def test_empty_documents_returns_empty(self):
        client = RerankerClient(api_url="http://fake/v1/rerank", model="test")

        with patch.object(httpx.Client, "post") as mock_post:
            results = client.rerank(query="test", documents=[], top_n=5)

        assert results == []
        mock_post.assert_not_called()


class TestRerankerClientFailure:
    """API 调用失败 → 降级返回空列表，不抛异常"""

    def test_timeout_returns_empty(self):
        client = RerankerClient(api_url="http://fake/v1/rerank", model="test")

        with patch.object(httpx.Client, "post", side_effect=httpx.TimeoutException("timeout")):
            results = client.rerank(query="test", documents=["a", "b"], top_n=2)

        assert results == []

    def test_http_500_returns_empty(self):
        client = RerankerClient(api_url="http://fake/v1/rerank", model="test")

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_resp
        )

        with patch.object(httpx.Client, "post", return_value=mock_resp):
            results = client.rerank(query="test", documents=["a"], top_n=1)

        assert results == []

    def test_connection_error_returns_empty(self):
        client = RerankerClient(api_url="http://fake/v1/rerank", model="test")

        with patch.object(httpx.Client, "post", side_effect=httpx.ConnectError("refused")):
            results = client.rerank(query="test", documents=["a"], top_n=1)

        assert results == []

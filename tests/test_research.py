# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.9 — Internet Research Tests"""
import pytest
import memory.sqlite_store
import config as config_module
from core.research import _domain, _is_credible, _extract_text, ResearchAssistant
from memory.manager import MemoryManager

config_module.JWT_SECRET = "test-secret-32-bytes-long-1234567890"


@pytest.fixture
def assistant(tmp_path):
    db_path = tmp_path / "test_research.db"
    chroma_path = tmp_path / "chroma"
    memory.sqlite_store.DB_PATH = db_path
    memory.vector_store.CHROMA_PATH = chroma_path
    return ResearchAssistant(MemoryManager(), cache_ttl_hours=1)


def test_domain_extraction():
    assert _domain("https://www.example.com/path") == "example.com"
    assert _domain("http://site.org") == "site.org"


def test_source_credibility():
    assert _is_credible("https://example.com/article", "A real article")
    assert not _is_credible("https://youtube.com/watch", "Video")
    assert not _is_credible("https://twitter.com/post", "Tweet")
    assert not _is_credible("https://example.com", "")


def test_extract_text_from_html():
    html = """
    <html>
      <head><title>Test</title><script>alert('x')</script></head>
      <body>
        <nav>Menu</nav>
        <article>
          <h1>Hello World</h1>
          <p>This is the main content.</p>
        </article>
        <footer>Footer</footer>
      </body>
    </html>
    """
    text = _extract_text(html)
    assert "Hello World" in text
    assert "main content" in text
    assert "alert" not in text
    assert "Menu" not in text
    assert "Footer" not in text


def test_research_cache(assistant):
    query = "test query"
    result = {"answer": "cached answer", "sources": [{"title": "T", "url": "http://t"}]}

    # Cache miss
    assert assistant.memory.get_research_cache(query) is None

    # Store
    import json
    assistant.memory.set_research_cache(query, json.dumps(result), ttl_hours=1)

    # Cache hit
    cached = assistant.memory.get_research_cache(query)
    assert cached is not None
    assert json.loads(cached)["answer"] == "cached answer"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_research_live_search(assistant):
    """Slow integration test requiring internet. Skipped by default with -m 'not slow'."""
    result = await assistant.research("what is the capital of France", max_results=3, fetch_full=False)
    assert "answer" in result
    assert "sources" in result
    assert len(result["sources"]) > 0
    assert "Paris" in result["answer"] or any("Paris" in s.get("snippet", "") for s in result["sources"])

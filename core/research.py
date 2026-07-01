# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.9 — Internet Research Module

Search the web, fetch pages, extract readable text, filter sources,
cache results, and summarize with citations.
"""
import json
import re
import time
import urllib.robotparser
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

from core.inference import generate_non_stream
from memory.manager import MemoryManager


@dataclass
class Source:
    title: str
    url: str
    snippet: str = ""
    content: str = ""


DEFAULT_BLOCKED_DOMAINS = {
    "facebook.com", "twitter.com", "x.com", "instagram.com", "tiktok.com",
    "youtube.com", "pinterest.com", "reddit.com",
}


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().lstrip("www.")


def _is_credible(url: str, title: str = "") -> bool:
    """Basic source filtering. Blocks known social sites and very short titles."""
    domain = _domain(url)
    if any(blocked in domain for blocked in DEFAULT_BLOCKED_DOMAINS):
        return False
    if len(title.strip()) < 5:
        return False
    return True


def _respects_robots(url: str) -> bool:
    """Check robots.txt for the URL's domain. Always returns True on error."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch("*", url)
    except Exception:
        return True


def _extract_text(html: str) -> str:
    """Extract readable text from HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "lxml")

    # Remove non-content tags
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    # Prefer article/main content
    main = soup.find("article") or soup.find("main") or soup.find("body") or soup
    text = main.get_text(separator="\n", strip=True)

    # Clean up
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:12000]  # Limit extracted text length


async def _fetch_page(url: str, timeout: float = 10.0) -> Optional[str]:
    """Fetch and extract text from a single URL."""
    if not _respects_robots(url):
        return None

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            headers = {
                "User-Agent": "EUNICE Research Bot/0.9 (personal assistant; research only)"
            }
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            if "text/html" not in resp.headers.get("content-type", ""):
                return None
            return _extract_text(resp.text)
    except Exception as e:
        return None


def _ddgs_search(query: str, max_results: int = 5) -> List[Source]:
    """Search DuckDuckGo and return sources."""
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results * 2):
                source = Source(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                )
                if _is_credible(source.url, source.title):
                    results.append(source)
                if len(results) >= max_results:
                    break
    except Exception as e:
        print(f"[RESEARCH] Search failed: {e}")
    return results


async def _fetch_sources(sources: List[Source], max_chars_per_source: int = 3000) -> List[Source]:
    """Fetch full content for sources."""
    fetched = []
    for source in sources:
        content = await _fetch_page(source.url)
        if content:
            source.content = content[:max_chars_per_source]
            fetched.append(source)
        # Be polite: small delay between fetches
        time.sleep(0.5)
    return fetched


def _build_context(sources: List[Source]) -> str:
    """Build a context string from fetched sources with citations."""
    lines = []
    for i, source in enumerate(sources, 1):
        lines.append(f"[Source {i}] {source.title}\nURL: {source.url}\n{source.content or source.snippet}")
    return "\n\n".join(lines)


async def _summarize(query: str, sources: List[Source]) -> dict:
    """Use the LLM to synthesize an answer from sources."""
    if not sources:
        return {
            "answer": "I couldn't find any relevant sources for that.",
            "sources": []
        }

    context = _build_context(sources)
    prompt = f"""You are EUNICE, a research assistant. Answer the user's question using ONLY the provided sources.
Be concise, accurate, and cite sources using [Source N] format.
If the sources don't contain the answer, say so — do not make things up.
If a source mentions a currency/item but does NOT explicitly rank it in the requested list, do not include it in a numbered ranking.
Never use contradictory phrasing like "not mentioned in the top X, but mentioned as..."
If the sources only provide a partial list, present exactly what they provide and note that it is incomplete.

User question: {query}

Sources:
{context}

Answer:"""

    answer = await generate_non_stream(prompt=prompt)
    answer = answer.strip() if answer else "I couldn't synthesize an answer from the sources."

    return {
        "answer": answer,
        "sources": [
            {"title": s.title, "url": s.url, "snippet": s.snippet}
            for s in sources
        ]
    }


class ResearchAssistant:
    """End-to-end internet research with caching."""

    def __init__(self, memory: MemoryManager = None, cache_ttl_hours: int = 24):
        self.memory = memory or MemoryManager()
        self.cache_ttl_hours = cache_ttl_hours

    async def research(self, query: str, max_results: int = 5, fetch_full: bool = True) -> dict:
        """Research a query and return a summarized answer with sources."""
        normalized_query = query.strip().lower()

        # Check cache
        cached = self.memory.get_research_cache(normalized_query)
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

        # Search
        sources = _ddgs_search(query, max_results=max_results)
        if not sources:
            return {
                "answer": "I couldn't find any relevant web sources for that.",
                "sources": []
            }

        # Fetch full content if requested
        if fetch_full:
            sources = await _fetch_sources(sources)

        # Summarize
        result = await _summarize(query, sources)

        # Cache
        self.memory.set_research_cache(normalized_query, json.dumps(result), ttl_hours=self.cache_ttl_hours)

        return result

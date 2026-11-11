"""web_search tool (Tavily)."""
import os

import requests

TOOLS = [{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current information.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Short search query"}},
            "required": ["query"],
        },
    },
}]


def web_search(args):
    query = args.get("query", "")
    print(f"[Searching: {query}]")
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return "Web search unavailable: TAVILY_API_KEY is not set."
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {key}"},
            json={"query": query, "max_results": 4, "include_answer": True},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return f"Search failed: {e}"
    parts = []
    if data.get("answer"):
        parts.append("Summary: " + data["answer"])
    for item in data.get("results", [])[:4]:
        content = (item.get("content") or "")[:300]
        parts.append(f"- {item.get('title', '')} ({item.get('url', '')}): {content}")
    return "\n".join(parts) or "No results found."


HANDLERS = {"web_search": web_search}
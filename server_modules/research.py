"""Web research for the stages that write in one call.

A stage that runs with tools searches the web itself. A stage that makes a single call cannot, so the search happens first: the model
writes the queries, Ollama's web search runs them, and the model writes up what is useful for the product. What each kind of stage
looks for is data, in `prompts/research/kinds.json`.
"""
from __future__ import annotations

from typing import Any, Callable

from . import llm, prompts

Say = Callable[[str], None]


def _queries(data: Any) -> list[str]:
    rows = data.get("queries") if isinstance(data, dict) else data
    found = [" ".join(str(q).split()) for q in (rows or []) if str(q).strip()]
    if not found:
        raise ValueError('give two or three search queries as {"queries": ["…"]}')
    return found[:3]


def gather(kind: str, product: str, outline: str, system: str, say: Say) -> str:
    """What the web says that is useful for this kind of stage and this product; "" when nothing could be found."""
    try:
        want = prompts.data("research/kinds")[kind]
    except (prompts.MissingPrompt, KeyError):
        return ""
    values = {"purpose": want["purpose"], "wanted": want["wanted"], "product": product, "outline": outline[:6000] or "(nothing yet)"}
    try:
        queries = llm.complete_json(system=system, label=f"research:{kind}", validator=_queries,
                                    user=prompts.load("research/queries", **values))
    except Exception as exc:  # noqa: BLE001 - the stage goes on without research
        say(f"Could not plan the web search ({str(exc)[:120]}); going on without it.")
        return ""
    found, seen = [], set()
    for query in queries:
        say(f'Searched the web for "{query}"')
        for row in llm.web_search(query, 4):
            if row["url"] and row["url"] not in seen:
                seen.add(row["url"])
                found.append(row)
    if not found:
        say("The web search returned nothing; going on without it.")
        return ""
    results = "\n\n".join(f"### {r['title']}\n{r['content']}" for r in found[:10])
    try:
        return llm.complete(system=system, user=prompts.load("research/digest", results=results, **values)).strip()
    except Exception as exc:  # noqa: BLE001
        say(f"Could not write the research up ({str(exc)[:120]}); going on without it.")
        return ""

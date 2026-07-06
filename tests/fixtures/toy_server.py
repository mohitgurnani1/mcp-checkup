# Copyright (c) mcp-checkup contributors.
# SPDX-License-Identifier: Apache-2.0

"""A tiny MCP server fixture with two lean tools and one deliberately bloated one.

Import-safe: nothing runs until executed as a script (stdio transport).
"""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("toy")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@mcp.tool()
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


_SEARCH_DESCRIPTION = """\
Search the toy corpus for documents matching a query, with an exhaustively
configurable retrieval pipeline. This tool exists to demonstrate what an
overweight tool definition looks like on the wire, so its description rambles
on with far more detail than any model could ever need. The search process
begins by tokenizing the query using a locale-aware analyzer that lowercases,
strips accents, folds compound words, expands common abbreviations, and applies
a stemming pass tuned for each supported language. The resulting terms are then
matched against an inverted index that stores positional information, so both
exact phrases and proximity-based matches can be scored. Scoring combines a
classic BM25 lexical component with an optional dense-vector semantic
component; the two are blended using a reciprocal rank fusion step whose
weights were chosen by a grid search nobody remembers running. After the
initial candidate set is assembled, a cascade of re-rankers may be applied:
first a lightweight gradient-boosted model over hand-crafted features such as
field length, term frequency saturation, and recency decay, then optionally a
cross-encoder that re-reads the full text of the top candidates. Results can
be filtered before or after ranking by arbitrary structured predicates,
grouped by collection, deduplicated by content hash, and paginated with a
stable cursor so that concurrent index updates do not cause items to be
skipped or repeated. Highlighting, when enabled, produces snippet fragments
with the matched terms wrapped in markers, trimmed to sentence boundaries
where possible. Metadata enrichment attaches source, author, timestamps, and
provenance records to every hit. Fuzzy matching tolerates typos up to a
configurable edit distance, at some cost to precision and latency. Timeouts
are enforced per shard and per request, and partial results are returned with
a flag rather than failing the entire call. In short: it searches things, and
it did not need this many words to say so.
"""


@mcp.tool(description=_SEARCH_DESCRIPTION)
def search(
    query: Annotated[
        str,
        Field(
            description=(
                "The free-text query to execute against the corpus. May contain quoted "
                "phrases for exact matching, a leading minus sign to exclude terms, and "
                "field-scoped clauses such as title:foo. Long queries are truncated to "
                "1024 characters after analyzer normalization, so put the important "
                "terms first if you are anywhere near that limit."
            )
        ),
    ],
    corpus: Annotated[
        str,
        Field(
            description=(
                "Name of the corpus or collection to search. Each corpus has its own "
                "analyzer configuration, ranking profile, and access control list, so "
                "the same query can return very different results across corpora. Use "
                "'default' unless you have a specific reason not to."
            )
        ),
    ] = "default",
    max_results: Annotated[
        int,
        Field(
            description=(
                "Maximum number of hits to return in this page, between 1 and 100. "
                "Larger pages increase tail latency roughly linearly because every "
                "extra candidate must pass through the re-ranking cascade before it "
                "can be returned to the caller."
            )
        ),
    ] = 10,
    offset: Annotated[
        int,
        Field(
            description=(
                "Zero-based index of the first hit to return, used for shallow "
                "pagination. Deep offsets beyond a few thousand are rejected; switch "
                "to cursor-based pagination instead, which remains stable even while "
                "the underlying index is being updated concurrently."
            )
        ),
    ] = 0,
    sort_by: Annotated[
        str,
        Field(
            description=(
                "Field to sort results by. The special value 'relevance' uses the "
                "blended lexical-plus-semantic ranking score; any other value must "
                "name a sortable indexed field such as 'created_at', 'title', or "
                "'popularity', otherwise the request fails validation."
            )
        ),
    ] = "relevance",
    sort_order: Annotated[
        str,
        Field(
            description=(
                "Direction of the sort, either 'asc' or 'desc'. Ignored when sort_by "
                "is 'relevance', because relevance-ordered results are always returned "
                "best-first regardless of what is requested here."
            )
        ),
    ] = "desc",
    filters: Annotated[
        str,
        Field(
            description=(
                "A JSON-encoded object of structured predicates applied to candidate "
                'documents before ranking, e.g. \'{"lang": "en", "year": '
                '{"gte": 2020}}\'. Supported operators are eq, neq, gt, gte, lt, '
                "lte, in, and exists. An empty string applies no filtering at all."
            )
        ),
    ] = "",
    include_metadata: Annotated[
        bool,
        Field(
            description=(
                "Whether to attach the full metadata record (source, author, "
                "timestamps, provenance chain) to every hit. Disable this when you "
                "only need titles and snippets, since the metadata block often "
                "dominates the response payload size."
            )
        ),
    ] = True,
    language: Annotated[
        str,
        Field(
            description=(
                "BCP-47 language tag used to select the query analyzer and stemmer, "
                "for example 'en', 'de', or 'ja'. The special value 'auto' runs a "
                "language detector over the query text first, adding a few "
                "milliseconds of latency per request."
            )
        ),
    ] = "auto",
    fuzziness: Annotated[
        float,
        Field(
            description=(
                "Maximum normalized edit distance tolerated when matching query terms, "
                "from 0.0 (exact matches only) to 1.0 (extremely permissive). Values "
                "above 0.4 noticeably hurt precision and increase latency, so prefer "
                "the default unless recall is desperate."
            )
        ),
    ] = 0.2,
    highlight: Annotated[
        bool,
        Field(
            description=(
                "Whether to return snippet fragments with matched terms wrapped in "
                "highlight markers. Snippets are trimmed to sentence boundaries where "
                "possible and capped at three fragments per hit, chosen by fragment "
                "score rather than document order."
            )
        ),
    ] = False,
    timeout_ms: Annotated[
        int,
        Field(
            description=(
                "Per-request time budget in milliseconds, enforced independently on "
                "every index shard. When the budget is exhausted, hits gathered so "
                "far are returned along with a partial-results flag instead of "
                "failing the whole request."
            )
        ),
    ] = 2000,
) -> str:
    """See the tool description; it says more than enough."""
    return f"no results for {query!r} in {corpus!r}"


@mcp.resource("toy://readme", description="The toy server's readme document.")
def readme() -> str:
    """Readme resource for the toy server."""
    return "# toy\n\nA tiny MCP server used as a test fixture for mcp-checkup."


@mcp.prompt(description="Produce a friendly greeting request.")
def hello(name: str = "world") -> str:
    """Prompt that asks for a friendly greeting."""
    return f"Please greet {name} warmly and briefly."


if __name__ == "__main__":
    mcp.run()

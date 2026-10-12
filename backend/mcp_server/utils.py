"""Deterministic parsing/export helpers for the standardized Bank Comparison
markdown table that `mcp_server.agent`'s system prompt requires the model to
produce.

These helpers do no LLM work — they mechanically parse the agent's already-
generated markdown reply and turn it into CSV, so an export endpoint or
frontend action can hand the user a .csv file without invoking the AI again.
"""

import csv
import io
import re

# Column order/wording is a hard contract with the system prompt in
# mcp_server.agent — changing either side without the other silently breaks
# export parsing.
BANK_TABLE_HEADERS = ("Bank Name", "Profit Rate", "Max Tenure", "Est Monthly EMI")

_SEPARATOR_ROW_PATTERN = re.compile(r"^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$")


def _split_table_row(line: str) -> list[str]:
    """Splits one markdown table row into trimmed cell strings.

    Tolerates optional leading/trailing pipes (`| a | b |` and `a | b` both
    parse the same way), matching how GitHub-flavored markdown tables are
    commonly written.
    """
    stripped = line.strip()
    stripped = stripped.removeprefix("|")
    stripped = stripped.removesuffix("|")
    return [cell.strip() for cell in stripped.split("|")]


def extract_bank_comparison_table(markdown_text: str) -> list[dict[str, str]]:
    """Extracts the standardized Bank Comparison table from an agent reply.

    Scans `markdown_text` for a markdown table whose header row matches
    `BANK_TABLE_HEADERS` exactly (same four columns, same order), then reads
    every contiguous row beneath it until the table ends.

    Args:
        markdown_text: The raw assistant reply, as returned by
            `agent.run_chat_agent` (its "reply" value).

    Returns:
        A list of dicts, one per bank row, each keyed by the entries in
        `BANK_TABLE_HEADERS`. Returns `[]` if no matching table is found —
        callers should treat that as "nothing to export", not an error.
    """
    lines = markdown_text.splitlines()

    for index, line in enumerate(lines):
        if "|" not in line:
            continue
        if tuple(_split_table_row(line)) != BANK_TABLE_HEADERS:
            continue
        if index + 1 >= len(lines) or not _SEPARATOR_ROW_PATTERN.match(
            lines[index + 1]
        ):
            continue

        rows = []
        for row_line in lines[index + 2 :]:
            if not row_line.strip() or "|" not in row_line:
                break
            cells = _split_table_row(row_line)
            if len(cells) != len(BANK_TABLE_HEADERS):
                break
            rows.append(dict(zip(BANK_TABLE_HEADERS, cells)))
        return rows

    return []


def bank_comparison_table_to_csv(rows: list[dict[str, str]]) -> str:
    """Renders parsed bank comparison rows as CSV text.

    Args:
        rows: Rows as returned by `extract_bank_comparison_table`.

    Returns:
        CSV text (comma-separated, `BANK_TABLE_HEADERS` as the header row),
        ready to be written to a `.csv` file or streamed as a download.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=BANK_TABLE_HEADERS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()

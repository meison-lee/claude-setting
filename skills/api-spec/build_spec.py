#!/usr/bin/env python3
"""Build a GAMAPASS-3295-style API spec as Atlassian Document Format (ADF)
and write it back to a Jira ticket's description.

Input: a JSON file (or stdin) describing one or more endpoints.
Output: --dry-run prints the ADF JSON; otherwise PUTs to the ticket.

Input schema:
{
  "ticket": "GAMAPASS-1234",          # target ticket key (omit if using --ticket)
  "endpoints": [
    {
      "method": "GET",                 # required
      "path": "/v1/faq",               # required
      "auth": {                        # required
        "value": "None",              # bold value, e.g. "None" / "Required" / "Bearer token"
        "note": "(public endpoint - no token required)"   # optional trailing note
      },
      "request": {                     # optional; omit sections that don't apply
        "pathParameters":  [ {"name","type","required","desc"}, ... ],
        "queryParameters": [ {"name","type","required","desc"}, ... ],
        "body": "{\n  \"x\": \"string\"\n}"   # raw JSON string, rendered as a json code block
      },
      "responseBody": "{\n  \"faqs\": []\n}",  # required; raw JSON string -> json code block
      "statusCodes": [                 # required
        {"code": "200 OK", "desc": "success, returns paginated FAQ items"}
      ]
    }
  ]
}

A single endpoint may be passed as the top-level object directly (no "endpoints" wrapper).
"""
import argparse
import json
import os
import sys
import urllib.request


# ---------- ADF node builders ----------

def text(s, marks=None):
    node = {"type": "text", "text": s}
    if marks:
        node["marks"] = [{"type": m} for m in marks]
    return node


def paragraph(*content):
    return {"type": "paragraph", "content": list(content)}


def bullet_list(items):
    """items: list of list-of-inline-nodes (one paragraph per list item)."""
    return {
        "type": "bulletList",
        "content": [
            {"type": "listItem", "content": [paragraph(*item)]}
            for item in items
        ],
    }


def code_block(code, language="json"):
    return {
        "type": "codeBlock",
        "attrs": {"language": language},
        "content": [text(code)],
    }


def param_item(p):
    req = "required" if p.get("required") else "optional"
    return [
        text(p["name"], marks=["code"]),
        text(f" ({p['type']}, {req}) — {p['desc']}"),
    ]


def _example_value(t):
    t = (t or "").lower()
    if t in ("bool", "boolean"):
        return "false"
    if t in ("int", "integer", "int32", "int64", "number", "float", "long"):
        return "0"
    if t in ("array", "list") or t.endswith("[]"):
        return "[]"
    if t in ("object", "map"):
        return "{}"
    return '"string"'


def changes_block(changes):
    """Render the added/modified fields as a single JSON code block.

    Each field becomes a line: "name": <example>,  // [kind:] description
    """
    lines = []
    for c in changes:
        val = c.get("example")
        if val is None:
            val = _example_value(c.get("type"))
        lines.append((f'  "{c["field"]}": {val}', c))
    width = max(len(code) for code, _ in lines)
    out = ["{"]
    for i, (code, c) in enumerate(lines):
        comma = "," if i < len(lines) - 1 else ""
        kind = c.get("kind")
        note = (f"{kind}: " if kind else "") + c["desc"]
        out.append(f"{code}{comma}".ljust(width + 2) + f"// {note}")
    out.append("}")
    return "\n".join(out)


def endpoint_blocks(ep):
    """Render one endpoint to a list of ADF block nodes, matching GAMAPASS-3295.

    For a NEW endpoint provide auth/request/responseBody/statusCodes (full spec).
    For a MODIFICATION of an existing endpoint, set "note" (e.g. claim it's an
    existing API) and "changes" (the added/modified fields); the full sections
    are optional and omitted when absent.
    """
    blocks = []

    # API Method and Path
    blocks.append(paragraph(
        text("API Method and Path: "),
        text(f"[{ep['method'].upper()}] {ep['path']}", marks=["code"]),
    ))

    # Description — what this new API / change does
    if ep.get("description"):
        blocks.append(paragraph(text("Description")))
        blocks.append(paragraph(text(ep["description"])))

    # Note (e.g. "Existing API — this ticket only adds the fields below")
    if ep.get("note"):
        blocks.append(paragraph(text(ep["note"])))

    # Authentication (optional — usually omitted for a pure modification)
    if ep.get("auth"):
        auth = ep["auth"]
        auth_inline = [text("Authentication: "), text(auth["value"], marks=["strong"])]
        if auth.get("note"):
            auth_inline.append(text(" " + auth["note"]))
        blocks.append(paragraph(*auth_inline))

    # API Changes (delta view for existing endpoints) — rendered as a code block
    if ep.get("changes"):
        blocks.append(paragraph(text("API Changes")))
        blocks.append(code_block(changes_block(ep["changes"])))

    # API Request (optional)
    req = ep.get("request") or {}
    has_request = req.get("pathParameters") or req.get("queryParameters") or req.get("body")
    if has_request:
        blocks.append(paragraph(text("API Request")))
        if req.get("pathParameters"):
            blocks.append(paragraph(text("Path Parameters:")))
            blocks.append(bullet_list([param_item(p) for p in req["pathParameters"]]))
        if req.get("queryParameters"):
            blocks.append(paragraph(text("Query Parameters:")))
            blocks.append(bullet_list([param_item(p) for p in req["queryParameters"]]))
        if req.get("body"):
            blocks.append(paragraph(text("Request Body:")))
            blocks.append(code_block(req["body"]))

    # API Response (Body) (optional)
    if ep.get("responseBody"):
        blocks.append(paragraph(text("API Response (Body)")))
        blocks.append(code_block(ep["responseBody"]))

    # Status Codes (optional)
    if ep.get("statusCodes"):
        blocks.append(paragraph(text("Status Codes")))
        blocks.append(bullet_list([
            [text(sc["code"], marks=["code"]), text(f" — {sc['desc']}")]
            for sc in ep["statusCodes"]
        ]))

    return blocks


def build_adf(endpoints):
    content = []
    for i, ep in enumerate(endpoints):
        if i > 0:
            content.append({"type": "rule"})
        content.extend(endpoint_blocks(ep))
    return {"type": "doc", "version": 1, "content": content}


# ---------- Jira write-back ----------

def update_ticket(ticket, adf):
    base = os.environ["JIRA_BASE_URL"].rstrip("/")
    email = os.environ["JIRA_EMAIL"]
    token = os.environ["JIRA_API_TOKEN"]
    import base64
    cred = base64.b64encode(f"{email}:{token}".encode()).decode()
    body = json.dumps({"fields": {"description": adf}}).encode()
    req = urllib.request.Request(
        f"{base}/rest/api/3/issue/{ticket}",
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Basic {cred}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", nargs="?", help="path to spec JSON (default: stdin)")
    ap.add_argument("--ticket", help="override target ticket key")
    ap.add_argument("--dry-run", action="store_true", help="print ADF, don't write")
    args = ap.parse_args()

    raw = open(args.spec).read() if args.spec else sys.stdin.read()
    data = json.loads(raw)

    endpoints = data["endpoints"] if "endpoints" in data else [data]
    ticket = args.ticket or data.get("ticket")
    adf = build_adf(endpoints)

    if args.dry_run:
        print(json.dumps(adf, indent=2, ensure_ascii=False))
        return

    if not ticket:
        sys.exit("No ticket key given (use --ticket or \"ticket\" field)")
    status = update_ticket(ticket, adf)
    print(f"Updated {ticket}: HTTP {status}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build a Jira ticket description (ADF) from a ticket JSON file, then create or update the issue.

Usage:
    python3 build_ticket.py ticket.json --dry-run   # render preview, touch nothing
    python3 build_ticket.py ticket.json             # create (no "ticket" key) or update (has "ticket")

Env: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN

Ticket JSON schema
------------------
{
  "ticket":     "GAMAPASS-1234",   // present => PUT (update description); absent => POST (create)
  "project":    "GAMAPASS",        // create only, default GAMAPASS
  "issuetype":  "Task",            // create only, default Task
  "summary":    "[BE] ...",        // required on create; on update, optional (present => retitle)

  "background":     [<block>, ...],  // 【背景／目的】 required
  "pending":        ["問題一", ...],  // 【待確認事項】 optional checklist, omit when nothing is blocked
  "implementation": [<block>, ...],  // 【實作方式】 required
  "impact":         [<block>, ...]   // 【影響範圍】 required
}

<block> is one of:
  {"p":  "段落文字"}                        paragraph
  {"h":  "小標題"}                          h3 sub-heading inside a section
  {"ul": ["項目", ...]}                     bullet list
  {"ol": ["步驟", ...]}                     numbered list
  {"code": "SELECT 1;", "lang": "sql"}      code block (lang default "text")
  {"tasks": ["待辦", ...]}                  checklist (Jira taskList)
  {"table": {"headers": ["A", "B"],         table; "headers" optional (renders a
             "rows": [["a1", "b1"], ...]}}     header row). A cell is a string, or a
                                               list of strings for multi-line cells.
  {"panel": "重點提示", "type": "warning"}   callout panel; type in info (default) /
                                               note / success / warning / error.
                                               Value may be a list for multiple lines.
  {"quote": "引用文字"}                      blockquote (string or list of strings)
  {"rule": true}                            horizontal divider (also accepts {"hr": true})

Inline markup inside any string: `code`, **bold**, and [text](https://url) links.
"""
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

SECTIONS = [
    ("background", "【背景／目的】"),
    ("pending", "【待確認事項】"),
    ("implementation", "【實作方式】"),
    ("impact", "【影響範圍】"),
]

_lid = [0]


def _next_lid():
    _lid[0] += 1
    return "ci-%d" % _lid[0]


# ---------------------------------------------------------------- inline markup

_INLINE = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))")
_LINK = re.compile(r"^\[([^\]]+)\]\(([^)]+)\)$")


def inline(text):
    """Split a string into ADF text nodes, honouring `code`, **bold**, [text](url)."""
    nodes = []
    for part in _INLINE.split(str(text)):
        if not part:
            continue
        if part.startswith("`") and part.endswith("`") and len(part) > 2:
            nodes.append({"type": "text", "text": part[1:-1],
                          "marks": [{"type": "code"}]})
        elif part.startswith("**") and part.endswith("**") and len(part) > 4:
            nodes.append({"type": "text", "text": part[2:-2],
                          "marks": [{"type": "strong"}]})
        elif _LINK.match(part):
            m = _LINK.match(part)
            nodes.append({"type": "text", "text": m.group(1),
                          "marks": [{"type": "link",
                                     "attrs": {"href": m.group(2)}}]})
        else:
            nodes.append({"type": "text", "text": part})
    return nodes or [{"type": "text", "text": ""}]


# ---------------------------------------------------------------- block nodes

def para(text):
    return {"type": "paragraph", "content": inline(text)}


def heading(text, level=3):
    return {"type": "heading", "attrs": {"level": level},
            "content": inline(text)}


def _list(kind, items):
    node = {
        "type": kind,
        "content": [{"type": "listItem", "content": [para(i)]} for i in items],
    }
    if kind == "orderedList":
        node["attrs"] = {"order": 1}
    return node


def code_block(text, lang="text"):
    return {"type": "codeBlock", "attrs": {"language": lang},
            "content": [{"type": "text", "text": text}]}


def task_list(items):
    return {
        "type": "taskList",
        "attrs": {"localId": _next_lid()},
        "content": [
            {"type": "taskItem",
             "attrs": {"localId": _next_lid(), "state": "TODO"},
             "content": inline(i)}
            for i in items
        ],
    }


def _cell(kind, val):
    body = val if isinstance(val, list) else [val]
    return {"type": kind, "attrs": {},
            "content": [para(v) for v in body] or [para("")]}


def table_node(t):
    if isinstance(t, list):  # bare list of rows, no header
        t = {"rows": t}
    rows = []
    if t.get("headers"):
        rows.append({"type": "tableRow",
                     "content": [_cell("tableHeader", h) for h in t["headers"]]})
    for r in t.get("rows", []):
        rows.append({"type": "tableRow",
                     "content": [_cell("tableCell", c) for c in r]})
    if not rows:
        raise SystemExit("table has no headers/rows")
    return {"type": "table",
            "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
            "content": rows}


_PANEL_TYPES = {"info", "note", "success", "warning", "error"}


def panel_node(val, ptype="info"):
    if ptype not in _PANEL_TYPES:
        raise SystemExit("panel type must be one of %s" % sorted(_PANEL_TYPES))
    body = val if isinstance(val, list) else [val]
    return {"type": "panel", "attrs": {"panelType": ptype},
            "content": [para(v) for v in body]}


def quote_node(val):
    body = val if isinstance(val, list) else [val]
    return {"type": "blockquote", "content": [para(v) for v in body]}


def block(b):
    if not isinstance(b, dict):
        return para(b)
    if "p" in b:
        return para(b["p"])
    if "h" in b:
        return heading(b["h"])
    if "ul" in b:
        return _list("bulletList", b["ul"])
    if "ol" in b:
        return _list("orderedList", b["ol"])
    if "code" in b:
        return code_block(b["code"], b.get("lang", "text"))
    if "tasks" in b:
        return task_list(b["tasks"])
    if "table" in b:
        return table_node(b["table"])
    if "panel" in b:
        return panel_node(b["panel"], b.get("type", "info"))
    if "quote" in b:
        return quote_node(b["quote"])
    if b.get("rule") or b.get("hr"):
        return {"type": "rule"}
    raise SystemExit("unknown block: %s" % json.dumps(b, ensure_ascii=False))


def build_doc(spec):
    content = []
    for key, title in SECTIONS:
        body = spec.get(key)
        if not body:
            continue
        content.append(heading(title, 2))
        if key == "pending":
            # a bare list of strings is shorthand for a checklist
            content.append(task_list(body) if isinstance(body[0], str)
                           else block(body[0]))
            for b in (body[1:] if not isinstance(body[0], str) else []):
                content.append(block(b))
        else:
            content.extend(block(b) for b in body)
    if not content:
        raise SystemExit("nothing to write: no section content found")
    return {"type": "doc", "version": 1, "content": content}


# ---------------------------------------------------------------- preview

def preview(spec, doc):
    def flat(n):
        if n.get("type") == "text":
            t = n["text"]
            marks = {m["type"]: m for m in n.get("marks", [])}
            if "link" in marks:
                t = "[%s](%s)" % (t, marks["link"]["attrs"]["href"])
            if "code" in marks:
                return "`%s`" % t
            if "strong" in marks:
                return "**%s**" % t
            return t
        return "".join(flat(c) for c in n.get("content", []) or [])

    if spec.get("ticket"):
        print("UPDATE %s (description will be OVERWRITTEN)" % spec["ticket"])
    else:
        print("CREATE %s / %s" % (spec.get("project", "GAMAPASS"),
                                  spec.get("issuetype", "Task")))
        print("SUMMARY: %s" % spec.get("summary", "(missing!)"))
    print("-" * 72)
    for n in doc["content"]:
        t = n["type"]
        if t == "heading":
            print("\n%s %s" % ("#" * n["attrs"]["level"], flat(n)))
        elif t == "paragraph":
            print(flat(n))
        elif t in ("bulletList", "orderedList"):
            for i, item in enumerate(n["content"], 1):
                mark = "-" if t == "bulletList" else "%d." % i
                print("  %s %s" % (mark, flat(item)))
        elif t == "taskList":
            for item in n["content"]:
                print("  [ ] %s" % flat(item))
        elif t == "codeBlock":
            print("```%s\n%s\n```" % (n["attrs"].get("language", ""), flat(n)))
        elif t == "table":
            for ri, row in enumerate(n["content"]):
                cells = [flat(c) for c in row["content"]]
                print("  | " + " | ".join(cells) + " |")
                if ri == 0 and row["content"][0]["type"] == "tableHeader":
                    print("  | " + " | ".join(["---"] * len(cells)) + " |")
        elif t == "panel":
            print("[%s] %s" % (n["attrs"].get("panelType", "info").upper(), flat(n)))
        elif t == "blockquote":
            print("> %s" % flat(n))
        elif t == "rule":
            print("---")
    print("-" * 72)


# ---------------------------------------------------------------- jira api

JIRA_VARS = ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")


def load_env_from_zshrc():
    # Non-interactive shells never source ~/.zshrc, where the JIRA_* vars are
    # exported — ask an interactive zsh for them. Marker prefixes keep the
    # values separable from any noise ~/.zshrc prints on startup.
    script = ";".join('printf "JV_%s=%%s\\n" "$%s"' % (k, k) for k in JIRA_VARS)
    try:
        out = subprocess.run(["zsh", "-ic", script], capture_output=True,
                             text=True, timeout=15).stdout
    except Exception:
        return
    for line in out.splitlines():
        for k in JIRA_VARS:
            prefix = "JV_%s=" % k
            if line.startswith(prefix) and line[len(prefix):]:
                os.environ.setdefault(k, line[len(prefix):])


def env():
    if not all(os.environ.get(k) for k in JIRA_VARS):
        load_env_from_zshrc()
    missing = [k for k in JIRA_VARS if not os.environ.get(k)]
    if missing:
        raise SystemExit("missing env var: %s (export it in ~/.zshrc or ~/.zshenv)"
                         % ", ".join(missing))
    base = os.environ["JIRA_BASE_URL"].rstrip("/")
    auth = base64.b64encode(
        ("%s:%s" % (os.environ["JIRA_EMAIL"],
                    os.environ["JIRA_API_TOKEN"])).encode()).decode()
    return base, auth


def call(method, path, auth, base, body=None):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Authorization": "Basic " + auth,
                 "Content-Type": "application/json",
                 "Accept": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        print("HTTP %s on %s %s" % (e.code, method, path), file=sys.stderr)
        print(e.read().decode("utf-8"), file=sys.stderr)
        raise SystemExit(1)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    dry = "--dry-run" in sys.argv
    if not args:
        raise SystemExit(__doc__)

    with open(args[0], encoding="utf-8") as f:
        spec = json.load(f)

    missing = [k for k in ("background", "implementation", "impact")
               if not spec.get(k)]
    if missing:
        raise SystemExit("required section(s) missing: %s "
                         "(骨架三段皆為必填)" % ", ".join(missing))

    doc = build_doc(spec)
    preview(spec, doc)
    if dry:
        print("dry run — nothing sent")
        return

    base, auth = env()
    if spec.get("ticket"):
        fields = {"description": doc}
        if spec.get("summary"):  # optional on update — omit to keep the title
            fields["summary"] = spec["summary"]
        call("PUT", "/rest/api/3/issue/" + spec["ticket"], auth, base,
             {"fields": fields})
        key = spec["ticket"]
        print("UPDATED:", key)
    else:
        if not spec.get("summary"):
            raise SystemExit("create requires \"summary\"")
        me = call("GET", "/rest/api/3/myself", auth, base)
        out = call("POST", "/rest/api/3/issue", auth, base, {"fields": {
            "project": {"key": spec.get("project", "GAMAPASS")},
            "issuetype": {"name": spec.get("issuetype", "Task")},
            "reporter": {"id": me["accountId"]},
            "summary": spec["summary"],
            "description": doc,
        }})
        key = out["key"]
        print("CREATED:", key)
    print("URL:", base + "/browse/" + key)


if __name__ == "__main__":
    main()

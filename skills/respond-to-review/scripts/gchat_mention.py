#!/usr/bin/env python3
"""Tag one GitLab user in an MR's Google Chat thread.

Usage (run from the MR's repo checkout, whose .env holds the webhook and GCHAT_USER_* lines):
  gchat_mention.py --mr 483 --user reverchen --text "gama-api-gateway !483 的 review 已逐點回覆：<link>"           # dry run
  gchat_mention.py --mr 483 --user reverchen --text "..." --send

Resolution, all of which must hold or nothing is sent:
  - .env maps GCHAT_USER_<user> to users/<digits>, and no other username maps to the same ID
  - the MR has a "gchat-thread:" note, and its space is the webhook's space
Exit codes: 0 ok (dry run printed / sent), 2 bad input or env, 3 NOT SURE (ask the user), 4 send failed.
Never prints the webhook URL.
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import urllib.parse
import urllib.request

# Google Chat over IPv6 hangs on this network (SYN_SENT forever): resolve IPv4 only.
_orig_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda host, port, family=0, *a, **kw: _orig_getaddrinfo(host, port, socket.AF_INET, *a, **kw)


def fail(code, msg):
    print(msg, file=sys.stderr)
    sys.exit(code)


def load_env(path):
    env = {}
    if not os.path.isfile(path):
        fail(2, f"no .env at {path}")
    with open(path) as f:
        for line in f:
            m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if m:
                env[m.group(1)] = m.group(2).strip("'\"")
    return env


def glab_json(path):
    out = subprocess.run(["glab", "api", path], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        fail(2, f"glab api {path} failed: {out.stderr.strip()[:200]}")
    return json.loads(out.stdout)


def project_path():
    url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True,
                         check=True).stdout.strip()
    # https://host/group/repo(.git) or git@host:group/repo(.git)
    m = re.match(r"^(?:\w+://[^/]+/|[^@]+@[^:]+:)(.+?)(?:\.git)?$", url)
    if not m:
        fail(2, f"cannot parse project from remote {url}")
    return m.group(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mr", required=True, help="MR IID in this checkout's project")
    ap.add_argument("--user", required=True, help="GitLab username to tag (the comment author)")
    ap.add_argument("--text", required=True, help="message after the mention; include the GitLab note link")
    ap.add_argument("--send", action="store_true", help="post it; without this only the resolution is printed")
    args = ap.parse_args()

    env = load_env(os.path.join(os.getcwd(), ".env"))
    webhook = env.get("GOOGLE_CHAT_WEBHOOK_URL", "")
    if not webhook:
        fail(2, "GOOGLE_CHAT_WEBHOOK_URL missing in .env")

    # Identity: exact username key, well-formed ID, ID not shared with another username.
    key = f"GCHAT_USER_{args.user}"
    raw = env.get(key, "")
    if not raw:
        known = sorted(k.removeprefix("GCHAT_USER_") for k in env if k.startswith("GCHAT_USER_"))
        fail(3, f"NOT SURE: no {key} in .env (mapped: {', '.join(known) or 'none'}) — ask the user who this is")
    chat_id = "users/" + raw.removeprefix("users/").removeprefix("user/")
    if not re.fullmatch(r"users/\d+", chat_id):
        fail(3, f"NOT SURE: {key} is not users/<digits> — ask the user")
    owners = [k for k, v in env.items() if k.startswith("GCHAT_USER_") and
              "users/" + v.removeprefix("users/").removeprefix("user/") == chat_id]
    if len(owners) > 1:
        fail(3, f"NOT SURE: {chat_id} is mapped by {', '.join(owners)} — ask the user which is right")

    project = project_path()
    pq = urllib.parse.quote(project, safe="")
    gl_user = glab_json(f"users?username={urllib.parse.quote(args.user)}")
    if not gl_user:
        fail(3, f"NOT SURE: GitLab has no user {args.user} — ask the user")
    gl_name = gl_user[0].get("name", "")

    # Target: the MR's existing thread, in the webhook's space.
    mr = glab_json(f"projects/{pq}/merge_requests/{args.mr}")
    notes = glab_json(f"projects/{pq}/merge_requests/{args.mr}/notes?per_page=100&sort=asc")
    thread = next((n["body"].removeprefix("gchat-thread:").strip() for n in notes
                   if n["body"].startswith("gchat-thread:")), "")
    if not thread:
        fail(2, f"!{args.mr} has no gchat-thread note; nothing to reply into")
    hook_space = re.search(r"spaces/[A-Za-z0-9_-]+", webhook)
    if not hook_space or not thread.startswith(hook_space.group(0) + "/"):
        fail(2, f"thread {thread} is not in the webhook's space; wrong checkout?")

    message = f"<{chat_id}> {args.text}"
    print(f"project  : {project} !{args.mr} ({mr.get('title', '')[:60]})")
    print(f"thread   : {thread}")
    print(f"tag      : {args.user} ({gl_name}) -> {chat_id}")
    print(f"message  : {message}")
    if not args.send:
        print("dry run: nothing sent")
        return

    body = json.dumps({"text": message, "thread": {"name": thread}}).encode()
    req = urllib.request.Request(webhook + "&messageReplyOption=REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD", data=body,
                                 headers={"Content-Type": "application/json; charset=UTF-8"})
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    except Exception as e:  # noqa: BLE001 — report, never retry: a duplicate post cannot be recalled
        fail(4, f"send failed ({type(e).__name__}); do not retry blindly, check the thread first")
    got = resp.get("thread", {}).get("name", "")
    print(f"sent into {got}" + ("" if got == thread else "  (WARNING: landed in a different thread)"))


if __name__ == "__main__":
    main()

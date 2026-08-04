"""GitHub GraphQL fetch + derived numbers. Standard library only.

Two determinism traps live in here, both of which otherwise produce a nightly
stream of meaningless commits:

  1. The contribution window is pinned to whole UTC days. Left alone,
     contributionsCollection measures "the past year" from the moment of the
     request, so two runs minutes apart bucket days into different weeks and
     shift the sparkline by a fraction of a pixel.

  2. Repositories are filtered to privacy: PUBLIC. A personal token sees
     private repos and the workflow's token does not, so without this the
     language percentages disagree depending on who ran the script.
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.github.com/graphql"
WINDOW_DAYS = 365

CONTRIB_Q = """
query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){
    name login createdAt
    followers{totalCount}
    contributionsCollection(from:$from,to:$to){
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      contributionCalendar{
        totalContributions
        weeks{contributionDays{date contributionCount}}
      }
    }
  }
}"""

REPO_Q = """
query($login:String!,$cursor:String){
  user(login:$login){
    repositories(first:100,after:$cursor,ownerAffiliations:OWNER,privacy:PUBLIC,
                 isFork:false,orderBy:{field:STARGAZERS,direction:DESC}){
      totalCount
      pageInfo{hasNextPage endCursor}
      nodes{
        name stargazerCount forkCount
        primaryLanguage{name color}
        languages(first:12,orderBy:{field:SIZE,direction:DESC}){
          edges{size node{name color}}
        }
      }
    }
  }
}"""


def _post(query, variables, token):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={
            "Authorization": "bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": "profile-stats-generator",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit("GitHub API %s: %s" % (e.code, e.read().decode()[:400]))
    if "errors" in payload:
        raise SystemExit("GraphQL errors: %s" % json.dumps(payload["errors"])[:400])
    return payload["data"]


def window(today=None):
    """Whole UTC days: [today-364 00:00:00Z, today 23:59:59Z]."""
    today = today or datetime.now(timezone.utc).date()
    start = today - timedelta(days=WINDOW_DAYS - 1)
    return (
        start.strftime("%Y-%m-%dT00:00:00Z"),
        today.strftime("%Y-%m-%dT23:59:59Z"),
        today,
    )


def fetch(login, token, today=None):
    frm, to, today = window(today)
    user = _post(CONTRIB_Q, {"login": login, "from": frm, "to": to}, token)["user"]
    if user is None:
        raise SystemExit("no such user: %s" % login)

    nodes, cursor = [], None
    while True:
        repos = _post(REPO_Q, {"login": login, "cursor": cursor}, token)["user"]["repositories"]
        nodes.extend(repos["nodes"])
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]

    cc = user["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    days.sort(key=lambda d: d["date"])

    return {
        "login": user["login"],
        "name": user["name"] or user["login"],
        "created": user["createdAt"][:10],
        "followers": user["followers"]["totalCount"],
        "today": today.isoformat(),
        "from": frm[:10],
        "total": cc["contributionCalendar"]["totalContributions"],
        "commits": cc["totalCommitContributions"],
        "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"],
        "reviews": cc["totalPullRequestReviewContributions"],
        "days": [(d["date"], d["contributionCount"]) for d in days],
        "repo_count": repos["totalCount"],
        "stars": sum(n["stargazerCount"] for n in nodes),
        "forks": sum(n["forkCount"] for n in nodes),
        "repos": nodes,
    }


def weekly(days):
    """Sum daily counts into ISO weeks, oldest first.

    A line through sparse daily counts claims values that never existed; over
    weekly aggregates continuity is defensible.
    """
    out, bucket = [], []
    for date, n in days:
        bucket.append(n)
        if datetime.strptime(date, "%Y-%m-%d").weekday() == 6:   # Sunday closes the week
            out.append(sum(bucket))
            bucket = []
    if bucket:
        out.append(sum(bucket))
    return out


def streaks(days, today):
    """Current and longest run of consecutive days with >=1 contribution.

    Today counts as neutral rather than as a break: a streak is not over at
    09:00 just because nothing has been pushed yet.
    """
    best = cur = 0
    best_span = cur_span = None
    for date, n in days:
        if n > 0:
            cur += 1
            cur_span = (date if cur == 1 else cur_span[0], date)
            if cur > best:
                best, best_span = cur, cur_span
        elif date != today:
            cur, cur_span = 0, None
    return {
        "current": cur, "current_span": cur_span,
        "longest": best, "longest_span": best_span,
    }


def languages(repos, top=6):
    """Two honest readings of the same data: bytes written, and repos touched."""
    by_bytes, by_repo, colors = {}, {}, {}
    for r in repos:
        for e in r["languages"]["edges"]:
            name, size = e["node"]["name"], e["size"]
            by_bytes[name] = by_bytes.get(name, 0) + size
            colors.setdefault(name, e["node"]["color"] or None)
        p = r.get("primaryLanguage")
        if p:
            by_repo[p["name"]] = by_repo.get(p["name"], 0) + 1
            colors.setdefault(p["name"], p["color"] or None)

    total = sum(by_bytes.values()) or 1
    ranked = sorted(by_bytes.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    return {
        "bytes": [(n, v, 100.0 * v / total, colors.get(n)) for n, v in ranked],
        "repos": sorted(by_repo.items(), key=lambda kv: (-kv[1], kv[0]))[:top],
        "colors": colors,
        "total_bytes": total,
    }


def token():
    for k in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(k):
            return os.environ[k]
    raise SystemExit("set GITHUB_TOKEN (the workflow's built-in token is enough)")

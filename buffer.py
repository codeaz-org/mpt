"""Publish to TikTok through Buffer.

Buffer posts to TikTok with its own TikTok-approved app, so captions and hashtags go
out with the video and the post is public -- neither of which our own unaudited app
can do (its drafts carry no caption, and direct posting is limited to SELF_ONLY).

Buffer's public GraphQL API has no upload endpoint: VideoAssetInput takes a URL and
Buffer fetches it. The rendered mp4 only exists on the runner, so it is published as a
GitHub release asset first -- public repo, stable URL, and it stays out of git history.

Env:
  BUFFER_ACCESS_TOKEN   personal API key from publish.buffer.com/settings/api
  BUFFER_CHANNEL_ID_<NICHE>  which TikTok channel a niche posts to
  BUFFER_CHANNEL_ID     fallback for a single-channel setup
  BUFFER_CHANNEL_ID_IG_<NICHE>  the Instagram channel a niche posts Reels to; unset
                        means no Instagram for that niche (never guessed)
  BUFFER_CHANNEL_ID_LI_<NICHE>  the LinkedIn page a niche posts to; same rule
  BUFFER_MODE           shareNow (default, publishes at once), addToQueue, customScheduled
  BUFFER_DRAFT          set to 1 to stage posts as Buffer drafts instead of publishing
  GITHUB_TOKEN          for the release upload; Actions provides it automatically
  GITHUB_REPOSITORY     owner/repo; Actions provides it automatically
"""
import json, mimetypes, os, re, time
from pathlib import Path

import requests

GRAPHQL_URL = "https://api.buffer.com/graphql"
MEDIA_TAG = "autopilot-media"  # one rolling release holds every video asset
KEEP_ASSETS = 20


def log(msg): print(f"[buffer] {msg}", flush=True)


def enabled():
    return bool((os.environ.get("BUFFER_ACCESS_TOKEN") or "").strip())


# ---------- GraphQL ----------
def gql(query, variables=None):
    token = (os.environ.get("BUFFER_ACCESS_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("BUFFER_ACCESS_TOKEN not set")
    r = requests.post(
        GRAPHQL_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=90,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        raise RuntimeError("buffer: " + "; ".join(
            e.get("message", "?") for e in payload["errors"])[:300])
    return payload["data"]


def tiktok_channel(niche_id=None):
    """The TikTok channel id for a niche, and the organisation it belongs to.

    Each niche posts to its own channel, chosen by BUFFER_CHANNEL_ID_<NICHEID>; without
    one it falls back to BUFFER_CHANNEL_ID, then to the only TikTok channel on the
    account. Guessing would publish one niche's video to another niche's audience."""
    account = gql("{ account { organizations { id } } }")["account"]
    orgs = account.get("organizations") or []
    if not orgs:
        raise RuntimeError("buffer account has no organisation")
    org = orgs[0]["id"]
    forced = ""
    if niche_id:
        forced = (os.environ.get(f"BUFFER_CHANNEL_ID_{niche_id.upper()}") or "").strip()
    forced = forced or (os.environ.get("BUFFER_CHANNEL_ID") or "").strip()
    if forced:
        return forced, org
    channels = gql(
        "query($i: ChannelsInput!){ channels(input: $i){ id name service } }",
        {"i": {"organizationId": org}},
    )["channels"]
    tiktok = [c for c in channels if (c.get("service") or "").lower() == "tiktok"]
    if not tiktok:
        raise RuntimeError("no TikTok channel connected in Buffer "
                           f"(found: {[c.get('service') for c in channels]})")
    if len(tiktok) > 1 and niche_id:
        raise RuntimeError(
            f"{len(tiktok)} TikTok channels connected; set BUFFER_CHANNEL_ID_{niche_id.upper()} "
            "so each niche posts to its own: "
            + ", ".join(f"{c.get('name')}={c['id']}" for c in tiktok))
    log(f"channel {tiktok[0].get('name', 'tiktok')} ({tiktok[0]['id']})")
    return tiktok[0]["id"], org


# ---------- media hosting ----------
def _gh_api(method, url, token, **kw):
    r = requests.request(method, url, timeout=180, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        **kw.pop("headers", {}),
    }, **kw)
    if not r.ok:
        raise RuntimeError(f"github {method} {url.split('/')[-1]}: {r.status_code} {r.text[:200]}")
    return r


def _release(repo, token):
    """The rolling release that holds video assets, created on first use."""
    base = f"https://api.github.com/repos/{repo}"
    r = requests.get(f"{base}/releases/tags/{MEDIA_TAG}", timeout=60, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    if r.status_code == 200:
        return r.json()
    return _gh_api("POST", f"{base}/releases", token, json={
        "tag_name": MEDIA_TAG,
        "name": "Autopilot media",
        "body": "Rendered videos hosted for Buffer to fetch. Managed automatically.",
        "prerelease": True,
    }).json()


def _prune(repo, token, release, keep=KEEP_ASSETS):
    assets = sorted(release.get("assets", []), key=lambda a: a.get("created_at", ""))
    for asset in assets[:-keep] if len(assets) > keep else []:
        try:
            _gh_api("DELETE", f"https://api.github.com/repos/{repo}/releases/assets/{asset['id']}", token)
        except Exception as e:
            log(f"could not delete old asset {asset.get('name')}: {str(e)[:80]}")


_hosted = {}  # local path -> public URL, so TikTok and Instagram share one upload


def host_file(path, token=None, repo=None):
    """Upload a file as a release asset and return its public URL. A file already
    hosted in this run is not uploaded again."""
    key = str(Path(path).resolve())
    if key in _hosted:
        return _hosted[key]
    token = token or (os.environ.get("GITHUB_TOKEN") or "").strip()
    repo = repo or (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if not token or not repo:
        raise RuntimeError("GITHUB_TOKEN and GITHUB_REPOSITORY are needed to host the video")
    path = Path(path)
    release = _release(repo, token)
    name = f"{int(time.time())}-{path.name}".replace(" ", "_")
    upload = release["upload_url"].split("{")[0]
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        asset = _gh_api("POST", f"{upload}?name={name}", token,
                        headers={"Content-Type": ctype}, data=f).json()
    _prune(repo, token, release)
    log(f"hosted {name} ({path.stat().st_size // 1024}KB)")
    _hosted[key] = asset["browser_download_url"]
    return _hosted[key]


# ---------- publishing ----------
# createPost returns a union: PostActionSuccess or one of several error types, all of
# which carry a message. Asking for the message on the interface keeps every failure
# legible instead of surfacing as a missing field.
CREATE_POST = """
mutation($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess { post { id dueAt schedulingType channelService } }
    ... on NotFoundError { message }
    ... on UnauthorizedError { message }
    ... on UnexpectedError { message }
    ... on RestProxyError { message }
    ... on LimitReachedError { message }
    ... on InvalidInputError { message }
  }
}
"""


def _create_post(channel_id, caption, assets, title, metadata=None):
    # shareNow publishes immediately. addToQueue drops the post into Buffer's posting
    # schedule instead, which with a backlog meant videos sat unpublished for days.
    mode = (os.environ.get("BUFFER_MODE") or "shareNow").strip()
    draft = (os.environ.get("BUFFER_DRAFT") or "").strip().lower() in ("1", "true", "yes")
    data = gql(CREATE_POST, {"input": {
        "channelId": channel_id,
        "text": caption,
        "assets": assets,
        "mode": mode,
        "schedulingType": "automatic",   # Buffer publishes it; no phone reminder
        "needsApproval": False,
        "saveToDraft": draft,
        "source": "mpt-autopilot",
        "metadata": metadata or {"tiktok": {"title": (title or caption)[:150]}},
    }})
    result = data["createPost"]
    if result.get("__typename") != "PostActionSuccess":
        raise RuntimeError(f"buffer rejected the post ({result.get('__typename')}): "
                           f"{result.get('message', 'no message')}")
    post = result.get("post") or {}
    log(f"queued post {post.get('id')} ({mode}{', draft' if draft else ''}"
        + (f", due {post['dueAt']}" if post.get("dueAt") else "") + ")")
    return post.get("id")


def publish(video_path, caption, title=None, video_url=None, niche_id=None):
    """Queue the video on the connected TikTok channel with its caption.

    No thumbnail is sent: Buffer rejects the whole post with "Video thumbnailUrl is not
    supported: social networks do not accept custom video thumbnail images". TikTok
    picks the cover frame itself."""
    channel_id, _ = tiktok_channel(niche_id)
    if not video_url:
        video_url = host_file(video_path)
    return _create_post(channel_id, caption, [{"video": {"url": video_url}}], title)


def instagram_channel(niche_id):
    """The Instagram channel id a niche posts Reels to, or None. Explicit only."""
    return (os.environ.get(f"BUFFER_CHANNEL_ID_IG_{niche_id.upper()}") or "").strip() or None


def publish_instagram(video_path, caption, channel_id, video_url=None):
    """Post the video as an Instagram Reel, shared to the feed too. The narration
    and script are AI-generated, so the post says so: Instagram labels undisclosed
    AI content itself, and disclosing is the honest default."""
    if not video_url:
        video_url = host_file(video_path)
    return _create_post(
        channel_id, caption[:2200], [{"video": {"url": video_url}}], None,
        metadata={"instagram": {"type": "reel", "shouldShareToFeed": True,
                                "isAiGenerated": True}})


def linkedin_channel(niche_id):
    """The LinkedIn page channel id a niche posts to, or None. Explicit only."""
    return (os.environ.get(f"BUFFER_CHANNEL_ID_LI_{niche_id.upper()}") or "").strip() or None


_URL = re.compile(r"https?://\S+")


def linkedin_text(caption, max_tags=3):
    """LinkedIn reads differently from TikTok: a wall of hashtags looks like spam, and
    a link in the post body is widely reported to cut reach. Keep three tags and move
    the link out; the caller posts it as the first comment. Returns (text, link)."""
    links = _URL.findall(caption)
    text = _URL.sub("", caption)
    tags = re.findall(r"#\w+", text)
    text = re.sub(r"\s*#\w+", "", text)
    text = re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text)).strip()
    text = re.sub(r":\s*$", "", text, flags=re.M).strip()
    if tags:
        text += "\n\n" + " ".join(tags[:max_tags])
    return text[:3000], (links[0] if links else None)


def publish_linkedin(video_path, caption, channel_id, video_url=None):
    """Post the video natively to a LinkedIn page. Any link goes on its own line at the
    end of the post: putting it in the first comment is the reach-friendly option, but
    Buffer rejects firstComment on the free plan ("LinkedIn first comment requires a
    paid plan"), which cost the first App Rescue episode its LinkedIn post. Set
    BUFFER_LINKEDIN_FIRST_COMMENT=1 once the plan allows it."""
    if not video_url:
        video_url = host_file(video_path)
    text, link = linkedin_text(caption)
    meta = {}
    if link and (os.environ.get("BUFFER_LINKEDIN_FIRST_COMMENT") or "").strip() == "1":
        meta["firstComment"] = link
    elif link:
        body, tags = (text.rsplit("\n\n", 1) + [""])[:2] if "#" in text.rsplit("\n\n", 1)[-1] else (text, "")
        text = f"{body}\n\n{link}" + (f"\n\n{tags}" if tags else "")
    return _create_post(channel_id, text, [{"video": {"url": video_url}}], None,
                        metadata={"linkedin": meta})


def channels():
    """Every connected channel, for finding the ids the env vars need."""
    org = gql("{ account { organizations { id } } }")["account"]["organizations"][0]["id"]
    return gql("query($i: ChannelsInput!){ channels(input: $i){ id name service } }",
               {"i": {"organizationId": org}})["channels"]


def delete(post_id):
    return gql("""mutation($input: DeletePostInput!){ deletePost(input: $input){
                    __typename ... on VoidMutationError { message } } }""",
               {"input": {"id": post_id}})


if __name__ == "__main__":
    # python3 buffer.py            account check
    # python3 buffer.py channels   list channel ids (for BUFFER_CHANNEL_ID_IG_<NICHE>)
    import sys
    if sys.argv[1:] == ["channels"]:
        for c in channels():
            print(f"{c['service']:<12} {c['name']:<30} {c['id']}")
    else:
        print(json.dumps(gql("{ account { email organizations { id name } } }"), indent=1))

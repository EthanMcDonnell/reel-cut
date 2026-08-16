"""Build the comment-automation spec a slug posts with.

Every automation this project generates is the same funnel: comment the CTA
keyword, get asked to follow, reply DONE, receive the resources. Only two things
differ between videos -- the **keyword** and the **reward** -- so those two are
the only things ``assets/<slug>/automation.json`` holds:

    {"trigger_keywords": ["S3"], "follower_message": "S3 resource:\\nhttps://..."}

Everything else is constant and lives here, in one place. A pack rename in
social-cockpit is then a single edit rather than one per video, and a video
cannot quietly drift off the standard because there is nothing per-video to
drift.

The constants are checked against the cockpit rather than trusted: see
``validate_automation.py``, which asks ``/api/automation-reply-functions`` and
``/api/follow-dm-functions`` whether they still exist.
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent

TEMPLATE_TYPE = "comment_to_follow_dm"
# Named packs in social-cockpit. `comment_reply_fn` writes the public reply under
# the comment; `dm_pack` generates the DM opener and the follow-up nudge. Both
# are verified live by validate_automation.py.
COMMENT_REPLY_FN = "casual_replies"
DM_PACK = "casual"
# What the commenter replies in the DM to claim the reward.
CONFIRM_KEYWORD = "DONE"
# Substituted for {{resource}} in the pack copy -- "…reply DONE to get the resources".
RESOURCE = "resources"
# A follow check that itself errors re-prompts rather than rewarding. Matches
# every flow built by hand on this account.
ON_CHECK_ERROR = "follow_prompt"


def spec_path(slug):
    return ROOT / "assets" / slug / "automation.json"


def load(slug):
    """The raw per-video file, or None when the slug posts without an automation."""
    path = spec_path(slug)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def build(slug, raw):
    """Expand the two per-video fields into the full spec the cockpit accepts.

    ``key`` is the slug, always: every hook of a video is a variation of the same
    post and has to join one flow, created by whichever hook publishes first and
    appended to by the rest.
    """
    return {
        "key": slug,
        "trigger_keywords": raw.get("trigger_keywords", []),
        "template_type": TEMPLATE_TYPE,
        "config": {
            "comment_reply_fn": COMMENT_REPLY_FN,
            "comment_replies": [],
            "dm_pack": DM_PACK,
            "confirm_keyword": CONFIRM_KEYWORD,
            "resource": RESOURCE,
            "on_check_error": ON_CHECK_ERROR,
            "follower_message": raw.get("follower_message", ""),
        },
    }


def for_slug(slug):
    """The full spec for a slug, or None when it has no automation.json."""
    raw = load(slug)
    return None if raw is None else build(slug, raw)

"""Local unWISE archive previews for the Vetting app."""

import json
import os
import re
from pathlib import Path

CACHE = Path(os.environ.get(
    "MOCA_LOCAL_UNWISE_CACHE", str(Path.home() / "Documents/Vetting/unWISE/GIFs")
))
IMAGE_SIZE = 50
FRAME_DELAY_MS = 500
PROFILE = "unwise-neo1-neo5-neo11-50as-v1"
PREVIEW_ID = re.compile(r"(?:moshpit-)?[1-9][0-9]{0,17}")


def cached_preview(oid, ra=None, dec=None):
    """Look up a complete entry and optionally check its sky position."""
    name = str(oid)
    if not PREVIEW_ID.fullmatch(name):
        return None
    gif = CACHE / (name + ".gif")
    try:
        data = json.loads(gif.with_suffix(".json").read_text())
        if data["profile"] != PROFILE or not gif.is_file():
            return None
        if ra is not None and (abs(float(ra) - data["ra"]) > 1e-7 or
                               abs(float(dec) - data["dec"]) > 1e-7):
            return None
    except (OSError, ValueError, TypeError, KeyError):
        return None
    return gif, data


def fix_online_cutout_script(script):
    """Release the WiseView UI and report a request that exhausted its retries."""
    # WiseView retries 504s but leaves both panels blocked on permanent errors.
    anchor = 'datatype: "jsonp",'
    if anchor not in script:
        return script
    script = script.replace(anchor, 'dataType: "json", timeout: 22000,', 1)
    error = re.compile(
        r'if \(xhr\.status != 504 \|\| this\.retries-- <= 0\) \{\s*'
        r'return;\s*\}\s*jQuery\.ajax\(this\);'
    )
    return error.sub(
        """if (xhr.status === 504 && this.retries-- > 0) {
            jQuery.ajax(this);
            return;
        }
        that.unblock();
        const note = document.getElementById("wiseview-request-error");
        if (note) note.remove();
        const error = document.createElement("p");
        error.id = "wiseview-request-error";
        error.textContent = "WiseView could not load this animation. Try again or change a setting to retry.";
        const retry = document.createElement("button");
        retry.textContent = "Retry WiseView";
        retry.onclick = () => { error.remove(); that.restart(); };
        error.append(" ", retry);
        document.getElementById("image").append(error);
        if (window.parent !== window)
            window.parent.postMessage({kind:"wiseview-cutout-failed", frame:
              new URLSearchParams(location.search).get("frame")}, "*");""",
        script.replace("retries: 6,", "retries: 1,", 1).replace(
            "that.__get_cutouts(meta);",
            'document.getElementById("wiseview-request-error")?.remove();\n\t\tthat.__get_cutouts(meta);',
            1,
        ),
        count=1,
    )

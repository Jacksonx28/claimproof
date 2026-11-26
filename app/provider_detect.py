"""Provider auto-detection for the DownProof checker.

Many solo founders and small teams do not know which provider a service
runs on, even though the provider decides which SLA credit table applies.
This module makes an honest best guess from two signals, in order:

1. The URL itself. Hosted addresses give the provider away, for example
   ``*.s3.amazonaws.com`` (AWS S3), ``*.azurewebsites.net`` (Azure),
   ``*.run.app`` (Google Cloud) or ``*.pages.dev`` (Cloudflare).
2. The site's response headers. Servers identify themselves: a ``cf-ray``
   header means Cloudflare, ``x-amz-*`` means AWS, ``x-azure-*`` / ``x-ms-*``
   means Azure, ``x-goog-*`` means Google.

The result is a suggestion for the form, never a lock: a site can sit
behind Cloudflare while the bill is with AWS, and detection can name the
company but not always the exact product. The caller shows the guess with
its source so the user can override it in one tap. When nothing matches,
this returns None and the user picks manually, exactly as before.

Stdlib only, like the rest of DownProof. The provider keys returned are
the same keys used by app/sla_credits.py TABLES and the web form.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from urllib.parse import urlparse

# Host suffix -> (provider key, what the address tells us). Order matters:
# the most specific suffixes come first, and detect_provider checks the
# AWS S3 host shapes before this list's generic amazonaws.com entry.
_HOST_SUFFIXES = [
    (".s3.amazonaws.com", "aws-s3", "an AWS S3 address"),
    (".digitaloceanspaces.com", "digitalocean-spaces", "a DigitalOcean Spaces address"),
    (".blob.core.windows.net", "azure-vm", "an Azure storage address"),
    (".azurewebsites.net", "azure-vm", "an Azure App Service address"),
    (".cloudapp.azure.com", "azure-vm", "an Azure cloud service address"),
    (".cloudapp.net", "azure-vm", "an Azure cloud service address"),
    (".run.app", "gcp-compute", "a Google Cloud Run address"),
    (".appspot.com", "gcp-compute", "a Google App Engine address"),
    (".web.app", "gcp-compute", "a Firebase Hosting address"),
    (".firebaseapp.com", "gcp-compute", "a Firebase Hosting address"),
    (".workers.dev", "cloudflare-workers", "a Cloudflare Workers address"),
    (".pages.dev", "cloudflare-workers", "a Cloudflare Pages address"),
    (".cloudfront.net", "aws-ec2", "an AWS CloudFront address"),
    (".ondigitalocean.app", "digitalocean-spaces", "a DigitalOcean App Platform address"),
    (".amazonaws.com", "aws-ec2", "an AWS address"),
]


def _from_host(host: str):
    """Provider key + source label from the hostname alone, or None."""
    if host.endswith(".amazonaws.com") and (
        ".s3." in host or host.startswith("s3.") or host.startswith("s3-")
    ):
        return "aws-s3", "an AWS S3 address"
    for suffix, key, label in _HOST_SUFFIXES:
        if host.endswith(suffix):
            return key, label
    return None


def _from_headers(headers):
    """Provider key from response headers, or None.

    ``headers`` is any mapping (an email.message.Message from urllib works).
    """
    h = {str(k).lower(): str(v) for k, v in dict(headers).items()}
    server = h.get("server", "").lower()
    squashed = server.replace(" ", "")
    if "cf-ray" in h or "cf-cache-status" in h or "cloudflare" in server:
        return "cloudflare-workers"
    if "amazons3" in squashed:
        return "aws-s3"
    if "x-amz-cf-id" in h or "x-amz-id-2" in h or "x-amz-request-id" in h:
        return "aws-ec2"
    if "x-azure-ref" in h or "x-ms-request-id" in h or "x-ms-version" in h:
        return "azure-vm"
    if (
        "x-goog-generation" in h
        or "x-guploader-uploadid" in h
        or server in ("gws", "sffe", "esf")
    ):
        return "gcp-compute"
    return None


def detect_provider(url: str, headers=None) -> dict | None:
    """Best-guess provider for ``url`` (and its response ``headers``).

    Returns {"provider": <sla_credits key>, "source": <plain-language
    origin of the guess>} or None when no signal matches.
    """
    candidate = url if "://" in url else "https://" + url
    host = (urlparse(candidate).hostname or "").lower()
    if host:
        found = _from_host(host)
        if found is not None:
            key, label = found
            return {"provider": key, "source": f"the URL itself ({label})"}
    if headers:
        key = _from_headers(headers)
        if key is not None:
            return {"provider": key, "source": "the site's response headers"}
    return None


def detect_from_url(url: str, timeout_s: float = 5.0) -> dict | None:
    """Fetch ``url`` once, capture its headers, and detect the provider.

    A failed fetch still allows URL-pattern detection (a dead S3 address
    is still an S3 address), so fetch errors never raise.
    """
    candidate = url if url.startswith(("http://", "https://")) else "https://" + url
    headers = None
    req = urllib.request.Request(
        candidate, method="GET", headers={"User-Agent": "DownProof-Miner/0.1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            headers = resp.headers
            resp.read(512)  # prove the body flows, same discipline as the miner
    except urllib.error.HTTPError as e:
        headers = e.headers  # an error page still carries the server's headers
    except Exception:
        headers = None
    return detect_provider(candidate, headers)

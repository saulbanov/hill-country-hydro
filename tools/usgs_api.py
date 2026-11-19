"""The USGS Water Data API key and quota headers, read in one place.

Key-less requests share a small quota. From 2026-10-03 the Mac run got about 150 answers a
morning and HTTP 429 OVER_RATE_LIMIT for the rest. A free api.data.gov key
(https://api.waterdata.usgs.gov/signup/) raises that ceiling. The key rides the X-Api-Key
header and never the URL, because every collector saves its request URL verbatim in a
.meta.json. The daily Mac run puts it in USGS_API_KEY from the login keychain.
"""
import os

REFUSED = (403, 429)  # the provider declined the request; the body is a refusal, never a reading
RATE_HEADERS = ('X-RateLimit-Limit', 'X-RateLimit-Remaining', 'Retry-After')

def has_key():
    return bool(os.environ.get('USGS_API_KEY', '').strip())

def headers(user_agent):
    h = {'User-Agent': user_agent}
    if has_key(): h['X-Api-Key'] = os.environ['USGS_API_KEY'].strip()
    return h

def rate_limit(response_headers):
    """The provider's own statement of the quota, kept beside each response when it sends one."""
    return {k: response_headers.get(k) for k in RATE_HEADERS if response_headers.get(k) is not None}

"""Strict network and integration constants for the independent read-only client."""

DOMAIN = "atlantic_cozytouch"
API_ORIGIN = "https://apis.groupe-atlantic.com"
TOKEN_PATH = "/users/token"
READ_PATH = "/magellan/cozytouch/setupviewv2"

# Public application client identifier used by the Atlantic mobile protocol.
# This is NOT a user's password or access token.
ATLANTIC_PUBLIC_CLIENT_ID = (
    "Q3RfMUpWeVRtSUxYOEllZkE3YVVOQmpGblpVYToyRWNORHpfZHkzNDJVSnFvMlo3cFNKTnZVdjBh"
)

POLL_SECONDS = 180
HTTP_TIMEOUT_SECONDS = 15

# Explicit user opt-in; no automatic cross-logical-device COP pairing.
OPT_EXPERIMENTAL_CROSS_DEVICE_COP = "experimental_cross_device_cop"

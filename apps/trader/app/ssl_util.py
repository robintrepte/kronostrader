"""TLS helpers for Windows networks that intercept HTTPS (corporate proxies)."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def configure_ssl(*, verify: bool = True) -> None:
    """
    Point Python/requests at a usable CA bundle.

    - Prefer certifi
    - Optionally install/use OS trust store via pip-system-certs
    - If verify=False (dev-only), disable verification for requests/urllib3
    """
    try:
        import certifi

        ca = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", ca)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca)
        os.environ.setdefault("CURL_CA_BUNDLE", ca)
    except Exception:
        logger.warning("certifi not available")

    try:
        import pip_system_certs  # noqa: F401 — patches certifi to use OS store
    except Exception:
        pass

    if verify:
        return

    logger.warning(
        "SSL verification DISABLED (SSL_VERIFY=false). "
        "Use only for local testing behind TLS interception."
    )
    os.environ["PYTHONHTTPSVERIFY"] = "0"
    try:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

    try:
        import requests
        from requests.adapters import HTTPAdapter

        _orig_init = HTTPAdapter.__init__
        _orig_send = HTTPAdapter.send

        def _init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            _orig_init(self, *args, **kwargs)

        def _send(self, request, **kwargs):  # type: ignore[no-untyped-def]
            kwargs["verify"] = False
            return _orig_send(self, request, **kwargs)

        HTTPAdapter.__init__ = _init  # type: ignore[method-assign]
        HTTPAdapter.send = _send  # type: ignore[method-assign]

        # Also default Session.verify
        _session_init = requests.Session.__init__

        def _session_init_wrap(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            _session_init(self, *args, **kwargs)
            self.verify = False

        requests.Session.__init__ = _session_init_wrap  # type: ignore[method-assign]
    except Exception:
        logger.exception("Failed to disable requests SSL verify")

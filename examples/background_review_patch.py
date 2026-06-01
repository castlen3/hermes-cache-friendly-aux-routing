"""
Illustrative patch for Hermes background_review.py
====================================================

⚠️  IMPORTANT: This is an ILLUSTRATIVE EXAMPLE ONLY.
    It is NOT guaranteed to run as-is on any specific Hermes version.
    File paths, class structures, and function signatures vary between releases.
    Use this as a reference for writing your own patch.

Purpose
-------
By default, background_review inherits the main conversation's provider,
model, and endpoint. This patch makes it check the ``auxiliary`` section
of config.yaml first, so it can be routed to a separate (cheaper) model.

Concept
-------
Read ``auxiliary.background_review`` from config.yaml.
If found, use it. Otherwise, fall back to the main runtime.
"""

# -----------------------------------------------------------
# BEFORE (simplified) — background_review inherits main runtime
# -----------------------------------------------------------

_review_provider = agent.provider
_review_model = agent.model
_review_base_url = _parent_runtime.get("base_url") or None
_review_api_key = _parent_runtime.get("api_key") or None


# -----------------------------------------------------------
# AFTER (patched) — checks auxiliary config first
# -----------------------------------------------------------

_review_provider = agent.provider
_review_model = agent.model
_review_base_url = _parent_runtime.get("base_url") or None
_review_api_key = _parent_runtime.get("api_key") or None

try:
    from agent.auxiliary_client import _get_auxiliary_task_config

    cfg = _get_auxiliary_task_config("background_review")
    if cfg:
        _review_provider = cfg.get("provider") or _review_provider
        _review_model = cfg.get("model") or _review_model
        _review_base_url = cfg.get("base_url") or _review_base_url
        _review_api_key = cfg.get("api_key") or _review_api_key
except Exception:
    logger.debug(
        "background_review: no auxiliary config; inheriting main runtime"
    )

logger.info(
    "background_review routing: provider=%s model=%s base_url=%s",
    _review_provider,
    _review_model,
    _review_base_url,
)

# The rest of background_review uses _review_provider, _review_model,
# _review_base_url, and _review_api_key for its API calls instead of
# the main conversation's parameters.


# -----------------------------------------------------------
# Integration guide
# -----------------------------------------------------------
#
# 1. Find where provider/model are set from the main agent runtime
#    in your version of background_review.py.
#
# 2. Insert the try/except block above to check auxiliary config
#    before falling back to main runtime values.
#
# 3. Verify by checking agent.log:
#    Expected:
#      background_review routing: provider=aux-model model=small-model ...
#    Not:
#      background_review routing: provider=main-model model=expensive-model ...
#
# 4. If _get_auxiliary_task_config is not available in your version,
#    use the fallback implementation below.


# -----------------------------------------------------------
# Minimal fallback — if _get_auxiliary_task_config doesn't exist
# -----------------------------------------------------------

def _get_auxiliary_task_config(task_name):
    """
    Read auxiliary task config from config.yaml.

    Returns a dict with provider/model/base_url/api_key keys,
    or an empty dict if not configured.
    """
    import yaml
    from pathlib import Path

    config_path = Path.home() / ".hermes" / "config.yaml"
    if not config_path.exists():
        return {}

    with open(config_path) as f:
        config = yaml.safe_load(f)

    return config.get("auxiliary", {}).get(task_name, {})

"""Hermes LCM Plugin — Lossless Context Management.

Replaces the built-in ContextCompressor with a DAG-based context engine
that persists every message and provides structured retrieval tools.

Based on the LCM paper by Ehrlich & Blackman (Voltropy PBC, Feb 2026).
"""

import logging
import os

logger = logging.getLogger(__name__)


def _env_flag_enabled(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def register(ctx):
    """Plugin entry point — register the LCM context engine."""
    from .config import LCMConfig
    from .engine import LCMEngine

    config = LCMConfig.from_env()

    # Resolve hermes_home for profile-scoped storage
    hermes_home = ""
    try:
        from hermes_cli.config import get_hermes_home
        hermes_home = str(get_hermes_home())
    except Exception:
        import os
        hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))

    engine = LCMEngine(config=config, hermes_home=hermes_home)

    # Register as the context engine (replaces ContextCompressor)
    ctx.register_context_engine(engine)

    # --- /lcm slash command registration ---
    # Upstream requires LCM_ENABLE_SLASH_COMMAND=1 AND a proper ctx.register_command.
    # The Hermes _EngineCollector loader does NOT provide register_command, so the
    # upstream path always falls through. Our patch adds a fallback that injects
    # directly into the PluginManager singleton.
    register_command = getattr(ctx, "register_command", None)
    slash_enabled = _env_flag_enabled("LCM_ENABLE_SLASH_COMMAND", default=False)
    _lcm_registered = False

    if callable(register_command) and slash_enabled:
        from .command import handle_lcm_command
        register_command(
            "lcm",
            lambda raw_args: handle_lcm_command(raw_args, engine),
            description="LCM status and diagnostics",
        )
        _lcm_registered = True

    # NachoTek patch: fallback when _EngineCollector lacks register_command
    if not _lcm_registered and slash_enabled:
        try:
            from hermes_cli.plugins import get_plugin_manager
            from .command import handle_lcm_command
            _mgr = get_plugin_manager()
            _mgr._plugin_commands["lcm"] = {
                "handler": lambda raw_args: handle_lcm_command(raw_args, engine),
                "description": "LCM status and diagnostics",
                "plugin": "lcm",
            }
            _lcm_registered = True
            logger.info("LCM /lcm command registered via PluginManager fallback")
        except Exception as _fallback_err:
            logger.warning("LCM PluginManager fallback failed: %s", _fallback_err)

    if not _lcm_registered and not slash_enabled:
        logger.info("LCM slash command disabled (set LCM_ENABLE_SLASH_COMMAND=1 to enable /lcm)")
    elif not _lcm_registered:
        logger.warning("LCM slash command registration failed on all paths")

    logger.info("LCM plugin loaded — lossless context management active")

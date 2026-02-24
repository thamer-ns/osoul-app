# ai_engine_core package
# Lightweight exports with lazy imports to reduce Streamlit rerun overhead.
from .config import AI_ENGINE_NAME, AI_ENGINE_VERSION

__all__ = [
    'AI_ENGINE_NAME', 'AI_ENGINE_VERSION',
    'generate_ai_report',
    'calculate_portfolio_risk_score', 'generate_portfolio_recommendation',
    'add_user_rule', 'list_user_rules', 'toggle_user_rule', 'delete_user_rule',
    'list_recent_ai_signals', 'record_signal_outcome', 'learn_from_outcomes',
]


def generate_ai_report(*args, **kwargs):
    from .reporting import generate_ai_report as _impl
    return _impl(*args, **kwargs)


def calculate_portfolio_risk_score(*args, **kwargs):
    from .portfolio import calculate_portfolio_risk_score as _impl
    return _impl(*args, **kwargs)


def generate_portfolio_recommendation(*args, **kwargs):
    from .portfolio import generate_portfolio_recommendation as _impl
    return _impl(*args, **kwargs)


def add_user_rule(*args, **kwargs):
    from .user_rules import add_user_rule as _impl
    return _impl(*args, **kwargs)


def list_user_rules(*args, **kwargs):
    from .user_rules import list_user_rules as _impl
    return _impl(*args, **kwargs)


def toggle_user_rule(*args, **kwargs):
    from .user_rules import toggle_user_rule as _impl
    return _impl(*args, **kwargs)


def delete_user_rule(*args, **kwargs):
    from .user_rules import delete_user_rule as _impl
    return _impl(*args, **kwargs)


def list_recent_ai_signals(*args, **kwargs):
    from .logging_learning import list_recent_ai_signals as _impl
    return _impl(*args, **kwargs)


def record_signal_outcome(*args, **kwargs):
    from .logging_learning import record_signal_outcome as _impl
    return _impl(*args, **kwargs)


def learn_from_outcomes(*args, **kwargs):
    from .logging_learning import learn_from_outcomes as _impl
    return _impl(*args, **kwargs)


def self_test():
    return {
        'package': 'ai_engine_core',
        'engine': AI_ENGINE_NAME,
        'version': AI_ENGINE_VERSION,
        'exports_ready': True,
    }

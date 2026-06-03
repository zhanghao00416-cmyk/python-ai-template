from app.core.di import container


def get_settings():
    from app.core.config import get_settings
    return get_settings()


def get_health_status():
    from app.bootstrap import get_health_status
    return get_health_status()
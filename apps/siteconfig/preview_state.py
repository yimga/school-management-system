import threading


PREVIEW_MODE_SESSION_KEY = "admin_preview_mode"
ACT_AS_ROLE_SESSION_KEY = "preview_act_as_role"


class PreviewState(threading.local):
    def __init__(self):
        super().__init__()
        self.enabled = False


_state = PreviewState()


def set_preview_mode(enabled: bool) -> None:
    _state.enabled = bool(enabled)


def is_preview_mode() -> bool:
    return getattr(_state, "enabled", False)


def reset_preview_mode() -> None:
    _state.enabled = False

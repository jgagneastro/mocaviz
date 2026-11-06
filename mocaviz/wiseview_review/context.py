"""Per-request database identity, including explicitly copied worker contexts."""
from contextvars import ContextVar, copy_context
from threading import Thread

AUTH = ContextVar('wiseview_mocadb_auth')


def current_auth():
    try:
        return AUTH.get()
    except LookupError:
        raise PermissionError('Private MOCAdb authentication is required.') from None


def start_thread(target, *args):
    context = copy_context()
    thread = Thread(target=context.run, args=(target, *args), daemon=True)
    thread.start()
    return thread

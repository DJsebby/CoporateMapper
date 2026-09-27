"""Small, dependency-free error boundary for executable scripts.

Library functions keep raising exceptions; only command entrypoints translate
failures into concise messages and process exit codes. Never echo exception
messages: network/database errors can contain credentials or response bodies.
"""

from contextlib import contextmanager
from functools import wraps
import json
import os
import re
import sys


class CommandError(ValueError):
    """An explicitly safe, actionable message suitable for terminal output."""


def error_message(error, *, hint=None):
    if isinstance(error, CommandError):
        return str(error)
    if isinstance(error, ImportError):
        name = (getattr(error, 'name', '') or '').split('.')[0]
        if name == 'playwright':
            return 'Browser dependency unavailable. Install playwright and run python -m playwright install chromium.'
        dependency = f' ({name})' if re.fullmatch(r'[A-Za-z0-9_]+', name) else ''
        return f'Python dependency unavailable{dependency}. Run python -m pip install -r requirements.txt in your project environment.'
    if isinstance(error, FileNotFoundError):
        return 'Required file or executable was not found. Check the input path and installed tools.'
    if isinstance(error, PermissionError):
        return 'Permission denied. Check access to the input and output files.'
    if isinstance(error, json.JSONDecodeError) or isinstance(error, UnicodeError):
        return 'The service returned an unreadable response. Try again later.'
    if isinstance(error, (TimeoutError, ConnectionError)) or any(
        word in type(error).__name__.lower() for word in ('timeout', 'connection', 'serviceunavailable', 'sessionexpired')
    ):
        return hint or 'Connection failed or timed out. Check the service and network, then try again.'
    if type(error).__name__ in {'AuthError', 'AuthenticationError', 'ConfigurationError'}:
        return 'Database connection failed. Check the Neo4j service and NEO4J_* settings.'
    if isinstance(error, OSError):
        return hint or 'A file or network operation failed. Check paths, permissions, and connectivity.'
    return hint or 'The command could not complete. Check its inputs, configuration, and service availability.'


def run_cli(action, *, label='Command', hint=None):
    try:
        result = action()
        return result if isinstance(result, int) else 0
    except KeyboardInterrupt:
        print(f'{label} cancelled. Earlier completed work may have been saved.', file=sys.stderr)
        return 130
    except BrokenPipeError:
        # Avoid another broken-pipe exception when Python flushes at shutdown.
        try:
            with open(os.devnull, 'w') as sink:
                os.dup2(sink.fileno(), sys.stdout.fileno())
        except (AttributeError, OSError, ValueError):
            pass
        return 0
    except Exception as error:
        print(f'{label}: {error_message(error, hint=hint)}', file=sys.stderr)
        return 1


def cli_entrypoint(label, *, hint=None):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            return run_cli(lambda: function(*args, **kwargs), label=label, hint=hint)
        return wrapped
    return decorate


@contextmanager
def command_imports(module_name):
    """Report missing startup dependencies for scripts without masking library imports."""
    try:
        yield
    except ImportError as error:
        if module_name != '__main__':
            raise
        print(error_message(error), file=sys.stderr)
        raise SystemExit(1) from None

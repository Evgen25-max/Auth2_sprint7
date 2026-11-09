import functools
import inspect
from typing import Any, Callable, Iterable, Optional

from opentelemetry import trace
from opentelemetry.trace import StatusCode

tracer = trace.get_tracer(__name__)


SENSITIVE_EXACT = {
    "password",
    "current_password",
    "new_password",
    "old_password",
    "hashed_password",
    "token",
    "access_token",
    "refresh_token",
    "refresh_token_str",
    "access_token_str",
    "id_token",
    "secret",
    "jwt_secret",
    "pepper",
    "password_pepper",
    "jti",
    "authorization",
    "cookie",
    "session",
}

SENSITIVE_SUBSTRINGS = (
    "password",
    "secret",
    "pepper",
    "authorization",
    "cookie",
    "jti",
)


def _is_sensitive(name: str) -> bool:
    lowered = name.lower()
    return lowered in SENSITIVE_EXACT or any(
        fragment in lowered for fragment in SENSITIVE_SUBSTRINGS
    )


def _record_arguments(span, func: Callable, args: tuple, kwargs: dict) -> None:
    try:
        sig = inspect.signature(func)
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
    except (TypeError, ValueError):
        return

    for param_name, value in bound.arguments.items():
        if param_name in {"self", "cls"}:
            continue

        if _is_sensitive(param_name):
            span.set_attribute(f"arg.{param_name}", "***REDACTED***")
            continue

        if value is None:
            continue

        if isinstance(value, bool):
            span.set_attribute(f"arg.{param_name}", value)
        elif isinstance(value, (int, float, str)):
            span.set_attribute(f"arg.{param_name}", value)
        else:
            span.set_attribute(f"arg.{param_name}.type", type(value).__name__)


def _record_result(span, result: Any) -> None:
    if result is None:
        return

    if isinstance(result, bool):
        span.set_attribute("result", result)
    elif isinstance(result, (int, float, str)):
        span.set_attribute("result", result)
    else:
        span.set_attribute("result.type", type(result).__name__)


def traced(
    name: Optional[str] = None,
    record_args: bool = True,
    record_result: bool = False,
) -> Callable:
    """
    Декоратор для создания OpenTelemetry-спана вокруг функции или метода.
    """

    def decorator(func: Callable) -> Callable:
        span_name = name or func.__qualname__

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                with tracer.start_as_current_span(span_name) as span:
                    if record_args:
                        _record_arguments(span, func, args, kwargs)

                    try:
                        result = await func(*args, **kwargs)
                        if record_result:
                            _record_result(span, result)
                        return result
                    except Exception as exc:
                        span.set_status(StatusCode.ERROR, str(exc))
                        span.record_exception(exc)
                        raise

            setattr(async_wrapper, "__traced__", True)
            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                if record_args:
                    _record_arguments(span, func, args, kwargs)

                try:
                    result = func(*args, **kwargs)
                    if record_result:
                        _record_result(span, result)
                    return result
                except Exception as exc:
                    span.set_status(StatusCode.ERROR, str(exc))
                    span.record_exception(exc)
                    raise

        setattr(sync_wrapper, "__traced__", True)
        return sync_wrapper

    return decorator


def trace_class(
    cls: Optional[type] = None,
    *,
    exclude: Optional[Iterable[str]] = None,
    record_args: bool = True,
    record_result: bool = False,
) -> Callable[[type], type]:
    """
    Декоратор для класса.

    Оборачивает все публичные async-методы класса спанами OpenTelemetry.

    """

    def wrap(target_cls: type) -> type:
        exclude_set = set(exclude or [])

        for attr_name, attr in list(target_cls.__dict__.items()):
            if attr_name in exclude_set:
                continue

            if attr_name.startswith("_"):
                continue

            if not callable(attr):
                continue

            if not inspect.iscoroutinefunction(attr):
                continue

            if getattr(attr, "__traced__", False):
                continue

            decorated = traced(
                name=f"{target_cls.__name__}.{attr_name}",
                record_args=record_args,
                record_result=record_result,
            )(attr)

            setattr(target_cls, attr_name, decorated)

        return target_cls

    if cls is None:
        return wrap

    return wrap(cls)
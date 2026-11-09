import functools
import inspect
from typing import Any, Callable, Iterable, Optional

from opentelemetry import trace
from opentelemetry.trace import StatusCode

tracer = trace.get_tracer(__name__)


# === Глобальные списки (работают всегда, если не задан allow_fields) ===
SENSITIVE_EXACT = {
    "password", "current_password", "new_password", "old_password",
    "hashed_password", "token", "access_token", "refresh_token",
    "refresh_token_str", "access_token_str", "id_token", "secret",
    "jwt_secret", "pepper", "password_pepper", "jti",
    "authorization", "cookie", "session",
}

SENSITIVE_SUBSTRINGS = (
    "password", "secret", "pepper", "authorization", "cookie", "jti",
)


def _is_sensitive(
    name: str,
    extra_exact: frozenset[str] = frozenset(),
    extra_substrings: tuple[str, ...] = (),
) -> bool:
    lowered = name.lower()
    if lowered in SENSITIVE_EXACT or lowered in extra_exact:
        return True
    if any(fragment in lowered for fragment in SENSITIVE_SUBSTRINGS):
        return True
    if any(fragment in lowered for fragment in extra_substrings):
        return True
    return False


def _record_arguments(
    span,
    func: Callable,
    args: tuple,
    kwargs: dict,
    extra_exact: frozenset[str] = frozenset(),
    extra_substrings: tuple[str, ...] = (),
    allow_fields: Optional[frozenset[str]] = None,
) -> None:
    try:
        sig = inspect.signature(func)
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
    except (TypeError, ValueError):
        return

    for param_name, value in bound.arguments.items():
        if param_name in {"self", "cls"}:
            continue

        lowered = param_name.lower()

        # === РЕЖИМ WHITELIST (allow_fields задан) ===
        # Всё, что НЕ в allow_fields, становится REDACTED независимо ни от чего.
        # Всё, что В allow_fields, пишется как есть.
        if allow_fields is not None:
            if lowered not in allow_fields:
                span.set_attribute(f"arg.{param_name}", "***REDACTED***")
                continue
            # поле разрешено → пропускаем sensitive-фильтр, пишем значение
        else:
            # === РЕЖИМ BLACKLIST (по умолчанию) ===
            if _is_sensitive(param_name, extra_exact, extra_substrings):
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
    redact_fields: Optional[Iterable[str]] = None,
    redact_substrings: Optional[Iterable[str]] = None,
    allow_fields: Optional[Iterable[str]] = None,
) -> Callable:
    """
    Декоратор OpenTelemetry-спана вокруг функции или метода (sync и async).

    Args:
        name: Имя спана (по умолчанию __qualname__).
        record_args: Записывать ли аргументы.
        record_result: Записывать ли результат.
        redact_fields: Доп. точные имена для маскировки (blacklist-режим).
        redact_substrings: Доп. подстроки для маскировки (blacklist-режим).
        allow_fields: WHITEList разрешённых параметров. Если задан —
            ВСЕ параметры вне этого списка становятся ***REDACTED***,
            а параметры внутри — пишутся как есть, ПЕРЕКРЫВАЯ глобальные
            sensitive-списки.

            Безопасность: allow_fields — осознанный override. Если вы
            случайно укажете в нём "password", пароль попадёт в трейс.
            Используйте whitelist только там, где полный контроль над
            списком полей важнее защиты по умолчанию.
    """
    extra_exact = frozenset(f.lower() for f in (redact_fields or ()))
    extra_substrings = tuple(s.lower() for s in (redact_substrings or ()))
    allow_set = (
        frozenset(f.lower() for f in allow_fields)
        if allow_fields is not None
        else None
    )

    def decorator(func: Callable) -> Callable:
        span_name = name or func.__qualname__

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                with tracer.start_as_current_span(span_name) as span:
                    if record_args:
                        _record_arguments(
                            span, func, args, kwargs,
                            extra_exact=extra_exact,
                            extra_substrings=extra_substrings,
                            allow_fields=allow_set,
                        )
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
                    _record_arguments(
                        span, func, args, kwargs,
                        extra_exact=extra_exact,
                        extra_substrings=extra_substrings,
                        allow_fields=allow_set,
                    )
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


def _unwrap_descriptor(attr):
    """
    Возвращает (raw_function, descriptor_kind), где descriptor_kind —
    'static' | 'class' | None.
    """
    if isinstance(attr, staticmethod):
        return attr.__func__, "static"
    if isinstance(attr, classmethod):
        return attr.__func__, "class"
    return attr, None


def trace_class(
    cls: Optional[type] = None,
    *,
    exclude: Optional[Iterable[str]] = None,
    record_args: bool = True,
    record_result: bool = False,
    redact_fields: Optional[Iterable[str]] = None,
    redact_substrings: Optional[Iterable[str]] = None,
    allow_fields: Optional[Iterable[str]] = None,
) -> Callable[[type], type]:
    """
    Декоратор класса. Оборачивает ВСЕ публичные методы (sync и async)
    спанами OpenTelemetry.

    Args:
        allow_fields: WHITEList, применяется ко ВСЕМ методам класса.
            См. docstring traced() про безопасность override.
    """
    extra_exact = frozenset(f.lower() for f in (redact_fields or ()))
    extra_substrings = tuple(s.lower() for s in (redact_substrings or ()))
    allow_set = (
        frozenset(f.lower() for f in allow_fields)
        if allow_fields is not None
        else None
    )

    def wrap(target_cls: type) -> type:
        exclude_set = set(exclude or [])

        for attr_name, attr in list(target_cls.__dict__.items()):
            if attr_name in exclude_set:
                continue
            if attr_name.startswith("_"):
                continue

            raw_func, kind = _unwrap_descriptor(attr)

            # Оборачиваем только функции (sync или async), не property и пр.
            if not (inspect.isfunction(raw_func) or inspect.ismethod(raw_func)):
                continue
            if not (
                inspect.iscoroutinefunction(raw_func)
                or inspect.isfunction(raw_func)
            ):
                continue
            if getattr(raw_func, "__traced__", False):
                continue

            decorated = traced(
                name=f"{target_cls.__name__}.{attr_name}",
                record_args=record_args,
                record_result=record_result,
                redact_fields=extra_exact,
                redact_substrings=extra_substrings,
                allow_fields=allow_set,
            )(raw_func)

            # Восстанавливаем природу дескриптора
            if kind == "static":
                decorated = staticmethod(decorated)
            elif kind == "class":
                decorated = classmethod(decorated)

            setattr(target_cls, attr_name, decorated)

        return target_cls

    if cls is None:
        return wrap
    return wrap(cls)

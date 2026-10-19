# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""
Mark plugin methods that can be called from outside Spyder's plugins.

Plugins mark methods with :func:`expose` to make them available to clients
that drive Spyder from the outside, such as AI agents (through the MCP server
plugin). Plugins don't depend on those clients: the decorator only marks the
method, and clients collect the marked methods of every plugin with
:func:`get_exposed_methods`.

Exposed methods are a contract with outside callers, so they must:

* Take JSON-compatible arguments, with type hints (``str``, ``int``,
  ``float``, ``bool``, ``list``, ``dict``, ``Literal`` and optional values of
  those). Their descriptions come from the ``Parameters`` section of the
  docstring, in numpydoc format.
* Return data: ``None``, strings, numbers, booleans, lists and dicts of
  them, or :class:`Image` objects (also inside lists and dicts). Methods that
  take time (e.g. running code in a console) return a
  :class:`concurrent.futures.Future` that is resolved with the data later.
* Raise :class:`ExposedCallError` (or resolve their future with it) when the
  call can't be completed, with a message that tells the caller what to do.
* Never open dialogs or wait for user input, which would block Spyder.

Exposed methods always run in the main Qt thread. Clients can say who is
calling with :func:`calling_as`, so exposed methods can tell callers apart
with :func:`current_caller` (e.g. to only let an agent interrupt the code it
started).
"""

# Standard library imports
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import functools
from typing import Any


@dataclass(frozen=True)
class ExposedSpec:
    """Options given to :func:`expose`, stored on the marked method."""

    name: str | None = None
    """
    Name for callers. By default, the method name. Set it to keep the name
    stable if the method is renamed.
    """

    description: str | None = None
    """Description for callers. By default, the method's docstring."""

    read_only: bool = False
    """Whether the method doesn't change any state."""

    destructive: bool = False
    """Whether the method may make changes that can't be undone."""


@dataclass
class Image:
    """An image returned by an exposed method."""

    data: bytes
    """Image data, e.g. the contents of a PNG file."""

    mime_type: str = "image/png"
    """MIME type of the data, e.g. ``image/png`` or ``image/svg+xml``."""


@dataclass(frozen=True)
class Caller:
    """An outside caller of exposed methods, e.g. an AI agent session."""

    id: str
    """Unique id of the caller."""

    name: str
    """Name shown to users, e.g. ``Agent 2``."""


_current_caller: ContextVar[Caller | None] = ContextVar(
    "spyder_exposed_caller", default=None
)


def current_caller() -> Caller | None:
    """
    Return who is calling the exposed method that is running, or ``None`` if
    it's not called from outside (e.g. by the user through Spyder's
    interface).

    Methods that finish later (returning a future) must read it when they're
    called, not when they finish.
    """
    return _current_caller.get()


@contextmanager
def calling_as(caller: Caller | None) -> Iterator[None]:
    """Run exposed methods called inside this block on behalf of ``caller``."""
    token = _current_caller.set(caller)
    try:
        yield
    finally:
        _current_caller.reset(token)


class ExposedCallError(Exception):
    """
    Error to report to the caller of an exposed method.

    Its message should explain what went wrong and, if possible, what the
    caller can do about it.
    """


def expose(
    func: Callable | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    read_only: bool = False,
    destructive: bool = False,
) -> Callable:
    """
    Mark a plugin method as callable from outside Spyder's plugins.

    The method itself doesn't change. Overriding a marked method in a
    subclass without the decorator stops exposing it.

    Parameters
    ----------
    func: Callable, optional
        Method to decorate, passed automatically when the decorator is used
        without arguments.
    name: str, optional
        Name for callers. By default, the method name.
    description: str, optional
        Description for callers. By default, the method's docstring without
        its sections (``Parameters``, ``Returns``, etc).
    read_only: bool, optional
        Whether the method doesn't change any state. The default is
        ``False``.
    destructive: bool, optional
        Whether the method may make changes that can't be undone. The
        default is ``False``.
    """
    if func is None:
        return functools.partial(
            expose,
            name=name,
            description=description,
            read_only=read_only,
            destructive=destructive,
        )

    func._spyder_exposed = ExposedSpec(
        name=name,
        description=description,
        read_only=read_only,
        destructive=destructive,
    )
    return func


def get_exposed_spec(func: Any) -> ExposedSpec | None:
    """Return the options of a method marked with :func:`expose`, if any."""
    spec = getattr(func, "_spyder_exposed", None)
    return spec if isinstance(spec, ExposedSpec) else None


def get_exposed_methods(
    cls: type,
) -> dict[str, tuple[Callable, ExposedSpec]]:
    """
    Return the methods of ``cls`` marked with :func:`expose`.

    Parameters
    ----------
    cls: type
        Class to inspect, usually a plugin class.

    Returns
    -------
    dict
        Maps the attribute name of each exposed method to the (unbound)
        function and its options.
    """
    methods = {}
    for attr_name in dir(cls):
        try:
            attr = getattr(cls, attr_name)
        except Exception:
            continue
        spec = get_exposed_spec(attr)
        if spec is not None and callable(attr):
            methods[attr_name] = (attr, spec)
    return methods

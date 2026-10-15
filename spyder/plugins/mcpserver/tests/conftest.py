# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""Fixtures for the MCP server plugin tests."""

# Reuse the IPython console fixture to test tools against real kernels
from spyder.plugins.ipythonconsole.tests.conftest import (  # noqa: F401
    ipyconsole,
    pytest_runtest_makereport,
)

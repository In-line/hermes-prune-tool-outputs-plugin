# hermes-prune-tool-outputs: model-initiated tool output pruning for Hermes Agent.
# Copyright (C) 2026  Alik Aslanyan <inline0@pm.me>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""hermes-prune-tool-outputs — model-initiated tool output pruning.

This plugin lets the MODEL decide when to prune. The model calls the
prune_tool_outputs tool explicitly when it determines previous tool
results are no longer needed.

Architecture:
1. Model calls prune_tool_outputs → handler sets a thread-safe flag
2. On the next API call, llm_request middleware checks the flag,
   replaces old large tool results with 1-line summaries, clears flag
3. Middleware also appends a brief instruction to the system message
   telling the model when to call prune_tool_outputs

Lossless: the session store keeps original tool results. Only the API
payload is pruned; full content can be recovered from the store if needed.
"""

import logging

logger = logging.getLogger("hermes_plugins.prune_tool_outputs")

__version__ = "1.0.0"


def register(ctx):
    """Plugin entry point."""
    from .middleware import llm_request_middleware
    from .tool import TOOL_SCHEMA, handle_prune_tool_outputs

    # Register the model-callable tool
    ctx.register_tool(
        name="prune_tool_outputs",
        toolset="context",
        schema=TOOL_SCHEMA,
        handler=handle_prune_tool_outputs,
        description="Replace old tool results with compact summaries to free context space",
        emoji="🧹",
    )

    # Register llm_request middleware for actual pruning + system prompt injection
    ctx.register_middleware("llm_request", llm_request_middleware)

    logger.info(
        "hermes-prune-tool-outputs registered: tool=prune_tool_outputs + llm_request middleware"
    )

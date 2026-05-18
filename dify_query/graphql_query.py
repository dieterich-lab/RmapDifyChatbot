"""Compatibility wrapper for the old module name.

Use dify_query.metadata_query for new imports.
"""

from dify_query.metadata_query import CODE_VERSION, main

__all__ = ["main", "CODE_VERSION"]

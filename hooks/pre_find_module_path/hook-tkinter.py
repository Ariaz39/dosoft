"""Keep tkinter available while packaging the portable DOSOFT beta.

The development Python installation intentionally obtains its Tcl/Tk data
from the local portable runtime.  PyInstaller's default availability check
does not know that location and would otherwise exclude tkinter altogether.
"""


def pre_find_module_path(hook_api):
    """Use the regular tkinter package search path without excluding it."""

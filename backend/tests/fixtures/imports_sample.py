"""Import variety fixture."""

import os
import sys as system
from pathlib import Path
from collections import OrderedDict, defaultdict
from ..services.auth import authenticate
from . import utils
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional

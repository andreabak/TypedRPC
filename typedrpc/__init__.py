"""TypedRPC package for quick JSON-like RPC server-clients applications
with dataclasses and type annotations"""

from . import models
from . import service
from . import sockets

from .models import *
from .service import *
from .sockets import *

__all__ = models.__all__ + service.__all__ + sockets.__all__

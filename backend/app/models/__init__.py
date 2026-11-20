"""All models; importing this package registers every table on ``Base.metadata``."""

from app.models.booking import Booking
from app.models.lab import Lab
from app.models.lab_closure import LabClosure
from app.models.slot import Slot
from app.models.user import User

__all__ = ["Booking", "Lab", "LabClosure", "Slot", "User"]

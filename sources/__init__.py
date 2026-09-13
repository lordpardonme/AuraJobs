"""AuraJobs Sources Package."""
from .base import BaseSourceAdapter
from .multiboard_adapter import MultiBoardAdapter, JobSpyAdapter
from .remoteok_adapter import RemoteOKAdapter
from .remotive_adapter import RemotiveAdapter
from .himalayas_adapter import HimalayasAdapter
from .ats_adapter import ATSAdapter

__all__ = [
    "BaseSourceAdapter",
    "MultiBoardAdapter",
    "JobSpyAdapter",
    "RemoteOKAdapter",
    "RemotiveAdapter",
    "HimalayasAdapter",
    "ATSAdapter"
]

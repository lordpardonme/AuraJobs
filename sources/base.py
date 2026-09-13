from abc import ABC, abstractmethod
import pandas as pd

class BaseSourceAdapter(ABC):
    """Abstract base class for all job source adapters."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def search(self, term: str, location: str, region: str, country: str,
               hours_old: int, results_wanted: int) -> pd.DataFrame:
        """
        Execute a search against the source.
        Returns a DataFrame of results, or an empty DataFrame on failure/no results.
        """
        pass

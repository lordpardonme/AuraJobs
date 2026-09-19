"""
API Response Caching Layer for AuraJobs.

Provides JSON file-based caching for adapter responses to:
- Reduce redundant API calls
- Speed up repeat runs
- Avoid rate limits
- Survive network blips

Cache key: SHA256 of (adapter_name + method_name + sorted_params)
Cache value: Serialized DataFrame + metadata
"""

import os
import json
import hashlib
import pickle
import time
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, Dict
import pandas as pd


class APICache:
    """JSON file-based cache for API responses."""

    def __init__(self, cache_dir: str = "cache", ttl_hours: int = 24, enabled: bool = True):
        """
        Initialize cache.

        Args:
            cache_dir: Directory to store cache files
            ttl_hours: Time-to-live in hours (default 24)
            enabled: Whether caching is enabled
        """
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_hours * 3600
        self.enabled = enabled
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # In-memory index for fast lookups
        self._index: Dict[str, Dict] = {}
        self._load_index()

    def _load_index(self):
        """Load cache index from disk."""
        index_file = self.cache_dir / "index.json"
        if index_file.exists():
            try:
                with open(index_file) as f:
                    self._index = json.load(f)
            except Exception:
                self._index = {}

    def _save_index(self):
        """Save cache index to disk."""
        index_file = self.cache_dir / "index.json"
        try:
            with open(index_file, "w") as f:
                json.dump(self._index, f)
        except Exception:
            pass

    def _make_key(self, adapter_name: str, method_name: str, **params) -> str:
        """Generate deterministic cache key from adapter, method, and parameters."""
        # Sort params for consistent key generation
        sorted_params = sorted(params.items())
        key_data = f"{adapter_name}:{method_name}:{sorted_params}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    def _cache_file(self, key: str) -> Path:
        """Get cache file path for a key."""
        return self.cache_dir / f"{key}.pkl"

    def _meta_file(self, key: str) -> Path:
        """Get metadata file path for a key."""
        return self.cache_dir / f"{key}.meta.json"

    def get(self, adapter_name: str, method_name: str, **params) -> Optional[pd.DataFrame]:
        """
        Retrieve cached response if valid.

        Returns:
            Cached DataFrame or None if not found/expired
        """
        if not self.enabled:
            return None

        key = self._make_key(adapter_name, method_name, **params)
        meta_path = self._meta_file(key)
        cache_path = self._cache_file(key)

        if not meta_path.exists() or not cache_path.exists():
            return None

        try:
            with open(meta_path) as f:
                meta = json.load(f)

            # Check TTL
            cached_time = meta.get("timestamp", 0)
            if time.time() - cached_time > self.ttl_seconds:
                self._remove(key)
                return None

            # Load DataFrame
            with open(cache_path, "rb") as f:
                df = pickle.load(f)

            # Update access time
            meta["last_accessed"] = time.time()
            meta["access_count"] = meta.get("access_count", 0) + 1
            with open(meta_path, "w") as f:
                json.dump(meta, f)

            return df

        except Exception:
            self._remove(key)
            return None

    def set(self, adapter_name: str, method_name: str, df: pd.DataFrame, **params):
        """Store response in cache."""
        if not self.enabled:
            return

        if df is None or df.empty:
            return

        key = self._make_key(adapter_name, method_name, **params)
        meta_path = self._meta_file(key)
        cache_path = self._cache_file(key)

        try:
            # Save DataFrame
            with open(cache_path, "wb") as f:
                pickle.dump(df, f)

            # Save metadata
            meta = {
                "adapter": adapter_name,
                "method": method_name,
                "params": params,
                "timestamp": time.time(),
                "last_accessed": time.time(),
                "access_count": 1,
                "rows": len(df),
                "columns": list(df.columns),
            }
            with open(meta_path, "w") as f:
                json.dump(meta, f)

            # Update index
            self._index[key] = meta
            self._save_index()

        except Exception:
            self._remove(key)

    def _remove(self, key: str):
        """Remove cache entry."""
        for ext in [".pkl", ".meta.json"]:
            path = self.cache_dir / f"{key}{ext}"
            if path.exists():
                path.unlink()
        self._index.pop(key, None)
        self._save_index()

    def clear(self, older_than_hours: Optional[int] = None):
        """Clear cache entries."""
        if older_than_hours is None:
            # Clear all
            for path in self.cache_dir.glob("*.pkl"):
                path.unlink()
            for path in self.cache_dir.glob("*.meta.json"):
                path.unlink()
            self._index.clear()
            self._save_index()
        else:
            # Clear only old entries
            cutoff = time.time() - (older_than_hours * 3600)
            for key, meta in list(self._index.items()):
                if meta.get("timestamp", 0) < cutoff:
                    self._remove(key)

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_entries = len(self._index)
        total_size = sum(
            (self.cache_dir / f"{k}.pkl").stat().st_size
            for k in self._index
            if (self.cache_dir / f"{k}.pkl").exists()
        )
        return {
            "enabled": self.enabled,
            "entries": total_entries,
            "size_mb": round(total_size / 1024 / 1024, 2),
            "ttl_hours": self.ttl_seconds / 3600,
        }


# Global cache instance
_global_cache: Optional[APICache] = None


def get_cache(
    cache_dir: str = "cache",
    ttl_hours: int = 24,
    enabled: bool = True
) -> APICache:
    """Get or create global cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = APICache(cache_dir, ttl_hours, enabled)
    return _global_cache


def cache_adapter_response(
    cache: Optional[APICache] = None,
    ttl_hours: int = 24
) -> Callable:
    """
    Decorator to cache adapter method responses.

    Usage:
        @cache_adapter_response()
        def fetch_jobs(self, term, location, ...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Get cache instance
            c = cache or get_cache(ttl_hours=ttl_hours)

            # Build cache params from method arguments
            # Get parameter names from function signature
            import inspect
            sig = inspect.signature(func)
            bound = sig.bind(self, *args, **kwargs)
            bound.apply_defaults()

            # Exclude self and build param dict
            params = {k: v for k, v in bound.arguments.items() if k != "self"}

            # Try cache first
            adapter_name = getattr(self, "name", self.__class__.__name__)
            method_name = func.__name__

            cached_df = c.get(adapter_name, method_name, **params)
            if cached_df is not None:
                print(f"  [CACHE HIT] {adapter_name}.{method_name} - {len(cached_df)} rows")
                return cached_df

            # Call original function
            result = func(self, *args, **kwargs)

            # Cache result
            if result is not None and not result.empty:
                c.set(adapter_name, method_name, result, **params)
                print(f"  [CACHE MISS] {adapter_name}.{method_name} - {len(result)} rows cached")

            return result
        return wrapper
    return decorator


def invalidate_adapter_cache(adapter_name: str, method_name: Optional[str] = None):
    """Invalidate cache entries for an adapter/method."""
    c = get_cache()
    keys_to_remove = []
    for key, meta in c._index.items():
        if meta.get("adapter") == adapter_name:
            if method_name is None or meta.get("method") == method_name:
                keys_to_remove.append(key)

    for key in keys_to_remove:
        c._remove(key)

    print(f"Invalidated {len(keys_to_remove)} cache entries for {adapter_name}")


# CLI helper functions
def print_cache_stats():
    """Print cache statistics."""
    c = get_cache()
    stats = c.stats()
    print(f"\nCache Stats:")
    print(f"  Enabled: {stats['enabled']}")
    print(f"  Entries: {stats['entries']}")
    print(f"  Size: {stats['size_mb']} MB")
    print(f"  TTL: {stats['ttl_hours']} hours")


def clear_cache(older_than_hours: Optional[int] = None):
    """Clear cache from CLI."""
    c = get_cache()
    c.clear(older_than_hours)
    if older_than_hours:
        print(f"Cleared cache entries older than {older_than_hours} hours")
    else:
        print("Cleared all cache entries")
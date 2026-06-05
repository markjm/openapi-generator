#!/usr/bin/env python3
"""Reproduce debug-setter overhead during Configuration deepcopy."""

import copy
import logging
import time

class ConfigurationBefore:
    """Reproduces the ORIGINAL (unfixed) behaviour."""

    def __init__(self):
        self.logger = {
            "package_logger": logging.getLogger("package"),
            "urllib3_logger": logging.getLogger("urllib3"),
        }
        self.__debug = False  # set directly to avoid triggering setter

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if k not in ("logger",):
                setattr(result, k, copy.deepcopy(v, memo))
        result.logger = copy.copy(self.logger)
        result.debug = self.debug   # <-- always fires the setter (bug)
        return result

    @property
    def debug(self):
        return self.__debug

    @debug.setter
    def debug(self, value):
        # ORIGINAL: unconditionally calls setLevel even when value is unchanged
        self.__debug = value
        for _, logger in self.logger.items():
            logger.setLevel(logging.DEBUG if value else logging.WARNING)


class ConfigurationAfter:
    """Reproduces the FIXED behaviour (both layers applied)."""

    def __init__(self):
        self.logger = {
            "package_logger": logging.getLogger("package"),
            "urllib3_logger": logging.getLogger("urllib3"),
        }
        self.__debug = False  # set directly to avoid triggering setter

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if k not in ("logger",):
                setattr(result, k, copy.deepcopy(v, memo))
        result.logger = copy.copy(self.logger)
        # __debug is already copied above; avoid re-running debug setter.
        return result

    @property
    def debug(self):
        return self.__debug

    @debug.setter
    def debug(self, value):
        try:
            if self.__debug == value:
                return
        except AttributeError:
            pass
        self.__debug = value
        for _, logger in self.logger.items():
            logger.setLevel(logging.DEBUG if value else logging.WARNING)


def count_clear_cache_calls(cls, num_loggers: int, num_copies: int) -> tuple[int, float]:
    """
    Register `num_loggers` loggers, deepcopy a Configuration instance
    `num_copies` times, and return (clear_cache_call_count, elapsed_seconds).
    """
    for i in range(num_loggers):
        logging.getLogger(f"dummy.logger.{i}")

    call_count = 0
    original_clear_cache = logging.Logger.manager.__class__._clear_cache

    def patched_clear_cache(self):
        nonlocal call_count
        call_count += 1
        original_clear_cache(self)

    logging.Logger.manager.__class__._clear_cache = patched_clear_cache

    cfg = cls()
    start = time.perf_counter()
    for _ in range(num_copies):
        copy.deepcopy(cfg)
    elapsed = time.perf_counter() - start

    logging.Logger.manager.__class__._clear_cache = original_clear_cache
    return call_count, elapsed


def main():
    NUM_LOGGERS = 2_000
    NUM_COPIES  = 500

    print(f"Simulating {NUM_LOGGERS:,} registered loggers, {NUM_COPIES:,} deepcopy calls\n")

    before_calls, before_time = count_clear_cache_calls(ConfigurationBefore, NUM_LOGGERS, NUM_COPIES)
    after_calls,  after_time  = count_clear_cache_calls(ConfigurationAfter,  NUM_LOGGERS, NUM_COPIES)

    print(f"BEFORE fix: {before_calls:>10,} _clear_cache calls  ({before_time:.3f}s)")
    print(f"AFTER  fix: {after_calls:>10,} _clear_cache calls  ({after_time:.3f}s)")
    print()

    if after_calls == 0:
        print("✓ Fix confirmed: zero redundant _clear_cache calls during deepcopy.")
    else:
        print("✗ Fix did not eliminate redundant _clear_cache calls.")

    speedup = before_time / after_time if after_time > 0 else float('inf')
    print(f"  Speedup: ~{speedup:.1f}x")


if __name__ == "__main__":
    main()

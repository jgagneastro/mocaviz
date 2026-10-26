"""Bounded, cancellable in-memory astrometry fits. No database operations."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import secrets
import threading
import time
from contextlib import contextmanager


class FitCancelled(RuntimeError):
    pass


class FitLimitReached(RuntimeError):
    pass


class FitBusy(RuntimeError):
    pass


def _positive_env(name, default, maximum):
    try:
        value = float(os.environ.get(name, default))
        if not math.isfinite(value) or value <= 0:
            raise ValueError(name)
        return min(value, maximum)
    except (ValueError, TypeError):
        return default


class FitControl:
    def __init__(self, timeout=None, max_calls=None, clock=time.monotonic):
        self.timeout = float(timeout if timeout is not None else _positive_env(
            'ASTROMETRY_FIT_TIMEOUT_SECONDS', 900, 7200))
        self.max_calls = int(max_calls if max_calls is not None else _positive_env(
            'ASTROMETRY_ULTRANEST_MAX_NCALLS', 2000000, 20000000))
        self.clock = clock
        self.started = clock()
        self.finished = None
        self.cancelled = threading.Event()
        self.calls = 0
        self.phase = 'Preparing robust starting fit'

    @property
    def remaining_calls(self):
        return max(0, self.max_calls - self.calls)

    def check(self, phase=None, likelihood=False):
        if self.cancelled.is_set():
            raise FitCancelled('Fit cancelled. No unfinished fit was applied.')
        if self.clock() - self.started >= self.timeout:
            raise FitLimitReached(
                'Fit stopped at the runtime limit (%g s). Sampling is incomplete; '
                'no fitted values were applied. Try SciPy or review the selected measurements.' % self.timeout)
        if likelihood:
            self.calls += 1
        if self.calls >= self.max_calls:
            raise FitLimitReached(
                'Fit stopped at the likelihood-call limit (%s). Sampling is incomplete; '
                'no fitted values were applied.' % self.max_calls)
        if phase is not None:
            self.phase = str(phase)

    def snapshot(self):
        end = self.finished if self.finished is not None else self.clock()
        return dict(elapsedSeconds=max(0., end - self.started), phase=self.phase,
                    likelihoodCalls=self.calls, maxLikelihoodCalls=self.max_calls,
                    timeoutSeconds=self.timeout)


_context = threading.local()


def current_control():
    return getattr(_context, 'control', None)


@contextmanager
def using_control(control):
    previous = current_control()
    _context.control = control
    try:
        yield control
    finally:
        _context.control = previous


class FitJobs:
    """One active fit per web process; short polls remain responsive.

    Tokens are also scoped to the caller's credential hash. Cancelling remains
    'cancelling' until the actual sampler acknowledges its cooperative stop.
    """
    terminal = frozenset(('complete', 'failed', 'cancelled', 'incomplete'))

    def __init__(self, control_factory=FitControl, ttl=3600, capacity=32):
        self.control_factory = control_factory
        self.ttl = ttl
        self.capacity = capacity
        self.lock = threading.RLock()
        self.jobs = {}

    def _snapshot(self, job):
        return dict(id=job['id'], state=job['state'], error=job.get('error'),
                    result=copy.deepcopy(job.get('result')),
                    **job['control'].snapshot())

    def _prune(self):
        now = time.monotonic()
        expired = [k for k, j in self.jobs.items() if j['state'] in self.terminal
                   and now - j['ended'] > self.ttl]
        for key in expired:
            del self.jobs[key]
        finished = sorted((j['ended'], k) for k, j in self.jobs.items()
                          if j['state'] in self.terminal)
        while len(self.jobs) >= self.capacity and finished:
            del self.jobs[finished.pop(0)[1]]

    def start(self, owner, body, runner):
        fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, allow_nan=False,
                                                separators=(',', ':')).encode()).hexdigest()
        with self.lock:
            self._prune()
            for existing in self.jobs.values():
                if existing['state'] not in self.terminal:
                    if existing['owner'] == owner and existing['fingerprint'] == fingerprint:
                        return self._snapshot(existing)
                    raise FitBusy('An astrometry fit is already running. Wait for it to finish or cancel it before starting another.')
            key = secrets.token_hex(16)
            job = dict(id=key, owner=owner, fingerprint=fingerprint, state='running',
                       control=self.control_factory(), result=None)
            self.jobs[key] = job
            thread = threading.Thread(target=self._run, args=(job, runner),
                                      name='astrometry-fit-' + key[:8], daemon=True)
            try:
                thread.start()
            except Exception:
                del self.jobs[key]
                raise
            return self._snapshot(job)

    def _run(self, job, runner):
        control = job['control']
        state, result, error = 'failed', None, None
        try:
            with using_control(control):
                control.check()
                result = runner()
                control.check()
            state = 'complete'
        except FitCancelled as exc:
            state, result, error = 'cancelled', None, str(exc)
        except FitLimitReached as exc:
            state, result, error = 'incomplete', None, str(exc)
        except Exception as exc:
            state, result, error = 'failed', None, ('%s: %s' % (type(exc).__name__, exc))[:1000]
        finally:
            with self.lock:
                control.finished = control.clock()
                job.update(state=state, result=result, error=error, ended=time.monotonic())

    def status(self, owner, key, cancel=False):
        with self.lock:
            job = self.jobs.get(key)
            if job is not None and job['state'] in self.terminal and time.monotonic() - job['ended'] > self.ttl:
                del self.jobs[key]
                job = None
            if job is None or not secrets.compare_digest(job['owner'], owner):
                raise KeyError('Fit job not found or expired. Start a new fit.')
            if cancel and job['state'] not in self.terminal:
                job['control'].cancelled.set()
                job['state'] = 'cancelling'
            return self._snapshot(job)

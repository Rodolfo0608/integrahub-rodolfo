import time
from dataclasses import dataclass

from app.upstreams import UpstreamError


@dataclass(frozen=True)
class Permit:
    generation: int
    probe: bool


class CircuitBreaker:
    """Single-event-loop breaker; counts failed logical calls, after their retries."""

    def __init__(self, threshold=3, cooldown=30.0, clock=time.monotonic):
        self.threshold = threshold
        self.cooldown = cooldown
        self.clock = clock
        self.state = "closed"
        self.failures = 0
        self.opened_at = 0.0
        self.generation = 0

    def _enter(self):
        if self.state == "half_open":
            raise UpstreamError("CIRCUIT_OPEN")
        if self.state == "open":
            if self.clock() - self.opened_at < self.cooldown:
                raise UpstreamError("CIRCUIT_OPEN")
            self.state = "half_open"
            return Permit(self.generation, True)
        return Permit(self.generation, False)

    def _finish(self, permit, success):
        # Ignore calls that started before a more recent state transition.
        if permit.generation != self.generation:
            return
        if success:
            self.failures = 0
            if permit.probe:
                self.state = "closed"
                self.generation += 1
            return
        self.failures += 1
        if permit.probe or self.failures >= self.threshold:
            self.state = "open"
            self.opened_at = self.clock()
            self.generation += 1

    async def call(self, operation):
        permit = self._enter()
        try:
            value = await operation()
        except UpstreamError:
            self._finish(permit, False)
            raise
        except BaseException:
            # A cancelled half-open probe must not block all future probes forever.
            if permit.probe:
                self._finish(permit, False)
            raise
        self._finish(permit, True)
        return value

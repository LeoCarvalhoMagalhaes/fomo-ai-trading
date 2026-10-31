import asyncio

from app.collector.scheduler import Scheduler


class FakeMarket:
    def __init__(self):
        self.calls = []

    async def refresh_tier1(self):
        self.calls.append("tier1")

    async def refresh_candles(self, tokens=None):
        self.calls.append("candles")
        return 0

    async def discover(self, trending=True):
        self.calls.append("discover")


class FakeEngine:
    def __init__(self):
        self.cycles = []
        self.next_full_at = None

    async def run_cycle(self, kind, trigger):
        self.cycles.append((kind, trigger))

    async def expire_recommendations(self):
        return 0

    async def monitor_positions(self):
        return None

    async def track_outcomes(self):
        return 0


async def test_scheduler_runs_initial_full_cycle_and_stops():
    m, e = FakeMarket(), FakeEngine()
    sched = Scheduler(m, e, quick_s=0.05, candles_s=0.05, discovery_s=10, full_s=10, outcomes_s=10)
    sched.start()
    await asyncio.sleep(0.3)
    await sched.stop()
    assert ("full", "inicio") in e.cycles
    assert any(k == "quick" for k, _ in e.cycles)
    assert "tier1" in m.calls and "candles" in m.calls
    assert e.next_full_at is not None
    assert all(t.done() for t in sched.tasks)


async def test_loop_survives_exceptions():
    m, e = FakeMarket(), FakeEngine()

    async def boom():
        raise RuntimeError("falha")

    m.refresh_tier1 = boom
    sched = Scheduler(m, e, quick_s=0.05, candles_s=10, discovery_s=10, full_s=10, outcomes_s=10)
    sched.start()
    await asyncio.sleep(0.25)
    await sched.stop()
    assert sum(1 for k, _ in e.cycles if k == "quick") == 0  # quick não roda sem dados, mas o loop segue vivo
    assert sched.errors >= 2

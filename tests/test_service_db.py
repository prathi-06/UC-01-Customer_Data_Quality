import concurrent.futures
from datetime import date, timedelta
import uuid
import pytest
from sqlalchemy import text
from app.db import engine
from app.service import (
    accept_run,
    finish_run,
    get_run,
    get_daily_usage,
    AcceptStatus
)

TEST_RECORDS = [{"record_id": "C01", "email": "a@b.com", "credit_limit": 100, "status": "ACTIVE"}]

@pytest.fixture(autouse=True)
def cleanup_test_data():
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM runs WHERE tenant_id LIKE 'test_%';"))
        conn.execute(text("DELETE FROM daily_usage WHERE tenant_id LIKE 'test_%';"))

def test_quota_of_3_then_4th_rejected():
    tenant = f"test_{uuid.uuid4().hex[:8]}"
    limit = 3
    fixed_date = date(2026, 10, 20)
    fake_clock = lambda: fixed_date

    # 3 accepts
    for i in range(1, 4):
        status, run_id, replay = accept_run(
            tenant_id=tenant,
            idempotency_key=f"key_{i}",
            operation="validate",
            records=TEST_RECORDS,
            quota_limit=limit,
            clock=fake_clock
        )
        assert status == AcceptStatus.ACCEPTED
        assert run_id is not None
        finish_run(run_id, "Succeeded", {"valid": 1})

    assert get_daily_usage(tenant, fixed_date) == 3

    # 4th should be rejected
    status4, run_id4, _ = accept_run(
        tenant_id=tenant,
        idempotency_key="key_4",
        operation="validate",
        records=TEST_RECORDS,
        quota_limit=limit,
        clock=fake_clock
    )
    assert status4 == AcceptStatus.QUOTA_EXHAUSTED
    assert run_id4 is None
    # Verify no run row created and usage remains 3
    assert get_daily_usage(tenant, fixed_date) == 3
    with engine.connect() as conn:
        run_count = conn.execute(text("SELECT count(*) FROM runs WHERE tenant_id = :t AND idempotency_key = 'key_4'"), {"t": tenant}).scalar()
        assert run_count == 0

def test_concurrency_one_slot_left_two_racing():
    for iteration in range(20):
        tenant = f"test_race_{uuid.uuid4().hex[:8]}"
        limit = 1
        fixed_date = date(2026, 10, 20)
        fake_clock = lambda: fixed_date

        def worker(key):
            return accept_run(
                tenant_id=tenant,
                idempotency_key=key,
                operation="validate",
                records=TEST_RECORDS,
                quota_limit=limit,
                clock=fake_clock
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker, "key_a")
            f2 = executor.submit(worker, "key_b")
            r1 = f1.result()
            r2 = f2.result()

        statuses = {r1[0], r2[0]}
        assert statuses == {AcceptStatus.ACCEPTED, AcceptStatus.QUOTA_EXHAUSTED}, f"Failed at iteration {iteration}: {statuses}"
        assert get_daily_usage(tenant, fixed_date) == 1
        with engine.connect() as conn:
            run_count = conn.execute(text("SELECT count(*) FROM runs WHERE tenant_id = :t"), {"t": tenant}).scalar()
            assert run_count == 1

def test_concurrency_same_key_single_run_row():
    for iteration in range(20):
        tenant = f"test_same_{uuid.uuid4().hex[:8]}"
        limit = 10
        fixed_date = date(2026, 10, 20)
        fake_clock = lambda: fixed_date

        def worker():
            return accept_run(
                tenant_id=tenant,
                idempotency_key="duplicate_key",
                operation="validate",
                records=TEST_RECORDS,
                quota_limit=limit,
                clock=fake_clock
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker)
            f2 = executor.submit(worker)
            r1 = f1.result()
            r2 = f2.result()

        results = [r1[0], r2[0]]
        # Exactly one should be ACCEPTED
        assert results.count(AcceptStatus.ACCEPTED) == 1, f"Failed at iteration {iteration}: {results}"
        # The other should be a REPLAY (RUNNING or TERMINAL)
        other_status = r2[0] if r1[0] == AcceptStatus.ACCEPTED else r1[0]
        assert other_status in (AcceptStatus.REPLAY_RUNNING, AcceptStatus.REPLAY_TERMINAL)

        with engine.connect() as conn:
            run_count = conn.execute(text("SELECT count(*) FROM runs WHERE tenant_id = :t AND idempotency_key = 'duplicate_key'"), {"t": tenant}).scalar()
            assert run_count == 1
        assert get_daily_usage(tenant, fixed_date) == 1

def test_utc_day_boundary_fake_clock():
    tenant = f"test_day_{uuid.uuid4().hex[:8]}"
    limit = 3
    day1 = date(2026, 10, 20)
    day2 = date(2026, 10, 21)

    # Day 1: fill quota to 3
    for i in range(3):
        st, r_id, _ = accept_run(tenant, f"d1_key_{i}", "validate", TEST_RECORDS, limit, clock=lambda: day1)
        assert st == AcceptStatus.ACCEPTED
        finish_run(r_id, "Succeeded")

    # Day 1 4th fails
    st4, _, _ = accept_run(tenant, "d1_key_3", "validate", TEST_RECORDS, limit, clock=lambda: day1)
    assert st4 == AcceptStatus.QUOTA_EXHAUSTED

    # Day 2: new day, accepts again!
    st_day2, r_id_day2, _ = accept_run(tenant, "d2_key_0", "validate", TEST_RECORDS, limit, clock=lambda: day2)
    assert st_day2 == AcceptStatus.ACCEPTED
    assert r_id_day2 is not None

    assert get_daily_usage(tenant, day1) == 3
    assert get_daily_usage(tenant, day2) == 1

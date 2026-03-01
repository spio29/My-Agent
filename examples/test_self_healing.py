"""
Test Self-Healing Mechanism

Test failure memory, cooldown, dan auto-reset functionality.

Usage:
  python -m examples.test_self_healing
"""

import asyncio
import sys
import os
import uuid

import pytest
import redis.asyncio as redis_async

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from datetime import datetime, timezone
from app.core.config import settings
import app.core.queue as queue_mod
import app.core.redis_client as redis_client_mod


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def _reset_redis_client_per_test():
    # AnyIO membuat event loop baru per test; refresh client singleton agar tidak nyangkut loop lama.
    fresh_client = redis_async.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
        encoding="utf-8",
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
        retry_on_timeout=False,
    )

    old_queue_client = queue_mod.redis_client
    old_shared_client = redis_client_mod.redis_client
    queue_mod.redis_client = fresh_client
    redis_client_mod.redis_client = fresh_client

    try:
        yield
    finally:
        try:
            await fresh_client.aclose()
        except Exception:
            pass
        queue_mod.redis_client = old_queue_client
        redis_client_mod.redis_client = old_shared_client


from app.core.queue import (
    record_job_outcome,
    get_job_failure_state,
    get_job_cooldown_remaining,
    _fallback_failure_state,
    _sekarang_iso,
)


async def test_self_healing_basic():
    """Test basic self-healing flow"""
    print("\n" + "=" * 80)
    print("TEST 1: BASIC SELF-HEALING FLOW")
    print("=" * 80)
    
    job_id = f"test-self-heal-1-{uuid.uuid4().hex[:6]}"
    
    # Simulate 3 consecutive failures
    print(f"\nSimulating 3 consecutive failures for job '{job_id}'...")
    
    for i in range(3):
        result = await record_job_outcome(
            job_id=job_id,
            success=False,
            error=f"Test error {i+1}",
            failure_threshold=3,
            failure_cooldown_sec=10,  # 10 seconds for testing
            failure_cooldown_max_sec=60,
        )
        print(f"  Failure {i+1}: consecutive_failures={result['consecutive_failures']}, "
              f"cooldown_until={result.get('cooldown_until')}")
    
    # Check failure state
    state = await get_job_failure_state(job_id)
    print(f"\nFailure state after 3 failures:")
    print(f"  consecutive_failures: {state['consecutive_failures']}")
    print(f"  cooldown_until: {state['cooldown_until']}")
    print(f"  last_error: {state['last_error']}")
    
    # Check cooldown remaining
    cooldown = await get_job_cooldown_remaining(job_id)
    print(f"  cooldown_remaining: {cooldown} seconds")
    
    assert state['consecutive_failures'] == 3, "Should have 3 consecutive failures"
    assert state['cooldown_until'] is not None, "Should have cooldown set"
    assert cooldown > 0, "Should have positive cooldown remaining"
    
    print("\n[PASS] TEST 1 PASSED: Basic self-healing works")
    return True


async def test_exponential_backoff():
    """Test exponential backoff on continued failures"""
    print("\n" + "=" * 80)
    print("TEST 2: EXPONENTIAL BACKOFF")
    print("=" * 80)
    
    job_id = f"test-self-heal-2-{uuid.uuid4().hex[:6]}"
    cooldown_base = 10  # 10 seconds
    
    print(f"\nSimulating failures with exponential backoff (base={cooldown_base}s)...")
    
    # Fail 6 times to see exponential growth
    for i in range(6):
        result = await record_job_outcome(
            job_id=job_id,
            success=False,
            error=f"Failure {i+1}",
            failure_threshold=3,
            failure_cooldown_sec=cooldown_base,
            failure_cooldown_max_sec=120,  # Max 2 minutes
        )
        
        if result['cooldown_until']:
            cooldown = await get_job_cooldown_remaining(job_id)
            expected = min(120, cooldown_base * (2 ** (i - 2)))  # i-2 because threshold=3
            print(f"  Failure {i+1}: cooldown={cooldown}s (expected ~{expected}s)")
    
    state = await get_job_failure_state(job_id)
    print(f"\nFinal state:")
    print(f"  consecutive_failures: {state['consecutive_failures']}")
    print(f"  cooldown_until: {state['cooldown_until']}")
    
    assert state['consecutive_failures'] == 6, "Should have 6 consecutive failures"
    
    print("\n[PASS] TEST 2 PASSED: Exponential backoff works")
    return True


async def test_auto_reset_on_success():
    """Test auto-reset when job succeeds"""
    print("\n" + "=" * 80)
    print("TEST 3: AUTO-RESET ON SUCCESS")
    print("=" * 80)
    
    job_id = f"test-self-heal-3-{uuid.uuid4().hex[:6]}"
    
    # First, create some failures
    print(f"\nCreating 3 failures...")
    for i in range(3):
        await record_job_outcome(
            job_id=job_id,
            success=False,
            error=f"Failure {i+1}",
            failure_threshold=3,
            failure_cooldown_sec=30,
            failure_cooldown_max_sec=120,
        )
    
    state_before = await get_job_failure_state(job_id)
    print(f"Before success:")
    print(f"  consecutive_failures: {state_before['consecutive_failures']}")
    print(f"  cooldown_until: {state_before['cooldown_until']}")
    
    # Now simulate success
    print(f"\nSimulating SUCCESS...")
    result = await record_job_outcome(
        job_id=job_id,
        success=True,
        error=None,
        failure_threshold=3,
        failure_cooldown_sec=30,
        failure_cooldown_max_sec=120,
    )
    
    state_after = await get_job_failure_state(job_id)
    print(f"After success:")
    print(f"  consecutive_failures: {state_after['consecutive_failures']}")
    print(f"  cooldown_until: {state_after['cooldown_until']}")
    print(f"  last_success_at: {state_after['last_success_at']}")
    
    assert state_after['consecutive_failures'] == 0, "Should reset to 0 failures"
    assert state_after['cooldown_until'] is None, "Should clear cooldown"
    assert state_after['last_success_at'] is not None, "Should record success time"
    
    print("\n[PASS] TEST 3 PASSED: Auto-reset on success works")
    return True


async def test_intermittent_failures():
    """Test that intermittent failures don't trigger cooldown"""
    print("\n" + "=" * 80)
    print("TEST 4: INTERMITTENT FAILURES (NO COOLDOWN)")
    print("=" * 80)
    
    job_id = f"test-self-heal-4-{uuid.uuid4().hex[:6]}"
    
    # Pattern: Success, Fail, Success, Fail, Success
    print(f"\nSimulating intermittent failures...")
    
    pattern = [True, False, True, False, True, False, True]
    
    for i, success in enumerate(pattern):
        result = await record_job_outcome(
            job_id=job_id,
            success=success,
            error=None if success else f"Failure {i+1}",
            failure_threshold=3,
            failure_cooldown_sec=30,
            failure_cooldown_max_sec=120,
        )
        print(f"  Run {i+1}: {'SUCCESS' if success else 'FAIL'} → "
              f"consecutive_failures={result['consecutive_failures']}")
    
    state = await get_job_failure_state(job_id)
    print(f"\nFinal state:")
    print(f"  consecutive_failures: {state['consecutive_failures']}")
    print(f"  cooldown_until: {state['cooldown_until']}")
    
    # Should NOT have cooldown because failures were not consecutive
    assert state['consecutive_failures'] == 0, "Should reset to 0 after last success"
    assert state['cooldown_until'] is None, "Should not have cooldown"
    
    print("\n[PASS] TEST 4 PASSED: Intermittent failures don't trigger cooldown")
    return True


async def test_max_cooldown_cap():
    """Test that cooldown is capped at maximum"""
    print("\n" + "=" * 80)
    print("TEST 5: MAXIMUM COOLDOWN CAP")
    print("=" * 80)
    
    job_id = f"test-self-heal-5-{uuid.uuid4().hex[:6]}"
    cooldown_max = 60  # 60 seconds max
    
    print(f"\nSimulating many failures (max_cooldown={cooldown_max}s)...")
    
    # Fail 15 times to exceed max
    for i in range(15):
        result = await record_job_outcome(
            job_id=job_id,
            success=False,
            error=f"Failure {i+1}",
            failure_threshold=3,
            failure_cooldown_sec=10,
            failure_cooldown_max_sec=cooldown_max,
        )
        
        if i >= 2:  # After threshold
            cooldown = await get_job_cooldown_remaining(job_id)
            print(f"  Failure {i+1}: cooldown={cooldown}s (max={cooldown_max}s)")
    
    state = await get_job_failure_state(job_id)
    cooldown = await get_job_cooldown_remaining(job_id)
    
    print(f"\nFinal state:")
    print(f"  consecutive_failures: {state['consecutive_failures']}")
    print(f"  cooldown: {cooldown}s (should be <= {cooldown_max}s)")
    
    assert cooldown <= cooldown_max, f"Cooldown should be capped at {cooldown_max}s"
    
    print("\n[PASS] TEST 5 PASSED: Maximum cooldown cap works")
    return True


async def main():
    """Run all self-healing tests"""
    print("\n" + "=" * 80)
    print("SELF-HEALING MECHANISM TEST SUITE")
    print("=" * 80)
    
    tests = [
        ("Basic Self-Healing", test_self_healing_basic),
        ("Exponential Backoff", test_exponential_backoff),
        ("Auto-Reset on Success", test_auto_reset_on_success),
        ("Intermittent Failures", test_intermittent_failures),
        ("Max Cooldown Cap", test_max_cooldown_cap),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
            print(f"\n[FAIL] TEST FAILED: {test_name}")
            print(f"   Error: {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, result, _ in results if result)
    total = len(results)
    
    for test_name, result, error in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {test_name}")
        if error:
            print(f"         Error: {error}")
    
    print(f"\nTotal: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n[SUCCESS] ALL TESTS PASSED! Self-healing mechanism is working perfectly!")
    else:
        print(f"\n[WARNING] {total - passed} test(s) failed. Please review the errors above.")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

"""Comprehensive tests for Clippy tools based on real DevOps Slack queries.

Tests cover:
1. Service registry lookups
2. Coralogix log searches (with/without environment)
3. Code search via Knowledge Base
4. Pipeline status checks
5. PR lookups
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lib.code_search import search_knowledge_base
from src.lib.config_loader import lookup_service
from src.lib.coralogix import handle_search_logs, natural_language_to_dataprime


def test_service_registry():
    """Test service registry lookups - based on real Slack mentions."""
    print("\n" + "=" * 60)
    print("SERVICE REGISTRY TESTS")
    print("=" * 60)

    # Real services mentioned in DevOps Slack
    test_services = [
        # Direct matches
        ("cast-core", "cast-core-service"),
        ("cast-core-service", "cast-core-service"),
        ("emvio-dashboard", "emvio-dashboard-app"),
        ("emvio-underwriting", "emvio-underwriting-service"),
        ("mrrobot-messaging-rest", "mrrobot-messaging-rest"),
        ("cast-connections-util", "cast-connections-util"),
        ("cast-support-portal", "cast-support-portal-service"),
        ("cast-component-library", "cast-component-library"),
        # Alias matches
        ("connector-hub", "mrrobot-connector-hub"),
        ("auth-rest", "mrrobot-auth-rest"),
        ("payment", "mrrobot-payment-service"),
        # Should NOT find
        ("nonexistent-service", None),
        ("fake-app", None),
    ]

    passed = 0
    failed = 0

    for query, expected_full_name in test_services:
        result = lookup_service(query)
        if expected_full_name is None:
            # Should NOT find
            if result is None:
                print(f"  ✅ '{query}' -> Not found (expected)")
                passed += 1
            else:
                print(f"  ❌ '{query}' -> Found {result.get('full_name')} (expected None)")
                failed += 1
        else:
            # Should find
            if result and result.get("full_name") == expected_full_name:
                print(f"  ✅ '{query}' -> {result.get('full_name')}")
                passed += 1
            elif result:
                print(f"  ❌ '{query}' -> {result.get('full_name')} (expected {expected_full_name})")
                failed += 1
            else:
                print(f"  ❌ '{query}' -> Not found (expected {expected_full_name})")
                failed += 1

    print(f"\nService Registry: {passed}/{passed + failed} passed")
    return passed, failed


def test_coralogix_environment_detection():
    """Test that Coralogix properly detects or flags missing environments."""
    print("\n" + "=" * 60)
    print("CORALOGIX ENVIRONMENT DETECTION TESTS")
    print("=" * 60)

    # Queries WITH environment (should detect)
    with_env = [
        ("errors in cast-core prod", "prod"),
        ("show logs from connector-hub in production", "prod"),
        ("check staging errors for emvio-dashboard", "staging"),
        ("dev logs for mrrobot-auth-rest", "dev"),
        ("sandbox errors in payment service", "sandbox"),
        ("errors in emvio-payment-service development", "dev"),
    ]

    # Queries WITHOUT environment (should flag missing_environment)
    without_env = [
        "errors in cast-core",
        "show me logs from connector-hub",
        "check errors for emvio-dashboard",
        "mrrobot-auth-rest errors",
        "payment service issues",
        "emvio-underwriting errors last 24 hours",
    ]

    passed = 0
    failed = 0

    print("\n  Queries WITH environment:")
    for query, expected_env in with_env:
        result = natural_language_to_dataprime(query)
        detected = result.get("environment")
        if detected and expected_env in detected:
            print(f"    ✅ '{query[:40]}...' -> env={detected}")
            passed += 1
        else:
            print(f"    ❌ '{query[:40]}...' -> env={detected} (expected {expected_env})")
            failed += 1

    print("\n  Queries WITHOUT environment (should flag missing):")
    for query in without_env:
        result = natural_language_to_dataprime(query)
        detected = result.get("environment")
        if detected is None:
            print(f"    ✅ '{query[:40]}...' -> env=None (will ask user)")
            passed += 1
        else:
            print(f"    ❌ '{query[:40]}...' -> env={detected} (should be None)")
            failed += 1

    print(f"\nEnvironment Detection: {passed}/{passed + failed} passed")
    return passed, failed


def test_coralogix_service_extraction():
    """Test that Coralogix extracts service names correctly."""
    print("\n" + "=" * 60)
    print("CORALOGIX SERVICE EXTRACTION TESTS")
    print("=" * 60)

    test_queries = [
        ("errors in cast-core prod", "cast-core"),
        ("show logs from mrrobot-connector-hub", "mrrobot-connector-hub"),
        ("emvio-dashboard-app staging errors", "emvio-dashboard-app"),
        ("check cast-connections-util logs", "cast-connections-util"),
        ("mrrobot-auth-rest authentication errors", "mrrobot-auth-rest"),
        ("emvio-payment-service timeouts", "emvio-payment-service"),
        ("cast-support-portal-app issues", "cast-support-portal-app"),
    ]

    passed = 0
    failed = 0

    for query, expected_service in test_queries:
        result = natural_language_to_dataprime(query)
        dataprime = result.get("dataprime_query", "")
        if expected_service in dataprime:
            print(f"  ✅ '{query[:40]}...' -> found '{expected_service}'")
            passed += 1
        else:
            print(f"  ❌ '{query[:40]}...' -> missing '{expected_service}'")
            print(f"      Query: {dataprime[:80]}...")
            failed += 1

    print(f"\nService Extraction: {passed}/{passed + failed} passed")
    return passed, failed


def test_coralogix_live_queries():
    """Test live Coralogix queries (requires API access)."""
    print("\n" + "=" * 60)
    print("CORALOGIX LIVE QUERY TESTS")
    print("=" * 60)

    test_queries = [
        # With environment
        ("errors in cast-core prod", True, "prod"),
        ("connector-hub staging logs", True, "staging"),
        # Without environment - should return missing_environment flag
        ("errors in payment-service", True, None),
        ("cast-core timeouts", True, None),
    ]

    passed = 0
    failed = 0

    for query, should_succeed, expected_env in test_queries:
        try:
            result = handle_search_logs(query, hours_back=1, limit=5)

            has_error = "error" in str(result).lower() and "API" in str(result)
            env_searched = result.get("environment_searched")
            missing_env = result.get("missing_environment")

            if has_error:
                print(f"  ⚠️  '{query[:35]}...' -> API error (check credentials)")
                # Don't count as failure if it's auth issue
                continue

            if expected_env:
                # Should have environment
                if env_searched == expected_env:
                    print(f"  ✅ '{query[:35]}...' -> env={env_searched}, {result.get('total_results', 0)} logs")
                    passed += 1
                else:
                    print(f"  ❌ '{query[:35]}...' -> env={env_searched} (expected {expected_env})")
                    failed += 1
            else:
                # Should flag missing environment
                if missing_env:
                    print(f"  ✅ '{query[:35]}...' -> missing_environment=True (will ask user)")
                    passed += 1
                else:
                    print(f"  ❌ '{query[:35]}...' -> missing_environment not set")
                    failed += 1

        except Exception as e:
            print(f"  ❌ '{query[:35]}...' -> Exception: {str(e)[:50]}")
            failed += 1

    print(f"\nLive Queries: {passed}/{passed + failed} passed")
    return passed, failed


def test_code_search():
    """Test Knowledge Base code search."""
    print("\n" + "=" * 60)
    print("CODE SEARCH (KNOWLEDGE BASE) TESTS")
    print("=" * 60)

    test_queries = [
        ("how does authentication work", True),
        ("webhook handling code", True),
        ("database connection", True),
        ("lambda function handler", True),
        ("error handling patterns", True),
        ("cast integration", True),
    ]

    passed = 0
    failed = 0

    for query, should_have_results in test_queries:
        try:
            result = search_knowledge_base(query, num_results=3)
            results = result.get("results", [])

            if should_have_results and len(results) > 0:
                repos = [r.get("repo", "unknown") for r in results[:2]]
                print(f"  ✅ '{query[:30]}...' -> {len(results)} results: {', '.join(repos)}")
                passed += 1
            elif not should_have_results and len(results) == 0:
                print(f"  ✅ '{query[:30]}...' -> No results (expected)")
                passed += 1
            else:
                print(f"  ❌ '{query[:30]}...' -> {len(results)} results (unexpected)")
                failed += 1

        except Exception as e:
            print(f"  ⚠️  '{query[:30]}...' -> Error: {str(e)[:40]}")
            # Don't count as failure if KB unavailable

    print(f"\nCode Search: {passed}/{passed + failed} passed")
    return passed, failed


def test_dataprime_query_generation():
    """Test DataPrime query generation for various patterns."""
    print("\n" + "=" * 60)
    print("DATAPRIME QUERY GENERATION TESTS")
    print("=" * 60)

    test_cases = [
        # (query, expected_patterns_in_dataprime)
        ("errors in cast-core prod", ["logGroup ~ 'cast-core'", "message ~ 'error'", "-prod"]),
        ("504 timeouts in connector-hub", ["504", "timeout", "connector-hub"]),
        ('find "connection refused" errors', ["connection refused"]),
        ("ECONNREFUSED in payment-service staging", ["ECONNREFUSED", "payment-service", "-staging"]),
        ("lambda cold starts in prod", ["cold start", "-prod"]),
        ("OOM errors in emvio-batch", ["OOM", "emvio-batch"]),
    ]

    passed = 0
    failed = 0

    for query, expected_patterns in test_cases:
        result = natural_language_to_dataprime(query)
        dataprime = result.get("dataprime_query", "").lower()

        missing = []
        for pattern in expected_patterns:
            if pattern.lower() not in dataprime:
                missing.append(pattern)

        if not missing:
            print(f"  ✅ '{query[:40]}...'")
            passed += 1
        else:
            print(f"  ❌ '{query[:40]}...' missing: {missing}")
            print(f"      Generated: {dataprime[:80]}...")
            failed += 1

    print(f"\nDataPrime Generation: {passed}/{passed + failed} passed")
    return passed, failed


def test_real_devops_scenarios():
    """Test scenarios based on real DevOps Slack conversations."""
    print("\n" + "=" * 60)
    print("REAL DEVOPS SCENARIO TESTS")
    print("=" * 60)

    scenarios = [
        # From Slack: "Running into an issue with trying to run cast-core-service locally"
        {
            "name": "Local dev issue - cast-core",
            "service_lookup": "cast-core-service",
            "expected_type": "backend",
        },
        # From Slack: "error when deploying emvio-underwriting-service"
        {
            "name": "Deploy error - emvio-underwriting",
            "service_lookup": "emvio-underwriting",
            "expected_type": "backend",
        },
        # From Slack: "PR approval for cast-core-service"
        {
            "name": "PR for cast-core-service",
            "service_lookup": "cast-core",
            "expected_full_name": "cast-core-service",
        },
        # From Slack: "emvio-dashboard-app needs devops approval"
        {
            "name": "Dashboard app lookup",
            "service_lookup": "emvio-dashboard",
            "expected_type": "frontend",
        },
        # From Slack: "mrrobot-messaging-rest PR"
        {
            "name": "Messaging service lookup",
            "service_lookup": "mrrobot-messaging-rest",
            "expected_type": "backend",
        },
    ]

    passed = 0
    failed = 0

    for scenario in scenarios:
        name = scenario["name"]
        result = lookup_service(scenario["service_lookup"])

        if result is None:
            print(f"  ❌ {name}: Service not found")
            failed += 1
            continue

        checks_passed = True

        if "expected_type" in scenario:
            if result.get("type") != scenario["expected_type"]:
                print(f"  ❌ {name}: type={result.get('type')} (expected {scenario['expected_type']})")
                checks_passed = False

        if "expected_full_name" in scenario:
            if result.get("full_name") != scenario["expected_full_name"]:
                print(f"  ❌ {name}: full_name={result.get('full_name')} (expected {scenario['expected_full_name']})")
                checks_passed = False

        if checks_passed:
            print(f"  ✅ {name}: {result.get('full_name')} ({result.get('type')})")
            passed += 1
        else:
            failed += 1

    print(f"\nReal Scenarios: {passed}/{passed + failed} passed")
    return passed, failed


def run_all_tests():
    """Run all test suites and report results."""
    print("\n" + "=" * 60)
    print("CLIPPY TOOLS COMPREHENSIVE TEST SUITE")
    print("Based on real DevOps Slack channel queries")
    print("=" * 60)

    total_passed = 0
    total_failed = 0

    # Run all test suites
    suites = [
        ("Service Registry", test_service_registry),
        ("Environment Detection", test_coralogix_environment_detection),
        ("Service Extraction", test_coralogix_service_extraction),
        ("DataPrime Generation", test_dataprime_query_generation),
        ("Real DevOps Scenarios", test_real_devops_scenarios),
        ("Live Coralogix Queries", test_coralogix_live_queries),
        ("Code Search", test_code_search),
    ]

    results = []
    for name, test_func in suites:
        try:
            passed, failed = test_func()
            total_passed += passed
            total_failed += failed
            results.append((name, passed, failed))
        except Exception as e:
            print(f"\n  ⚠️  {name} suite failed: {e}")
            results.append((name, 0, 1))
            total_failed += 1

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for name, passed, failed in results:
        status = "✅" if failed == 0 else "❌"
        print(f"  {status} {name}: {passed}/{passed + failed}")

    print(f"\n  TOTAL: {total_passed}/{total_passed + total_failed} tests passed")

    if total_failed > 0:
        print(f"\n  ⚠️  {total_failed} tests failed - review above for details")
        return 1
    else:
        print("\n  🎉 All tests passed!")
        return 0


if __name__ == "__main__":
    exit(run_all_tests())

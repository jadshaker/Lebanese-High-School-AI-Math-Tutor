#!/bin/bash

# Script to run unit tests for all services
# Tests are run per service to avoid sys.path conflicts

set -e  # Exit on error

echo "Running unit tests for all microservices..."
echo "==========================================="
echo ""

FAILED_SERVICES=()
PASSED_SERVICES=()

# Function to run tests for a service
run_service_tests() {
    local service=$1
    echo "Testing $service service..."
    if python3.14 -m pytest tests/unit/test_services/test_${service}.py -v -m unit --tb=short; then
        PASSED_SERVICES+=("$service")
        echo "✓ $service tests passed"
    else
        FAILED_SERVICES+=("$service")
        echo "✗ $service tests failed"
    fi
    echo ""
}

# Run tests for each service
run_service_tests "cache"
run_service_tests "embedding"
run_service_tests "large_llm"
run_service_tests "small_llm"
run_service_tests "fine_tuned_model"
run_service_tests "input_processor"
run_service_tests "reformulator"
run_service_tests "gateway"

# Summary
echo "==========================================="
echo "Test Summary:"
echo "==========================================="
echo "Passed: ${#PASSED_SERVICES[@]}/8 services"
for service in "${PASSED_SERVICES[@]}"; do
    echo "  ✓ $service"
done

if [ ${#FAILED_SERVICES[@]} -gt 0 ]; then
    echo ""
    echo "Failed: ${#FAILED_SERVICES[@]}/8 services"
    for service in "${FAILED_SERVICES[@]}"; do
        echo "  ✗ $service"
    done
    exit 1
fi

echo ""
echo "All service tests passed! 🎉"

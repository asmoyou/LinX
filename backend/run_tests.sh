#!/bin/bash
# Test runner script for LinX backend
# Usage: ./run_tests.sh [test-type] [options]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
TEST_TYPE="all"
COVERAGE=false
VERBOSE=false
PARALLEL=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        unit|integration|e2e|performance|security)
            TEST_TYPE=$1
            shift
            ;;
        --coverage|-c)
            COVERAGE=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --parallel|-p)
            PARALLEL=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./run_tests.sh [test-type] [options]"
            echo ""
            echo "Test types:"
            echo "  unit          Run unit tests only"
            echo "  integration   Run integration tests only"
            echo "  e2e           Run end-to-end tests only"
            echo "  performance   Run performance tests only"
            echo "  security      Run security tests only"
            echo "  all           Run all tests (default)"
            echo ""
            echo "Options:"
            echo "  -c, --coverage    Generate coverage report"
            echo "  -v, --verbose     Verbose output"
            echo "  -p, --parallel    Run tests in parallel"
            echo "  -h, --help        Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./run_tests.sh                    # Run all tests"
            echo "  ./run_tests.sh unit               # Run unit tests only"
            echo "  ./run_tests.sh unit --coverage    # Run unit tests with coverage"
            echo "  ./run_tests.sh --coverage         # Run all tests with coverage"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Build pytest command
PYTEST_CMD="pytest"

# Add test path based on type
case $TEST_TYPE in
    unit)
        PYTEST_CMD="$PYTEST_CMD tests/unit"
        ;;
    integration)
        PYTEST_CMD="$PYTEST_CMD tests/integration"
        ;;
    e2e)
        PYTEST_CMD="$PYTEST_CMD tests/e2e"
        ;;
    performance)
        PYTEST_CMD="$PYTEST_CMD tests/performance"
        ;;
    security)
        PYTEST_CMD="$PYTEST_CMD tests/security"
        ;;
    all)
        PYTEST_CMD="$PYTEST_CMD tests/"
        ;;
esac

# Add coverage options
if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=. --cov-report=html --cov-report=term"
fi

# Add verbose option
if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

# Add parallel option
if [ "$PARALLEL" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -n auto"
fi

# Print header
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}LinX Backend Test Runner${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo -e "Test type: ${YELLOW}$TEST_TYPE${NC}"
echo -e "Coverage:  ${YELLOW}$COVERAGE${NC}"
echo -e "Verbose:   ${YELLOW}$VERBOSE${NC}"
echo -e "Parallel:  ${YELLOW}$PARALLEL${NC}"
echo ""
echo -e "Command: ${YELLOW}$PYTEST_CMD${NC}"
echo ""

# Run tests
echo -e "${GREEN}Running tests...${NC}"
echo ""

if eval $PYTEST_CMD; then
    echo ""
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}✅ All tests passed!${NC}"
    echo -e "${GREEN}================================${NC}"
    
    if [ "$COVERAGE" = true ]; then
        echo ""
        echo -e "${YELLOW}Coverage report generated in: htmlcov/index.html${NC}"
    fi
    
    exit 0
else
    echo ""
    echo -e "${RED}================================${NC}"
    echo -e "${RED}❌ Some tests failed!${NC}"
    echo -e "${RED}================================${NC}"
    exit 1
fi

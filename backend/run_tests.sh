#!/bin/bash
# Comprehensive test runner script for LinX (灵枢)
# This script runs all unit tests and generates coverage reports

set -e

echo "=== LinX (灵枢) - Test Runner ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}Warning: Virtual environment not activated${NC}"
    echo "Activating virtual environment..."
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    elif [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    else
        echo -e "${RED}Error: Virtual environment not found${NC}"
        echo "Please create a virtual environment first:"
        echo "  python3 -m venv .venv"
        echo "  source .venv/bin/activate"
        echo "  pip install -r requirements.txt"
        echo "  pip install -r requirements-dev.txt"
        exit 1
    fi
fi

# Check if pytest is installed
if ! python -c "import pytest" 2>/dev/null; then
    echo -e "${RED}Error: pytest not installed${NC}"
    echo "Installing test dependencies..."
    pip install -r requirements-dev.txt
fi

# Parse command line arguments
TEST_PATH="${1:-.}"
COVERAGE_MIN="${2:-80}"
VERBOSE=""
MARKERS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        -vv|--very-verbose)
            VERBOSE="-vv"
            shift
            ;;
        -m|--marker)
            MARKERS="-m $2"
            shift 2
            ;;
        -k|--keyword)
            MARKERS="-k $2"
            shift 2
            ;;
        --fast)
            MARKERS="-m 'not slow'"
            shift
            ;;
        --slow)
            MARKERS="-m slow"
            shift
            ;;
        *)
            TEST_PATH="$1"
            shift
            ;;
    esac
done

echo "Test Configuration:"
echo "  Test Path: $TEST_PATH"
echo "  Coverage Minimum: ${COVERAGE_MIN}%"
echo "  Verbose: ${VERBOSE:-No}"
echo "  Markers: ${MARKERS:-None}"
echo ""

# Run tests with coverage
echo -e "${GREEN}Running tests...${NC}"
echo ""

pytest $TEST_PATH \
    --cov=. \
    --cov-report=term-missing \
    --cov-report=html \
    --cov-report=xml \
    --cov-fail-under=$COVERAGE_MIN \
    $VERBOSE \
    $MARKERS \
    || TEST_FAILED=1

echo ""

if [ -n "$TEST_FAILED" ]; then
    echo -e "${RED}✗ Tests failed${NC}"
    exit 1
else
    echo -e "${GREEN}✓ All tests passed${NC}"
fi

# Display coverage summary
echo ""
echo "=== Coverage Summary ==="
echo ""
python -c "
import xml.etree.ElementTree as ET
try:
    tree = ET.parse('coverage.xml')
    root = tree.getroot()
    line_rate = float(root.attrib['line-rate']) * 100
    branch_rate = float(root.attrib['branch-rate']) * 100
    print(f'Line Coverage: {line_rate:.2f}%')
    print(f'Branch Coverage: {branch_rate:.2f}%')
    if line_rate >= $COVERAGE_MIN:
        print('\033[0;32m✓ Coverage target met\033[0m')
    else:
        print(f'\033[0;31m✗ Coverage below target ({$COVERAGE_MIN}%)\033[0m')
except:
    print('Coverage report not available')
"

echo ""
echo "Detailed coverage report: htmlcov/index.html"
echo ""

# Run specific test suites
echo "=== Test Suite Summary ==="
echo ""

# Count tests by category
echo "Test counts by module:"
find . -name "test_*.py" -type f | while read file; do
    module=$(dirname "$file" | sed 's|^\./||')
    count=$(grep -c "def test_" "$file" 2>/dev/null || echo 0)
    if [ "$count" -gt 0 ]; then
        echo "  $module: $count tests"
    fi
done | sort

echo ""
echo -e "${GREEN}Test run complete!${NC}"

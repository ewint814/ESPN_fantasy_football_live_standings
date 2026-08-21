#!/bin/bash
# Quick test script for Fantasy Football Tracker
# Tests the app without starting a full web server

echo "======================================"
echo "Fantasy Football Tracker - Quick Test"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Python version
echo "1️⃣  Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1)
if [[ $? -eq 0 ]]; then
    echo -e "   ${GREEN}✅ $PYTHON_VERSION${NC}"
else
    echo -e "   ${RED}❌ Python not found${NC}"
    exit 1
fi

# Test 2: Dependencies
echo ""
echo "2️⃣  Checking dependencies..."
DEPS_OK=true
for dep in flask requests espn-api python-dotenv gunicorn; do
    if pip3 show $dep &> /dev/null; then
        echo -e "   ${GREEN}✅ $dep installed${NC}"
    else
        echo -e "   ${RED}❌ $dep NOT installed${NC}"
        DEPS_OK=false
    fi
done

if [ "$DEPS_OK" = false ]; then
    echo ""
    echo -e "${YELLOW}Installing missing dependencies...${NC}"
    pip3 install -q -r requirements.txt
fi

# Test 3: File structure
echo ""
echo "3️⃣  Checking file structure..."
FILES=("fantasy_tracker.py" "config.py" "nfl_utils.py" "requirements.txt" ".env.example")
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "   ${GREEN}✅ $file exists${NC}"
    else
        echo -e "   ${RED}❌ $file missing${NC}"
        exit 1
    fi
done

# Test 4: Python syntax
echo ""
echo "4️⃣  Checking Python syntax..."
if python3 -m py_compile fantasy_tracker.py config.py nfl_utils.py 2>&1; then
    echo -e "   ${GREEN}✅ All Python files are valid${NC}"
else
    echo -e "   ${RED}❌ Syntax errors found${NC}"
    exit 1
fi

# Test 5: Run unit tests
echo ""
echo "5️⃣  Running unit tests..."
if [ -f "test_app.py" ]; then
    python3 test_app.py
    if [[ $? -eq 0 ]]; then
        echo -e "   ${GREEN}✅ All unit tests passed${NC}"
    else
        echo -e "   ${RED}❌ Some unit tests failed${NC}"
        exit 1
    fi
else
    echo -e "   ${YELLOW}⚠️  test_app.py not found, skipping${NC}"
fi

# Test 6: Check for .env file
echo ""
echo "6️⃣  Checking configuration..."
if [ -f ".env" ]; then
    echo -e "   ${GREEN}✅ .env file exists${NC}"
    
    # Check if it has the required variables
    if grep -q "ESPN_LEAGUE_ID" .env && grep -q "ESPN_S2" .env && grep -q "ESPN_SWID" .env; then
        echo -e "   ${GREEN}✅ All required variables present${NC}"
        HAS_CREDENTIALS=true
    else
        echo -e "   ${YELLOW}⚠️  .env file incomplete${NC}"
        HAS_CREDENTIALS=false
    fi
else
    echo -e "   ${YELLOW}⚠️  No .env file found${NC}"
    echo "   📝 Copy .env.example to .env and add your ESPN credentials"
    HAS_CREDENTIALS=false
fi

# Summary
echo ""
echo "======================================"
echo "Test Summary"
echo "======================================"
echo ""

if [ "$HAS_CREDENTIALS" = true ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    echo ""
    echo "Ready to run with:"
    echo "  python3 fantasy_tracker.py"
    echo ""
    echo "Or with Docker:"
    echo "  docker build -t fantasy-tracker ."
    echo "  docker run -p 5000:5000 --env-file .env fantasy-tracker"
else
    echo -e "${YELLOW}⚠️  Almost ready!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. cp .env.example .env"
    echo "  2. Edit .env with your ESPN credentials"
    echo "  3. python3 fantasy_tracker.py"
fi

echo ""
echo "📚 For detailed testing instructions, see: TESTING.md"
echo ""

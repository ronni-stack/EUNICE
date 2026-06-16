#!/bin/bash
cd ~/EUNICE_MASTER
API_KEY="eun_f56ea9a4a0b06a863dd82a24ca1f3381"
BASE="http://localhost:8000"

echo "=== 1. HEALTH ==="
curl -s $BASE/health | python3 -m json.tool

echo ""
echo "=== 2. STORE FACT ==="
curl -s -X POST $BASE/chat -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"message":"remember that my car is a Tesla Model 3","session":"test"}' | python3 -m json.tool

echo ""
echo "=== 3. RECALL ==="
curl -s -X POST $BASE/chat -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"message":"what car do I drive","session":"test"}' | python3 -m json.tool

echo ""
echo "=== 4. BALANCE (should ask confirm) ==="
curl -s -X POST $BASE/chat -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"message":"what is my balance","session":"test"}' | python3 -m json.tool

echo ""
echo "=== 5. CONFIRM BALANCE ==="
curl -s -X POST $BASE/chat -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"message":"confirm get_balance","session":"test"}' | python3 -m json.tool

echo ""
echo "=== 6. TRANSFER (should deny) ==="
curl -s -X POST $BASE/chat -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"message":"transfer $100 to Bob","session":"test"}' | python3 -m json.tool

echo ""
echo "=== 7. UNKNOWN FACT ==="
curl -s -X POST $BASE/chat -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"message":"what is my sisters name","session":"test"}' | python3 -m json.tool

echo ""
echo "=== 8. TRAILS ==="
curl -s -H "Authorization: Bearer $API_KEY" $BASE/trails | python3 -m json.tool

echo ""
echo "=== 9. DAEMON STATUS ==="
curl -s -H "Authorization: Bearer $API_KEY" $BASE/daemon/status | python3 -m json.tool

echo ""
echo "=== 10. STREAMING ==="
echo "First 5 tokens:"
curl -s -N -X POST $BASE/chat/stream -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"message":"hello EUNICE","session":"test"}' | grep -o '"token": "[^"]*"' | head -5 | sed 's/"token": "//;s/"//'
echo "..."

echo ""
echo "=== TEST COMPLETE ==="

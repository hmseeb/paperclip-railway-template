#!/bin/sh
# Stranger journey against a fresh Paperclip deploy: usage: journey.sh <base-url>
# Proves: sign-up alone gives no admin, browser claim -> instance admin, company create +
# read back, second visitor cannot claim or read the owner's company, SPA served.
set -eu
U=$1; J=$(mktemp -d)
H="-H Content-Type:application/json -H Origin:$U"
pass(){ echo "PASS $*"; }; fail(){ echo "FAIL $*"; exit 1; }
curl -fsS "$U/api/health" | grep -q '"bootstrapStatus":"bootstrap_pending"' && pass "pending before claim" || fail "not pending"
curl -fsS "$U/api/health" | grep -q '"deploymentExposure":"private"' && pass "private exposure" || fail "exposure"
curl -fsS "$U/" | grep -qi '<div id="root"' && pass "SPA served" || fail "no SPA"
E="owner-$(date +%s)@example.com"
curl -fsS -c $J/a $H "$U/api/auth/sign-up/email" -d "{\"email\":\"$E\",\"password\":\"Sup3r-secret-pw!\",\"name\":\"Owner\"}" >/dev/null && pass "owner sign-up"
C=$(curl -s -o /dev/null -w '%{http_code}' -b $J/a $H "$U/api/companies" -d '{"name":"Before Claim"}')
[ "$C" -ge 400 ] && pass "company create refused before claim ($C)" || fail "company create allowed before claim ($C)"
curl -fsS -b $J/a $H -X POST "$U/api/bootstrap/claim" | grep -q '"claimed":true' && pass "browser claim" || fail "claim"
curl -fsS "$U/api/health" | grep -q '"bootstrapStatus":"ready"' && pass "health ready after claim" || fail "still pending"
ID=$(curl -fsS -b $J/a $H "$U/api/companies" -d '{"name":"Acme Robots","description":"journey test"}' | sed -E 's/.*"id":"([^"]+)".*/\1/')
[ -n "$ID" ] && pass "company created $ID"
curl -fsS -b $J/a "$U/api/companies/$ID" | grep -q "Acme Robots" && pass "company read back"
curl -fsS -c $J/b $H "$U/api/auth/sign-up/email" -d "{\"email\":\"x$E\",\"password\":\"Sup3r-secret-pw!\",\"name\":\"Stranger\"}" >/dev/null
C=$(curl -s -o /dev/null -w '%{http_code}' -b $J/b $H -X POST "$U/api/bootstrap/claim")
[ "$C" = 409 ] && pass "second claim refused ($C)" || fail "second claim ($C)"
C=$(curl -s -o /dev/null -w '%{http_code}' -b $J/b "$U/api/companies/$ID")
[ "$C" -ge 400 ] && pass "2nd user cannot read owner company ($C)" || fail "2nd user reads company ($C)"

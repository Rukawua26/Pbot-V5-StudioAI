#!/usr/bin/env bash
# Run the opt-in Binance Futures TESTNET e2e tests (sandbox mode, no real funds).
# Prompts for dedicated testnet keys without echoing either; nothing is written to disk.
set -euo pipefail
cd "$(dirname "$0")/.."

read -r -s -p "Testnet API key: " BINANCE_TESTNET_API_KEY
echo
read -r -s -p "Testnet API secret: " BINANCE_TESTNET_API_SECRET
echo
export BINANCE_TESTNET_API_KEY BINANCE_TESTNET_API_SECRET
export RUN_BINANCE_TESTNET_E2E=true SNIPER_DISABLE_FILE_TELEMETRY=1

./.venv/bin/python -m unittest -v \
  tests.integration.test_binance_testnet_wallet_sync_sl_repair \
  tests.integration.test_binance_testnet_execution_flow

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
source "$ROOT/toolchain/toolchain.env"

if [ "$#" -ne 1 ]; then
  echo "usage: $0 TOOL_DIRECTORY" >&2
  exit 2
fi

TOOL_DIR="$1"
mkdir -p "$TOOL_DIR"

download() {
  url="$1"
  expected_sha256="$2"
  destination="$3"

  if [ -f "$destination" ] && echo "$expected_sha256  $destination" | sha256sum --check --status; then
    return
  fi

  partial="${destination}.partial"
  curl \
    --fail \
    --location \
    --connect-timeout 15 \
    --max-time 900 \
    --retry 3 \
    --retry-all-errors \
    --silent \
    --show-error \
    --continue-at - \
    "$url" \
    --output "$partial"
  if ! echo "$expected_sha256  $partial" | sha256sum --check --status; then
    rm -f "$partial"
    echo "download digest mismatch: $url" >&2
    return 1
  fi
  chmod 0755 "$partial"
  mv "$partial" "$destination"
}

download \
  "$GOOSE_LINUX_ARM64_URL" \
  "$GOOSE_LINUX_ARM64_SHA256" \
  "$TOOL_DIR/goose"

STATICCHECK_ARCHIVE="$TOOL_DIR/staticcheck-${STATICCHECK_VERSION}-linux-arm64.tar.gz"
download \
  "$STATICCHECK_LINUX_ARM64_URL" \
  "$STATICCHECK_LINUX_ARM64_SHA256" \
  "$STATICCHECK_ARCHIVE"

EXTRACT_DIR="$(mktemp -d "$TOOL_DIR/.staticcheck.XXXXXX")"
trap 'rm -rf "$EXTRACT_DIR"' RETURN
tar -xzf "$STATICCHECK_ARCHIVE" -C "$EXTRACT_DIR"
install -m 0755 "$EXTRACT_DIR/staticcheck/staticcheck" "$TOOL_DIR/staticcheck"
trap - RETURN
rm -rf "$EXTRACT_DIR"

test "$("$TOOL_DIR/goose" -version 2>&1)" = "goose version: v$GOOSE_VERSION"
"$TOOL_DIR/staticcheck" -version | grep -F "staticcheck $STATICCHECK_VERSION" >/dev/null

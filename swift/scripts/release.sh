#!/bin/bash
# Builds the app and zips it for a GitHub Release. Prints the gh command; does not publish.
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/make-app.sh
V="$(tr -d '[:space:]' < ../VERSION)"
ZIP="build/HiveMac-${V}-macOS.zip"
rm -f "$ZIP"
ditto -c -k --keepParent build/HiveMac.app "$ZIP"
echo "Built swift/$ZIP"
echo "Publish with: gh release create v${V} swift/${ZIP} --prerelease --title \"HiveMac ${V} (beta)\""

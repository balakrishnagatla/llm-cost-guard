#!/bin/bash
# Publish docs/ to the GitHub wiki.
# One-time setup: open the repo's Wiki tab and click "Create the first page" -> "Save page".
set -euo pipefail

REPO="${REPO:-balakrishnagatla/llm-cost-guard}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git clone -q "https://github.com/${REPO}.wiki.git" "$WORK/wiki"

for f in "$ROOT"/docs/*.md; do
  # Wiki links have no .md extension; repo-relative links need full GitHub URLs.
  sed -e 's/(\([A-Za-z0-9_-]*\)\.md)/(\1)/g' \
      -e "s#(\.\./\([^)]*\))#(https://github.com/${REPO}/blob/main/\1)#g" \
      "$f" > "$WORK/wiki/$(basename "$f")"
done

cd "$WORK/wiki"
git add -A
if git diff --cached --quiet; then
  echo "Wiki is already up to date."
else
  git commit -q -m "Update wiki from docs/"
  git push -q
  echo "Wiki published: https://github.com/${REPO}/wiki"
fi

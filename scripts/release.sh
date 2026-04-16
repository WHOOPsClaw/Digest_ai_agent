#!/bin/bash
# Usage: ./scripts/release.sh 0.1.0

set -e

VERSION=$1
if [ -z "$VERSION" ]; then
  echo "Usage: $0 <version>"
  exit 1
fi

# Detect sed in-place flavor (BSD/macOS vs GNU)
if sed --version >/dev/null 2>&1; then
  SED_INPLACE=(-i)
else
  SED_INPLACE=(-i "")
fi

# Update version in pyproject.toml
sed "${SED_INPLACE[@]}" "s/^version = .*/version = \"$VERSION\"/" pyproject.toml
sed "${SED_INPLACE[@]}" "s/__version__ = .*/__version__ = \"$VERSION\"/" newsbrief/__init__.py

# Update CHANGELOG (if present)
if [ -f CHANGELOG.md ]; then
  sed "${SED_INPLACE[@]}" "s/## \[Unreleased\]/## [Unreleased]\n\n## [$VERSION] - $(date +%Y-%m-%d)/" CHANGELOG.md
  git add CHANGELOG.md
fi

# Commit + tag
git add pyproject.toml newsbrief/__init__.py
git commit -m "Release v$VERSION"
git tag "v$VERSION"

echo "Release v$VERSION prepared"
echo ""
echo "Next:"
echo "  git push origin main --tags"
echo "  Create GitHub Release from tag v$VERSION"

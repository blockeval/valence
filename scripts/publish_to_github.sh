#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 git@github.com:OWNER/valence.git" >&2
  exit 2
fi

REMOTE_URL="$1"

if [[ ! -d .git ]]; then
  git init
  git branch -M main
fi

git add .
if ! git diff --cached --quiet; then
  git commit -m "Release VALENCE v0.8.0"
fi

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

if ! git rev-parse v0.8.0 >/dev/null 2>&1; then
  git tag -a v0.8.0 -m "VALENCE v0.8.0 public research release"
fi

git push -u origin main
git push origin v0.8.0

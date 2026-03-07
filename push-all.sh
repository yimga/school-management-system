#!/bin/bash
# Commit and push all (including untracked). nul is in .gitignore.
cd "$(dirname "$0")"
git add -A
git status -s
git commit -m "Commit all: untracked and modified files"
git pull --rebase origin main
git push origin main

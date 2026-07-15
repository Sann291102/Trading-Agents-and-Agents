#!/bin/sh
# The preview tool spawns this with an inherited cwd under a macOS
# TCC-protected directory (~/Desktop), which can hang/break Node's own
# internal process.cwd() calls even when every path argument passed to the
# program itself is absolute. `cd` to an absolute path first -- chdir() to
# a new absolute path doesn't require reading the old cwd, so this
# succeeds where staying put and passing absolute args alone did not.
cd /Users/vivek/ai-organization/frontend || exit 1
exec node_modules/.bin/next dev --port 3000

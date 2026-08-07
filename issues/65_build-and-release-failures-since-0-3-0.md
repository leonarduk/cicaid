# 65 — Build and Release Failures Since 0.3.0

**URL:** https://github.com/leonarduk/cicaid/issues/65
**Labels:** bug, Medium Value
**State:** open

## What

Builds and releases have been failing since version 0.3.0.

## Why

Unable to create a wheel package successfully.

## How

1. When tagging the code for a release, the build process was triggered but failed to create a duplicate tag.
2. After removing the duplicate tag, the build failed to update the README file.
3. Upon attempting to update the README and removing it again, the build is now failing to generate a wheel package.

## Files Affected

- Unknown

## Constraints

None

## LLM tier

sonnet

## Value

Medium Value

## Success looks like

- [ ] Build successfully creates a new release with an updated wheel package.
- [ ] README file is updated without causing build failures.

## Failure looks like

- [ ] Build continues to fail after multiple attempts to resolve issues.
- [ ] Unable to create a new release or update the README.
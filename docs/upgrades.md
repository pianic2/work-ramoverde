# Upgrade policy

## Python and Django

Use Python 3.13 for the current template. Django 5.2 is the current LTS baseline and supports Python 3.13. Track Django's support schedule; the next planned LTS is 6.2 in April 2027, so upgrade after its stable release and dependency compatibility checks rather than adopting development builds. Update bounds, uv lock, test migrations on PostgreSQL, run deployment checks, and verify third-party DRF/OpenAPI/JWT dependencies.

## Node and web

Use Node 24 LTS and pnpm workspaces. Dependabot proposes weekly updates. Review major versions manually, keep lockfiles committed, and run lint, typecheck, web tests and production build.

## Expo, React Native and personal component library

Expo SDK, React, React Native, Router and native modules move together. Current compatible tuple: SDK 57, React 19.2.3, RN 0.86.3, Router 57, personal library 0.1.0-rc.2. Its peers exclude RN 0.87, so do not upgrade React Native to 0.87 until the library publishes a release supporting it. Prefer the newest stable compatible tuple, checked with Expo's official SDK mapping, package peers, `expo-doctor`, render tests and Metro export. Replace the RC dependency with a compatible stable library release when available.

## PostgreSQL and images

External images that can be verified through their publisher's registry are pinned by tag and multi-platform digest; Dependabot monitors Dockerfiles and Compose directories. Review PostgreSQL major upgrade notes and use tested backup/restore before upgrading. Keep Compose, CI and production versions aligned.

The NGINX base image is pinned to its verified OCI index digest. A previously configured MinIO image returned `not found`, so the broken local storage profile was removed. Add a maintained S3-compatible local service only when a product needs it and its image can be verified from the publisher.

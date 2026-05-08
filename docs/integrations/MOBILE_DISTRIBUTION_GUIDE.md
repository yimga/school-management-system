# Mobile Distribution Guide

The web app is the primary surface; native shells (PWA / Capacitor / React Native) are optional. This guide is a placeholder reference for when distribution is opened.

## Apple App Store

1. **Enroll:** https://developer.apple.com/programs/ — $99/year per organization.
2. **Provision:** App Store Connect → My Apps → New App. Bundle ID, primary language, SKU.
3. **TestFlight:** for internal beta with up to 10,000 testers.
4. **Submit for Review:** typical review time is 1–3 business days.

Required assets:
- App icon (1024×1024)
- Screenshots (6.5", 5.5" required minimum)
- Privacy policy URL
- App privacy questionnaire (data collection, third-party SDKs)

## Google Play

1. **Enroll:** https://play.google.com/console — $25 one-time fee.
2. **Create app** → Bundle ID, default language, app name.
3. **Internal testing track** for first builds; promote to closed → open → production.
4. **Data safety form** mandatory.

Required assets:
- App icon (512×512)
- Feature graphic (1024×500)
- Screenshots (phone + tablet)
- Privacy policy URL

## Build pipeline

The repo provides a PWA service worker out of the box. For native shells:

- Capacitor: `npx cap add ios|android` then build per platform.
- Expo / React Native: separate `mobile/` directory pinned to a specific app version.

The mobile track is optionally tied to backend version via the `/-/version/` endpoint so the shell can refuse to launch against an incompatible deployment.

## What this guide does NOT cover

- App-store dispute / rejection appeals — handled outside the repo.
- Country-specific app-store legal requirements (e.g. China requires ICP filing).

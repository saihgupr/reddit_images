# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [1.3] - 2026-11-24

### Added
- A second data source: the community Arctic Shift archive, which needs no Reddit account or app. It is now the default when no working Reddit app is configured.
- A **Data source** option (Automatic, Archive only, Reddit API only). Automatic uses a working Reddit app when there is one and falls back to the archive when Reddit rejects the credentials, so images keep loading instead of the card going blank.
- Client ID and client secret are now optional, so the integration can be set up with no Reddit account at all.

### Changed
- The Repairs issue for rejected credentials now says images are still being served by the archive.
- The archive source reads the most recent 100 posts and ranks them by score, since the archive's search only sorts by date.

## [1.2] - 2026-11-23

### Added
- A Repairs issue is raised when Reddit rejects the app credentials, with the steps to fix them.
- The last downloaded image is saved and restored after a restart, so the card keeps showing it while Reddit is unreachable.

### Fixed
- Token and listing requests now retry transient network errors (2 seconds, then 5 seconds) before giving up.

## [1.1] - 2026-11-20

### Fixed
- Restored image loading after Reddit shut down public `.rss` feeds on November 13, 2026. The integration now uses Reddit's official OAuth API with an app-only token instead of RSS.
- Added client ID and client secret fields to the setup flow and a Configure dialog for existing installs.
- Added clearer errors for rejected credentials and unreachable Reddit endpoints.
- Image content type is now detected from the downloaded file instead of always assuming JPEG.

### Changed
- README updated for the Home Assistant Marketplace (HACS was merged into Home Assistant as the Marketplace in 2026.11): new install steps, Marketplace badge, and refreshed feature and how-it-works notes.

## [1.0.10] - 2026-11-01

### Added
- Added `brand/` directory containing `icon.png`, `icon@2x.png`, `logo.png`, and `logo@2x.png` for Home Assistant and HACS default catalog compliance.

## [1.0.9] - 2026-08-05

### Added
- Added HACS and Hassfest GitHub Actions workflows.

## [1.0.8] - 2026-06-05

### Fixed
- Fixed Reddit API `403 Forbidden` errors by switching from the blocked `.json` API endpoints to public Atom/RSS (`.rss`) feeds.
- Implemented robust XML parsing using Python's standard `xml.etree.ElementTree` and regex to reliably extract the best-resolution image URLs from single-image, gallery, and video posts.
- Added custom User-Agent headers to the CDN image download requests to prevent future image loading blocks.

## [1.0.7] - 2025-12-16

### Added
- Clean release with working images.
- Selection mode options in the config flow.

## [1.0.1] - 2025-12-16

### Changed
- Internal cleanups and version bump.

## [1.0.0] - 2025-12-16

### Added
- Initial release under HACS.
- Lovelace dashboard integration guides.

## [1.0] - 2025-12-06

### Added
- Initial version of the Reddit Images integration.

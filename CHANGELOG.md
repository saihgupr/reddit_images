# Changelog

All notable changes to this project will be documented in this file.

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

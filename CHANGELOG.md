# Changelog

All notable changes to this project are documented here.

## [0.1.6] - 2026-09-10

### Added
- New local Home Assistant integration icon for `m2A Eau`

### Changed
- Branding refreshed for clearer identification in Home Assistant and HACS
- Removed the separate hDPI icon so Home Assistant falls back consistently to the new `icon.png`

## [0.1.5] - 2026-09-10

### CI / packaging fixes
- Declared Home Assistant Recorder dependency required by Hassfest
- Corrected documentation and issue tracker URLs for `SepuLeVrai/ha_m2a_SDE`
- Added GitHub repository-topic guidance required by HACS

### Added
- HACS-ready public repository structure
- Complete Home Assistant manifest metadata
- Local integration brand icon
- HACS and Hassfest GitHub Actions
- GitHub issue templates and security guidance
- France country metadata for HACS

### Changed
- Removed private/example household data from documentation and translations
- Removed `strings.json` in favor of `translations/en.json` for custom integration localization
- Reduced routine authentication/history success logging from warning to debug

## [0.1.4] - 2026-09-10

### Added
- Reverse chronological historical backfill
- Per-month progress persistence
- N-1 historical date remapping
- Full-history resynchronization button

### Fixed
- Unavailable old periods no longer abort the entire historical import

## [0.1.3] - 2026-09-10

### Fixed
- Full-history import completion is now tracked independently from the recent cache

## [0.1.2] - 2026-09-10

### Fixed
- Browser-compatible request/session behavior for the m2A portal
- Home Assistant aiohttp session lifecycle handling

## [0.1.1] - 2026-09-10

### Fixed
- Authentication session preflight
- Improved HTTP authentication diagnostics

## [0.1.0] - 2026-09-10

### Added
- Initial Home Assistant integration
- m2A authentication and meter lookup
- Daily consumption and N-1 comparison
- Recorder statistics and historical import

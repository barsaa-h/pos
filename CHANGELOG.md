# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Eye icon toggle to show/hide PIN code on admin login page
- Content Security Policy (CSP) and security headers (X-Content-Type-Options, X-Frame-Options, etc.)
- Request size limit error handler (413)
- Skip-to-content link for keyboard accessibility
- Live region (aria-live) for notification area
- Touch-friendly minimum target sizes (44px) for interactive elements
- `.dockerignore` for optimized Docker builds
- `.coveragerc` configuration for test coverage reporting
- `requirements-dev.txt` for development dependencies
- Backup script at `deploy/backup.sh`
- Nginx reverse proxy configuration at `deploy/nginx.conf`
- GitHub Actions CI pipeline (lint, test, docker build)
- Pre-commit hooks configuration

### Security
- CSP headers restrict script/style sources
- 413 error prevents large request attacks

### Changed
- Admin login form now includes PIN visibility toggle (eye icon)
- PIN field wrapper with toggle button for better UX
- Ctrl+H keyboard shortcut to toggle PIN visibility

"""
ResearchOS Version Information

Semantic versioning scheme:
  MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]

MAJOR: Architectural changes, breaking API changes
MINOR: New capability layers (Phase 4.x), new features
PATCH: Bug fixes, coverage improvements, documentation
"""

__version__ = "1.0.1"
__version_info__ = (1, 0, 1)

# Release metadata
VERSION_CODENAME = "Release-Candidate"
PHASE = 5  # Last completed phase
STATUS = "release-candidate"

# Git information (updated by CI/CD on release)
GIT_COMMIT = ""  # Will be set by CI pipeline
GIT_TAG = "v1.0.1"  # Current release tag
BUILD_DATE = ""  # Will be set by CI pipeline

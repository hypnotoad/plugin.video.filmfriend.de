# SPDX-License-Identifier: GPL-2.0-only

"""Pure helpers for translating Filmfriend catalogue metadata."""


def release_date_metadata(value):
	"""Return Kodi date metadata for a Filmfriend ISO date, if usable.

	Filmfriend catalogue records may explicitly contain ``releaseDate: null``.
	Keeping this helper independent of Kodi makes that API edge case directly
	testable without importing any Kodi modules.
	"""
	if not isinstance(value, str):
		return {}

	value = value.strip()
	if len(value) < 4 or not value[:4].isdigit():
		return {}

	metadata = {'year': value[:4]}
	if len(value) >= 10:
		metadata['premiered'] = value[:10]
		metadata['aired'] = value[:10]
	return metadata

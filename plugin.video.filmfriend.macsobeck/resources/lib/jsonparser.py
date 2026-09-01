# -*- coding: utf-8 -*-
import urllib.parse

import xbmcaddon
import xbmcgui

import resources.lib.external.libmediathek4utils as lm4utils
from resources.lib.api import ApiError, NotFound
from resources.lib.auth import AuthenticationError, LoginExpired, LoginRequired
from resources.lib.kodi_runtime import build_runtime

__addon__ = xbmcaddon.Addon()
__addonid__ = __addon__.getAddonInfo('id')
__addonname__ = __addon__.getAddonInfo('name')

german = {
	'order':'GermanName',

	'synopsis':'germanSynopsis',
	'title':'germanTitle',
	'name':'germanName',
	'teaser':'germanTeaser',
}

english = {
	'order':'EnglishName',

	'synopsis':'englishSynopsis',
	'title':'englishTitle',
	'name':'englishName',
	'teaser':'englishTeaser',
}

french = {
	'order':'FrenchName',

	'synopsis':'frenchSynopsis',
	'title':'frenchTitle',
	'name':'frenchName',
	'teaser':'frenchTeaser',
}

italian = {
	'order':'ItalianName',

	'synopsis':'italianSynopsis',
	'title':'italianTitle',
	'name':'italianName',
	'teaser':'italianTeaser',
}

languages = {
	'en':english,
	'de':german,
	'fr':french,
	'it':italian,
}

langCode = lm4utils.getSetting('language')
if langCode in ['system', '']:
	l = lm4utils.getISO6391()
	if l in languages:
		langCode = l
	else:
		langCode = 'en'

lang = languages[langCode]

_settings, _logger, _oauth, _authentication, _api = build_runtime(langCode)


def _handleApiError(error):
	if isinstance(error, LoginRequired):
		lm4utils.displayMsg(
			lm4utils.getTranslation(30512),
			lm4utils.getTranslation(30513))
	elif isinstance(error, LoginExpired):
		xbmcgui.Dialog().ok(__addonname__, lm4utils.getTranslation(30509))
	else:
		lm4utils.displayMsg(
			lm4utils.getTranslation(30506),
			lm4utils.getTranslation(30507))
	_logger.error(
		"api.operation_failed",
		endpoint_host=urllib.parse.urlsplit(
			getattr(error, "endpoint", "")).hostname or "",
		endpoint_path=urllib.parse.urlsplit(
			getattr(error, "endpoint", "")).path,
		error_type=error.__class__.__name__,
		status=getattr(error, "status_code", None),
	)

def parseMain():
	return None

def parseGenres():
	tenant = lm4utils.getSetting("tenant")
	if tenant == '':
		lm4utils.displayMsg(lm4utils.getTranslation(30512), lm4utils.getTranslation(30513))
		return [], []

	# get list of genres
	try:
		genres = _api.genres(tenant)
	except (ApiError, AuthenticationError) as error:
		_handleApiError(error)
		return [], []
	genre_names = [d["name"] for d in genres]
	genre_ids = [d["id"] for d in genres]
	return genre_names, genre_ids

def parseWatchList(params,content='videos'):
	try:
		j = _api.watchlist(params)
	except (ApiError, AuthenticationError) as error:
		_handleApiError(error)
		return _emptyPage(content)
	return parseResponse(j,content)

def parseSearch(params,content='videos'):
	try:
		j = _api.search(params)
	except (ApiError, AuthenticationError) as error:
		_handleApiError(error)
		return _emptyPage(content)
	return parseResponse(j,content)

def parseResponse(responseJson, content='videos'):
	res = _emptyPage(content)
	if responseJson is None or 'results' not in responseJson:
		return res

	for item in responseJson['results']:
		if 'result' in item:
			result = item['result']
		else:
			result = item.get(item.get('kind', '').lower())
		if not isinstance(result, dict):
			_logger.warning(
				"media.invalid_search_result",
				kind=item.get("kind", ""))
			continue
		if item['kind'] == 'Series':
			d = {'type':'tvshow', 'params':{'mode':'listSearch', 'content':'tvshows'}, 'metadata':{'art':{}}}
			d['metadata']['name'] = _getString(result,'title')
			d['metadata']['plot'] = _getString(result,'synopsis')
			d['metadata']['art'] = _getArt(result)

			d['params']['params'] = f'?kinds=Season&series={result["id"]}&orderBy={lang["order"]}&sortDirection=Ascending'
			res['items'].append(d)


		elif item['kind'] == 'Season':
			d = {'type':'season', 'params':{'mode':'listSearch', 'content':'episodes'}, 'metadata':{'art':{},'genres':[]}}
			d['metadata']['name'] = f"{_getString(result['series'],'title')} - Season {str(result['seasonNumber'])}"
			d['metadata']['plot'] = _getString(result,'synopsis')

			d['metadata']['season'] = result['seasonNumber']
			d['metadata']['mpaa'] = result.get(
				'motionPictureContentRating', '')
			d['metadata']['art'] = _getArt(result)
			if 'genres' in result['series']:
				for genre in result['series']['genres']:
					d['metadata']['genres'].append(_getString(genre,'name'))
			if 'releaseDate' in result:
				d['metadata']['year'] = result['releaseDate'][:4]
				d['metadata']['premiered'] = result['releaseDate'][:10]
				d['metadata']['aired'] = result['releaseDate'][:10]

			d['params']['params'] = f'?kinds=Video&season={result["id"]}&orderBy={lang["order"]}&sortDirection=Ascending'
			res['items'].append(d)


		elif item['kind'] in ('Video', 'Movie', 'Episode'):
			d = {'type':'movie', 'params':{'mode':'playVideo'}, 'metadata':{'art':{},'actors':[],'directors':[],'artists':[],'writers':[],'genres':[],'credits':[]}}
			d['metadata']['name'] = _getString(result,'title')
			if 'originalTitle' in result:
				d['metadata']['originaltitle'] = result['originalTitle']
			d['metadata']['plot'] = _getString(result,'synopsis')
			d['metadata']['plotoutline'] = _getString(result,'teaser')

			if 'season' in result:
				d['metadata']['season'] = result['season']['seasonNumber']
			if 'episodeNumber' in result:
				d['metadata']['episode'] = result['episodeNumber']
				d['type'] = 'episode'
			d['metadata']['duration'] = result['runtime']
			if 'releaseDate' in result:
				d['metadata']['year'] = result['releaseDate'][:4]
				d['metadata']['premiered'] = result['releaseDate'][:10]
				d['metadata']['aired'] = result['releaseDate'][:10]
			d['metadata']['art'] = _getArt(result)

			participations = result.get(
				'participations', result.get('participants', []))
			if participations:
				for participant in participations:
					if participant['kind'] in ['Actor', 'Voice']:
						d['metadata']['actors'].append({'role':participant.get('englishDescription',''),'name':_getName(participant)})
					elif participant['kind'] in ['Director', 'Producer']:
						d['metadata']['directors'].append(_getName(participant))
					elif participant['kind'] == 'Composer':
						d['metadata']['artists'].append(_getName(participant))
					elif participant['kind'] in ['Writer', 'Editor']:
						d['metadata']['writers'].append(_getName(participant))
					elif participant['kind'] in ['Misc', 'Camera']:
						d['metadata']['credits'].append(_getName(participant))
			if 'genres' in result:
				for genre in result['genres']:
					d['metadata']['genres'].append(_getString(genre,'name'))

			d['params']['video'] = result["id"]
			res['items'].append(d)

		else:
			_logger.warning(
				"media.unsupported_kind", kind=item["kind"])

	if content == 'tvshows':
		# sort by name unless we're showing the seasons of a single tv show, then sort by season number
		res['items'] = sorted(res['items'], key=lambda entry: entry['metadata']['season'] if entry['type'] == 'season' else entry['metadata']['name'])
	elif content == 'episodes':
		res['items'] = sorted(res['items'], key=lambda entry: entry['metadata']['episode'])

	return res

def getVideoUrl(videoId):
	# first check the media type and if it's currently available
	mediaType = "movies"
	try:
		try:
			details = _api.media_details(mediaType, videoId)
		except NotFound:
			# fallback: try if it's an episode
			mediaType = "episodes"
			details = _api.media_details(mediaType, videoId)
		if details["state"]["kind"] != "Active":
			lm4utils.displayMsg(
				lm4utils.getTranslation(30603),
				lm4utils.getTranslation(30604))
			return _emptyMedia()
		videoInfo = _api.media_uri(mediaType, videoId)
	except (ApiError, AuthenticationError, KeyError) as error:
		_handleApiError(error)
		return _emptyMedia()

	if not videoInfo.get("mpegDash") or not videoInfo.get("widevineLicenseServerUri"):
		_logger.error("playback.uri_response_incomplete")
		lm4utils.displayMsg(
			lm4utils.getTranslation(30506),
			lm4utils.getTranslation(30507))
		return _emptyMedia()

	url = f'{videoInfo["mpegDash"]}'
	return {
		'media': [{
			'url': url,
			'widevine_license_url': videoInfo["widevineLicenseServerUri"],
			'type': 'video',
			'stream': 'DASH',
		}]
	}

def _emptyPage(content='videos'):
	return {'items': [], 'content': content, 'pagination': {'currentPage': 0}}

def _emptyMedia():
	return {'media':[]}

def _getString(d,k):
	try:
		s = d.get(lang[k], '')
		if s != '':
			return s
		else:
			return d[english[k]]
	except:
		try:
			return d.get(k)
		except:
			return ''

def _getName(participant):
	if 'firstName' in participant['person']:
		return f"{participant['person']['firstName']} {participant['person']['lastName']}"
	else:
		return participant['person']['lastName']

def _getArt(item):
	thumb = ''
	fanart = ''
	poster = ''
	banner = ''
	if 'artworkUris' in item:
		for art in item['artworkUris']:
			if art['kind'] == 'Thumbnail' and thumb == '':
				thumb = art['resolution2x']
			elif art['kind'] == 'Thumbnail' and fanart == '':
				fanart = art['resolution4x']
			elif art['kind'] == 'Background':
				fanart = art['resolution1080']
			elif art['kind'] == 'CoverPortrait' and poster == '':
				poster = art['resolution4x']
			elif art['kind'] == 'Teaser' and banner == '':
				banner = art['resolution720']
	else:
		for art in item['artworks']:
			if art['kind'] == 'Thumbnail' and thumb == '':
				thumb = art['uri']['thumbnail2x']
			elif art['kind'] == 'Thumbnail' and fanart == '':
				fanart = art['uri']['resolution4x']
			elif art['kind'] == 'Background':
				fanart = art['uri']['resolution1080']
			elif art['kind'] == 'CoverPortrait' and poster == '':
				poster = art['uri']['thumbnail4x']
			elif art['kind'] == 'Teaser' and banner == '':
				banner = art['uri']['resolution720']
	return {'thumb':thumb, 'fanart':fanart, 'poster':poster, 'banner':banner}

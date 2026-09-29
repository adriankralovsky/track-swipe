"""Shared yt-dlp authentication and readable errors. Credentials stay on disk."""
import re
from pathlib import Path

BROWSERS = ('firefox', 'chrome', 'chromium', 'brave', 'edge', 'vivaldi', 'opera', 'safari')
ANSI = re.compile(r'(?:\x1b|␛)\[[0-?]*[ -/]*[@-~]')


def clean_error(error):
    return ANSI.sub('', str(error)).strip()


def auth_required(error):
    text = clean_error(error).lower()
    return any(term in text for term in ('sign in', 'sign-in', 'cookies-from-browser', 'login required', 'authentication required'))


def friendly_error(error):
    text = clean_error(error)
    if text.startswith('YouTube requires sign-in for this video.'): return text
    if auth_required(text):
        return ('YouTube requires sign-in for this video. Configure YouTube authentication in '
                'Settings → Audio (browser cookies for native runs, or a Netscape cookies file '
                'for Docker), then retry. Expired cookies may need re-exporting. Details: ' + text)
    return text


def options(settings):
    result = {'quiet': True, 'nocolor': True, 'socket_timeout': 30,
              'js_runtimes': {'node': {}}, 'noplaylist': True}
    mode = settings.get('youtube_auth', 'none')
    if mode == 'file':
        path = Path(settings.get('youtube_cookies_file', '')).expanduser()
        if not path.is_file():
            raise ValueError('YouTube cookies file not found. Check Settings → Audio and Docker mounts.')
        result['cookiefile'] = str(path)
    elif mode == 'browser':
        browser = settings.get('youtube_browser', 'firefox')
        if browser not in BROWSERS:
            raise ValueError('Unsupported browser for YouTube cookies')
        result['cookiesfrombrowser'] = (browser, settings.get('youtube_browser_profile') or None, None, None)
    return result

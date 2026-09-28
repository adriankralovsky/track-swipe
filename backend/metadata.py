"""Optional public enrichment. Only fill missing canonical fields, never YouTube titles."""
import logging, threading, time
import httpx
from .importer import norm

_gate=threading.Lock()
_last_request=0
log=logging.getLogger('trackswipe.metadata')

def enrich(track):
    m=dict(track); warnings=[]
    if m.get('spotify_id') and (not m.get('artwork') or not m.get('title')):
        try:
            r=httpx.get('https://open.spotify.com/oembed',params={'url':'https://open.spotify.com/track/'+m['spotify_id']},timeout=10)
            r.raise_for_status(); data=r.json()
            if not m.get('title'): m['title']=data.get('title','')
            if not m.get('artwork'): m['artwork']=data.get('thumbnail_url','')
        except Exception as exc: warnings.append('Spotify public metadata unavailable'); log.info('Spotify enrichment: %s',exc)
    if m.get('isrc') and (not m.get('artwork') or not m.get('duration') or not m.get('album')):
        try:
            global _last_request
            with _gate:
                time.sleep(max(0,1.1-(time.monotonic()-_last_request)))
                r=httpx.get('https://musicbrainz.org/ws/2/isrc/'+str(m['isrc']),params={'fmt':'json','inc':'artist-credits+releases'},headers={'User-Agent':'TrackSwipe/1.0 (local personal music library)'},timeout=12)
                _last_request=time.monotonic()
            r.raise_for_status(); recordings=r.json().get('recordings',[])
            for recording in recordings:
                artists=[a.get('name') or a.get('artist',{}).get('name','') for a in recording.get('artist-credit',[]) if isinstance(a,dict)]
                if norm(recording.get('title'))!=norm(m.get('title')): continue
                if m.get('artists') and norm(m['artists'][0]) not in [norm(a) for a in artists]: continue
                if not m.get('artists'): m['artists']=artists
                if not m.get('album_artist') and artists: m['album_artist']=artists[0]
                if not m.get('duration') and recording.get('length'): m['duration']=recording['length']/1000
                # Artwork/release data only from an exact album match; don't choose a random compilation.
                release=next((x for x in recording.get('releases',[]) if m.get('album') and norm(x.get('title'))==norm(m['album'])),None)
                if release:
                    if not m.get('release_date'): m['release_date']=release.get('date','')
                    if not m.get('artwork'): m['artwork']='https://coverartarchive.org/release/'+release['id']+'/front-500'
                break
        except Exception as exc: warnings.append('MusicBrainz enrichment unavailable'); log.info('MusicBrainz enrichment: %s',exc)
    return m,warnings

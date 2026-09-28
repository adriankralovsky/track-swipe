import re
from difflib import SequenceMatcher
from .importer import norm

TERMS={'live':'ignore_live','cover':'ignore_covers','piano':'ignore_covers','instrumental':'ignore_instrumental','karaoke':'ignore_instrumental','remix':'ignore_remixes','remastered':None,'slowed':'ignore_speed','reverb':'ignore_speed','sped up':'ignore_speed','nightcore':'ignore_speed','acoustic':None,'edit':None,'extended':None,'lyrics':None,'lyric video':None,'reaction':None,'tutorial':None,'performance':None}

def score(t,c,s):
    title=norm(t['title']); ct=norm(c['title']); artists=t.get('artists',[])
    ca=norm(' '.join(c.get('artists',[]))); channel=norm(c.get('channel',''))
    primary=norm(artists[0]) if artists else ''
    cleaned=re.sub(r'\b(official audio|official video|audio|visualizer|music video)\b','',ct).strip()
    if primary and cleaned.startswith(primary+' '): cleaned=cleaned[len(primary):].strip()
    exact_title=title==cleaned; exact_artist=bool(primary and (primary in [norm(a) for a in c.get('artists',[])] or primary==re.sub(r' topic$','',channel)))
    title_sim=SequenceMatcher(None,title,cleaned).ratio() if title else 0
    candidate_artists=[norm(a) for a in c.get('artists',[])]
    artist_match=exact_artist or bool(primary and primary in candidate_artists)
    featured=artists[1:]
    featured_match=all(norm(a) in candidate_artists or norm(a) in ct for a in featured)
    duration=abs(float(t.get('duration') or 0)-float(c.get('duration') or 0)) if t.get('duration') and c.get('duration') else None
    topic=channel.endswith(' topic'); music=c.get('music',False)
    suspicious=[term for term,key in TERMS.items() if re.search(r'\b'+re.escape(term)+r'\b',ct) and not re.search(r'\b'+re.escape(term)+r'\b',title) and (not key or s.get(key,True))]
    video=bool(re.search(r'official (music )?video|music video',ct))
    points=40*title_sim+25*artist_match
    reasons=[{'label':'Exact title' if exact_title else f'Title similarity {title_sim:.0%}','ok':exact_title}, {'label':'Exact artist' if exact_artist else 'Artist not verified','ok':exact_artist}]
    if featured:
        reasons.append({'label':'Featured artists match' if featured_match else 'Featured artists not verified','ok':featured_match})
        if not featured_match: points-=5
    if duration is not None:
        points+=20 if duration<2 else max(-25,20-duration*1.5)
        if duration>s['max_duration_difference']: points-=25
        reasons.append({'label':f'Duration difference: {duration:.1f}s','ok':duration<2})
    else: reasons.append({'label':'Duration unavailable','ok':False})
    if topic and s['prefer_topic']: points+=10
    elif music and s['prefer_music']: points+=8
    elif c.get('official'): points+=5
    if music and s['prefer_music']: points+=5
    if t.get('album') and norm(t['album'])==norm(c.get('album')):
        points+=3; reasons.append({'label':'Album matches','ok':True})
    if c.get('auto_generated'):
        reasons.append({'label':'YouTube Music auto-generated audio','ok':True})
    if t.get('isrc') and c.get('isrc'):
        same_isrc=norm(t['isrc'])==norm(c['isrc'])
        points+=10 if same_isrc else -50
        reasons.append({'label':'ISRC matches' if same_isrc else 'ISRC mismatch','ok':same_isrc})
    if video and s['penalize_video']: points-=18
    points-=min(65,len(suspicious)*30)
    reasons.extend([{'label':'Topic channel' if topic else 'YouTube Music song' if music else 'General YouTube upload','ok':topic or music},{'label':', '.join(suspicious) if suspicious else 'No unexpected version keywords','ok':not suspicious}])
    if video: reasons.append({'label':'Music video: possible intro/outro','ok':False})
    c.update(confidence=round(max(0,min(100,points))),reasons=reasons,topic=topic,auto_eligible=bool(topic and music and exact_title and exact_artist and duration is not None and duration<2 and featured_match and not suspicious and not video))
    return c

def search(t,s,query=None):
    from ytmusicapi import YTMusic
    import requests
    import yt_dlp
    class TimedSession(requests.Session):
        def request(self,*args,**kwargs):
            kwargs.setdefault('timeout',20)
            return super().request(*args,**kwargs)
    q=query or ' '.join(t.get('artists',[]))+' '+t['title']
    out={}; errors=[]
    try:
        for r in YTMusic(requests_session=TimedSession()).search(q,filter='songs',limit=s['candidate_count'])[:s['candidate_count']]:
            vid=r.get('videoId')
            if not vid: continue
            a=[v['name'] for v in r.get('artists',[])]
            out[vid]=dict(video_id=vid,title=r.get('title',''),artists=a,album=(r.get('album') or {}).get('name',''),channel=' · '.join(a),duration=r.get('duration_seconds') or 0,thumbnail=(r.get('thumbnails') or [{}])[-1].get('url',''),music=True,official=False,auto_generated=r.get('videoType')=='MUSIC_VIDEO_TYPE_ATV')
    except Exception as e: errors.append('YouTube Music: '+str(e))
    try:
        with yt_dlp.YoutubeDL({'quiet':True,'no_warnings':True,'extract_flat':True,'socket_timeout':15}) as y:
            result=y.extract_info(f'ytsearch{s["candidate_count"]}:{q} audio',download=False)
            for r in result.get('entries',[]):
                vid=r.get('id')
                if not vid: continue
                c=out.get(vid,{})
                c.update(video_id=vid,title=c.get('title') or r.get('title',''),channel=r.get('channel') or r.get('uploader') or '',duration=c.get('duration') or r.get('duration') or 0,thumbnail=c.get('thumbnail') or f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg',official=bool(r.get('channel_is_verified')))
                out[vid]=c
    except Exception as e: errors.append('YouTube: '+str(e))
    if not out: raise ValueError('; '.join(errors) or 'No search results. Try a different query.')
    return sorted([score(t,c,s) for c in out.values()],key=lambda c:c['confidence'],reverse=True),errors

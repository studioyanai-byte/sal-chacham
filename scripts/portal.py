import requests,re,gzip,json,sys
import xml.etree.ElementTree as ET
B='https://url.publishedprices.co.il'
def session(user):
    s=requests.Session(); import os; s.verify=os.environ.get('CA_BUNDLE',True)
    r=s.get(B+'/login',timeout=30); tok=re.search(r'name="csrftoken"\s+content="([^"]+)"',r.text).group(1)
    r=s.post(B+'/login/user',data={'username':user,'password':'','csrftoken':tok,'r':''},timeout=30)
    if '/file' not in r.url: return None,None
    m=re.search(r'name="csrftoken"\s+content="([^"]+)"',r.text); tok=m.group(1) if m else tok
    return s,tok
def listfiles(s,tok):
    r=s.post(B+'/file/json/dir',data={'sEcho':1,'iColumns':5,'iDisplayStart':0,'iDisplayLength':100000,'mDataProp_0':'fname','sSearch':'','cd':'/','csrftoken':tok},timeout=90)
    return [x['fname'] for x in r.json().get('aaData',[])]
def get(s,name):
    r=s.get(B+'/file/d/'+name,timeout=180); raw=r.content
    try: raw=gzip.decompress(raw)
    except Exception: pass
    return raw
def parse(raw):
    for enc in ('utf-8-sig','utf-16'):
        try: t=raw.decode(enc); break
        except Exception: continue
    t=re.sub(r'<\?xml[^>]*\?>','',t,count=1).strip()
    return ET.fromstring(t)

"""Compacts data.json (from build_data.py) into the format the page loads (site/data.json)."""
import json, sys
d=json.load(open('data.json'))
def clean(x): return '' if x in ('לא ידוע','unknown','') else str(x).replace('|',' ')
lines='\n'.join('|'.join([c,n.replace('|',' '),clean(m),('%g'%q if q else ''),u if u not in ('לא ידוע','') else '',str(w)]) for c,n,m,q,u,w in d['products'])
prices=[','.join('' if v==0 else format(v,'x') for v in s['p']) for s in d['prices']]
out={'gen':d['gen'],'stores':d['stores'],'P':lines,'S':prices,'PR':[s['pr'] for s in d['prices']],'D':d['promoDesc']}
if len(d['products'])<5000: sys.exit('too few products – keeping previous data.json')
json.dump(out,open(sys.argv[1] if len(sys.argv)>1 else '../data.json','w'),ensure_ascii=False,separators=(',',':'))
print('ok',len(d['products']))

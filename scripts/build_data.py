"""Builds data.json for Sal Chacham from the chains' price-transparency files (publishedprices.co.il).
Usage: python3 build_data.py  -> writes data.json (+ data.min.json)
"""
import sys, re, json, gzip, datetime, collections, statistics
sys.path.insert(0, '.')
from portal import session, listfiles, get, parse

# (portal user, chain key, store id, city key)
BRANCHES = [
    ('RamiLevi', 'rl', '041', 'reh'), ('RamiLevi', 'rl', '040', 'yav'), ('RamiLevi', 'rl', '043', 'rlz'),
    ('yohananof', 'yoh', '031', 'reh'), ('yohananof', 'yoh', '025', 'nz'), ('yohananof', 'yoh', '016', 'gy'), ('yohananof', 'yoh', '052', 'ged'),
    ('TivTaam', 'tt', '018', 'reh'), ('TivTaam', 'tt', '014', 'rlz'),
    ('osherad', 'oa', '025', 'rlz'),
    ('Keshet', 'kes', '013', 'rlz'),
    ('freshmarket', 'lhv', '025', 'yav'), ('freshmarket', 'dudu', '010', 'by'),
]
NOW = datetime.datetime.now()
STALE_DAYS = 60

def kids(el):
    return {c.tag: (c.text or '').strip() for c in el if len(c) == 0}

def fnum(x, d=0.0):
    try: return float(str(x).replace(',', '.'))
    except Exception: return d

def pdate(x):
    try: return datetime.datetime.fromisoformat(x.replace('Z', '')[:19])
    except Exception:
        try: return datetime.datetime.strptime(x[:10], '%Y-%m-%d')
        except Exception: return None

def latest(files, prefix, store):
    pat = re.compile(r'^' + prefix + r'\d+-\d+-0*' + str(int(store)) + r'-\d+', re.I)
    c = sorted([f for f in files if pat.match(f)])
    return c[-1] if c else None

def store_meta(s, files, store):
    st = sorted([f for f in files if f.lower().startswith('stores')])
    root = parse(get(s, st[-1]))
    for x in root.iter():
        if x.tag.lower() in ('store', 'branch'):
            d = {c.tag.lower(): (c.text or '').strip() for c in x}
            if d.get('storeid', '').lstrip('0') == str(int(store)):
                return d
    return {}

BAD_M = {'', 'unknown', 'משתנה', 'לא ידוע', 'כללי', 'ללא', 'ללא יצרן', 'n/a', 'none', '-', '.', '0'}
def good_m(m):
    return (m or '').strip().lower() not in BAD_M

def parse_prices(raw):
    root = parse(raw); out = {}
    for it in root.iter():
        if it.tag.lower() != 'item': continue
        d = kids(it); code = d.get('ItemCode', '').strip()
        price = fnum(d.get('ItemPrice'))
        if not code or price <= 0: continue
        ls = pdate(d.get('LastSaleDateTime', '') or '')
        if ls and (NOW - ls).days > STALE_DAYS: continue          # phantom / not sold lately
        out[code] = {
            'n': re.sub(r'\s+', ' ', d.get('ItemName', '')).strip(),
            'm': (d.get('ManufacturerName') or d.get('ManufactureName') or '').strip(),
            'q': fnum(d.get('Quantity')), 'u': (d.get('UnitQty') or '').strip(),
            'w': 1 if d.get('bIsWeighted', '0') in ('1', 'true') else 0,
            'p': round(price, 2),
            'upd': (d.get('PriceUpdateDate') or d.get('PriceUpdateTime') or '')[:16],
        }
    return out

def parse_promos(raw, prices):
    root = parse(raw); best = {}
    for pr in root.iter():
        if pr.tag.lower() != 'promotion': continue
        d = kids(pr)
        st = pdate(d.get('PromotionStartDateTime') or d.get('PromotionStartDate') or '')
        en = pdate(d.get('PromotionEndDateTime') or d.get('PromotionEndDate') or '')
        if en and en.hour == 0 and en.minute == 0 and 'T' not in (d.get('PromotionEndDate') or 'T'): en = en + datetime.timedelta(days=1)
        if (st and st > NOW) or (en and en < NOW): continue
        club = ''.join(x.text or '' for x in pr.iter() if x.tag.lower() == 'clubid').strip()
        if club not in ('', '0') and 'כלל' not in club: continue          # club-only promos skipped
        if (d.get('AdditionalIsCoupon') or '0') == '1': continue
        desc = re.sub(r'\s+', ' ', d.get('PromotionDescription', '')).strip()
        p_price = fnum(d.get('DiscountedPrice'), 0); p_min = fnum(d.get('MinQty'), 0)
        for it in pr.iter():
            if it.tag.lower() not in ('promotionitem', 'item'): continue
            k = kids(it); code = k.get('ItemCode', '').strip()
            if code not in prices: continue
            reg = prices[code]['p']
            dp = fnum(k.get('DiscountedPrice'), 0) or p_price
            mq = fnum(k.get('MinQty'), 0) or p_min or 1
            if dp <= 0: continue
            w = prices[code]['w']
            eff = dp / mq if (mq >= 2 and not w) else dp
            if not (0.25 * reg <= eff < reg - 0.004): continue      # sanity: must be a real discount
            cur = best.get(code)
            if not cur or eff < cur['e']:
                best[code] = {'e': round(eff, 2), 'mq': int(mq) if (mq >= 2 and not w) else 1, 't': round(dp, 2), 'd': desc[:60]}
    return best

def load_previous(path):
    """Previous compact data.json -> {store_id: (meta, prices, promos)} to carry over branches whose file is missing right now."""
    try: d = json.load(open(path, encoding='utf-8'))
    except Exception: return {}
    lines = d['P'].split('\n'); out = {}
    for j, st in enumerate(d['stores']):
        arr = d['S'][j].split(','); prices = {}
        for i, v in enumerate(arr):
            if not v: continue
            c, n, m, q, u, w = (lines[i].split('|') + ['']*6)[:6]
            prices[c] = {'n': n, 'm': m, 'q': fnum(q), 'u': u, 'w': 1 if w == '1' else 0, 'p': int(v, 16)/100, 'upd': ''}
        promos = {}
        for k, v in d['PR'][j].items():
            c = lines[int(k)].split('|')[0]
            if c in prices: promos[c] = {'e': v[0]/100, 'mq': v[1], 't': v[2]/100, 'd': d['D'][v[3]]}
        out[st['chain'] + st['sid']] = (st, prices, promos)
    return out

def main():
    prev = load_previous(sys.argv[1] if len(sys.argv) > 1 else '../data.json')
    sess = {}; stores = []; per_store = []
    for user, chain, sid, city in BRANCHES:
        if user not in sess:
            try:
                s, tok = session(user); sess[user] = (s, tok, listfiles(s, tok) if s else [])
            except Exception as e:
                print('login/list failed', user, e); sess[user] = (None, None, [])
        s, tok, files = sess[user]
        pf, pm = latest(files, 'PriceFull', sid), latest(files, 'PromoFull', sid)
        if not pf:
            old = prev.get(f'{chain}{sid}')
            if old:
                st, prices, promos = old; st = dict(st); st['stale'] = True
                print(f'{chain}:{sid} no file now – carried over {len(prices)} items from {st.get("upd")}')
                stores.append(st); per_store.append((prices, promos))
            else: print('no price file', user, sid)
            continue
        try:
            meta = store_meta(s, files, sid)
            prices = parse_prices(get(s, pf))
            promos = parse_promos(get(s, pm), prices) if pm else {}
        except Exception as e:
            print('download failed', chain, sid, e); old = prev.get(f'{chain}{sid}')
            if old:
                st, prices, promos = old; st = dict(st); st['stale'] = True; stores.append(st); per_store.append((prices, promos))
            continue
        ts = re.search(r'-(\d{8})-?(\d{4,6})', pf)
        upd = datetime.datetime.strptime(ts.group(1) + ts.group(2)[:4], '%Y%m%d%H%M').isoformat() if ts else NOW.isoformat()
        print(f'{chain}:{sid} {meta.get("storename","")} items={len(prices)} promos={len(promos)} file={pf}')
        stores.append({'id': f'{chain}{sid}', 'chain': chain, 'sid': sid, 'city': city,
                       'name': meta.get('storename', ''), 'addr': meta.get('address', ''), 'upd': upd})
        per_store.append((prices, promos))
    # union of products; name = most common
    names = collections.defaultdict(collections.Counter); info = {}
    for prices, _ in per_store:
        for code, d in prices.items():
            names[code][d['n']] += 1
            if code not in info: info[code] = dict(d)
            elif not good_m(info[code].get('m')) and good_m(d.get('m')): info[code]['m'] = d['m']   # take manufacturer from any chain that has it
    codes = sorted(names, key=lambda c: (-sum(1 for p, _ in per_store if c in p), c))
    idx = {c: i for i, c in enumerate(codes)}
    P = []
    for c in codes:
        d = info[c]
        P.append([c, names[c].most_common(1)[0][0], d['m'], d['q'], d['u'], d['w']])
    descs = []; didx = {}
    S = []
    for prices, promos in per_store:
        arr = [0] * len(codes); pro = {}
        for c, d in prices.items():
            arr[idx[c]] = int(round(d['p'] * 100))
        for c, d in promos.items():
            if d['d'] not in didx: didx[d['d']] = len(descs); descs.append(d['d'])
            pro[idx[c]] = [int(round(d['e'] * 100)), d['mq'], int(round(d['t'] * 100)), didx[d['d']]]
        S.append({'p': arr, 'pr': pro})
    data = {'gen': NOW.isoformat(timespec='minutes'), 'stores': stores, 'products': P, 'prices': S, 'promoDesc': descs}
    json.dump(data, open('data.json', 'w'), ensure_ascii=False, separators=(',', ':'))
    print('products', len(P), 'bytes', len(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()))

if __name__ == '__main__':
    main()

"""
KBO 경기 일정 수집 스크립트 (mykbostats.com 기반)
"""
import json, re, requests, sys
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

TEAM_MAP = {
    "Doosan Bears":"두산","Hanwha Eagles":"한화","Kia Tigers":"KIA",
    "Kiwoom Heroes":"키움","KT Wiz":"KT","LG Twins":"LG",
    "Lotte Giants":"롯데","NC Dinos":"NC","Samsung Lions":"삼성","SSG Landers":"SSG",
}
STADIUM_MAP = {
    "Seoul-Jamsil":"잠실","Suwon":"수원","Incheon":"인천","Incheon-Munhak":"인천",
    "Daejeon":"대전","Gwangju":"광주","Daegu":"대구","Busan-Sajik":"사직",
    "Changwon":"창원","Seoul-Gocheok":"고척","Pohang":"포항","Ulsan":"울산",
}
HOME_STADIUM = {
    "LG":"잠실","두산":"잠실","KT":"수원","SSG":"인천","한화":"대전",
    "KIA":"광주","삼성":"대구","롯데":"사직","NC":"창원","키움":"고척",
}
SLUG_MAP = {
    "Kia":"KIA","KT":"KT","LG":"LG","NC":"NC","SSG":"SSG",
    "Doosan":"두산","Hanwha":"한화","Lotte":"롯데","Samsung":"삼성","Kiwoom":"키움",
}
MONTH_MAP = {
    "January":1,"February":2,"March":3,"April":4,"May":5,"June":6,
    "July":7,"August":8,"September":9,"October":10,"November":11,"December":12
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def norm_team(n): return TEAM_MAP.get(n.strip(), n.strip())
def norm_stadium(n): return STADIUM_MAP.get(n.strip(), n.strip())
def parse_time(t):
    t = t.strip().lower()
    try: return datetime.strptime(t, "%I:%M%p").strftime("%H:%M")
    except: return t

def parse_html(html, debug=False):
    soup = BeautifulSoup(html, "html.parser")
    games = []

    if debug:
        h3s = soup.find_all("h3")
        links = [a for a in soup.find_all("a") if "/games/" in a.get("href","")]
        print(f"  [DEBUG] h3 태그: {len(h3s)}개, games 링크: {len(links)}개")
        if len(h3s) == 0:
            # JS 렌더링 여부 확인용: script 태그 수와 body 텍스트 일부 출력
            scripts = soup.find_all("script")
            print(f"  [DEBUG] script 태그: {len(scripts)}개")
            body = soup.find("body")
            if body:
                print(f"  [DEBUG] body 텍스트 처음 300자: {body.get_text()[:300]!r}")
        for h in h3s[:3]:
            print(f"  [DEBUG] h3: {h.get_text(strip=True)!r}")
        for l in links[:3]:
            print(f"  [DEBUG] link: href={l.get('href')} text={l.get_text(strip=True)[:60]!r}")

    slug_re = re.compile(r"/games/\d+-(.+?)-vs-(.+?)-\d{8}")
    time_re = re.compile(r"(\d+:\d+(?:am|pm))", re.I)
    result_re = re.compile(r"\d+\s*:\s*\d+\s*(?:Final|Cancelled|Postponed|Suspended)", re.I)
    current_date = None

    for tag in soup.find_all(["h3", "a"]):
        if tag.name == "h3":
            m = re.search(r"(\w+)\s+(\d+),\s+(\d{4})", tag.get_text(strip=True))
            if m:
                month = MONTH_MAP.get(m.group(1), 0)
                if month:
                    current_date = f"{m.group(3)}-{month:02d}-{int(m.group(2)):02d}"
        elif tag.name == "a" and current_date:
            href = tag.get("href", "")
            sm = slug_re.search(href)
            if not sm: continue
            away = SLUG_MAP.get(sm.group(1), sm.group(1))
            home = SLUG_MAP.get(sm.group(2), sm.group(2))
            text = tag.get_text(separator=" ", strip=True)
            tm = time_re.search(text)
            if tm:
                after = text[tm.end():].strip()
                for k in sorted(TEAM_MAP.keys(), key=len, reverse=True):
                    after = after.replace(k, "").strip()
                stadium = norm_stadium(after) or HOME_STADIUM.get(home, "")
                games.append({"date":current_date,"home":home,"away":away,
                              "stadium":stadium,"time":parse_time(tm.group(1))})
            elif result_re.search(text):
                games.append({"date":current_date,"home":home,"away":away,
                              "stadium":HOME_STADIUM.get(home,""),"time":""})
    return games

def fetch_week(date_str):
    url = f"https://mykbostats.com/schedule/week_of/{date_str}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.text

def week_monday(d):
    return d - timedelta(days=d.weekday())

def main():
    now = datetime.now()
    print(f"📅 KBO 일정 수집 시작 ({now.strftime('%Y-%m-%d %H:%M')})")
    seen, all_games = set(), []

    for week_offset in range(8):
        target = now + timedelta(weeks=week_offset)
        date_str = week_monday(target).strftime("%Y-%m-%d")
        try:
            html = fetch_week(date_str)
            games = parse_html(html, debug=(week_offset == 0))
            new = sum(1 for g in games if (g["date"],g["home"],g["away"]) not in seen
                      and not seen.add((g["date"],g["home"],g["away"])))
            all_games.extend(g for g in games if True)
            print(f"  {date_str}: {new}경기")
        except Exception as e:
            print(f"  {date_str}: 실패 - {e}")

    # 중복 제거 및 정렬
    seen2, unique = set(), []
    for g in all_games:
        k = (g["date"],g["home"],g["away"])
        if k not in seen2:
            seen2.add(k); unique.append(g)
    unique.sort(key=lambda x:(x["date"],x["home"]))

    output = {"updated":now.strftime("%Y-%m-%d %H:%M"),
              "source":"mykbostats.com","count":len(unique),"games":unique}
    with open("schedule.json","w",encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ schedule.json 저장 완료 (총 {len(unique)}경기)")

if __name__ == "__main__":
    main()

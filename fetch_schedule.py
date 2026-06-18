"""
KBO 경기 일정 수집 스크립트 (mykbostats.com 기반)
GitHub Actions에서 매일 새벽 자동 실행됩니다.
"""
import json, re, requests
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
    "Changwon":"창원","Seoul-Gocheok":"고척","Pohang":"포항","Ulsan":"울산","Cheongju":"청주",
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

def parse_time(t):
    """'6:30pm' 또는 '18:30' → '18:30'"""
    t = t.strip().lower().replace(" kst","")
    if re.match(r'^\d{1,2}:\d{2}$', t):
        return t  # 이미 24시간 형식
    try:
        return datetime.strptime(t, "%I:%M%p").strftime("%H:%M")
    except:
        try:
            return datetime.strptime(t, "%I:%M %p").strftime("%H:%M")
        except:
            return ""

def parse_html(html):
    soup = BeautifulSoup(html, "html.parser")
    games = []
    slug_re = re.compile(r"/games/\d+-(.+?)-vs-(.+?)-\d{8}")
    # 시간 패턴: 6:30pm, 5:00pm, 2:00pm 등
    time_re = re.compile(r"\b(\d{1,2}:\d{2}(?:am|pm))\b", re.I)
    # 결과 경기 패턴: 숫자:숫자 형태 스코어
    score_re = re.compile(r"\b\d+\s*:\s*\d+\b")
    status_re = re.compile(r"\b(Final|Cancelled|Postponed|Suspended)\b", re.I)
    current_date = None

    for tag in soup.find_all(["h3", "a"]):
        if tag.name == "h3":
            m = re.search(r"(\w+)\s+(\d+),\s+(\d{4})", tag.get_text(strip=True))
            if m:
                month = MONTH_MAP.get(m.group(1), 0)
                if month:
                    current_date = f"{m.group(3)}-{month:02d}-{int(m.group(2)):02d}"
            continue

        if not current_date:
            continue
        href = tag.get("href", "")
        sm = slug_re.search(href)
        if not sm:
            continue

        away = SLUG_MAP.get(sm.group(1), sm.group(1))
        home = SLUG_MAP.get(sm.group(2), sm.group(2))

        # 링크 내부 모든 텍스트 노드를 개별로 수집
        # BeautifulSoup의 strings로 공백 없이 붙어있는 문제 해결
        texts = list(tag.strings)  # 각 텍스트 노드 분리
        full_text = tag.get_text(separator=" ", strip=True)

        # 시간 추출 (텍스트 노드에서 직접)
        time_val = ""
        for t in texts:
            tm = time_re.search(t.strip())
            if tm:
                time_val = parse_time(tm.group(1))
                break
        # 못 찾으면 전체 텍스트에서 재시도
        if not time_val:
            tm = time_re.search(full_text)
            if tm:
                time_val = parse_time(tm.group(1))

        # 구장명 추출 (텍스트 노드에서)
        stadium_val = HOME_STADIUM.get(home, "")
        for t in texts:
            t = t.strip()
            if t in STADIUM_MAP:
                stadium_val = STADIUM_MAP[t]
                break

        # 예정 경기 vs 결과 경기 판별
        is_result = bool(score_re.search(full_text) and status_re.search(full_text))
        is_scheduled = bool(time_val and not is_result)

        if is_scheduled or is_result:
            games.append({
                "date": current_date,
                "home": home,
                "away": away,
                "stadium": stadium_val,
                "time": time_val if is_scheduled else "",
            })

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
            games = parse_html(html)
            new = 0
            for g in games:
                k = (g["date"], g["home"], g["away"])
                if k not in seen:
                    seen.add(k); all_games.append(g); new += 1
            print(f"  {date_str}: {new}경기")
        except Exception as e:
            print(f"  {date_str}: 실패 - {e}")

    all_games.sort(key=lambda x: (x["date"], x["home"]))
    output = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "source": "mykbostats.com",
        "count": len(all_games),
        "games": all_games,
    }
    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ schedule.json 저장 완료 (총 {len(all_games)}경기)")

if __name__ == "__main__":
    main()

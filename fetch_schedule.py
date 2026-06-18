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
    t = t.strip().lower()
    try: return datetime.strptime(t, "%I:%M%p").strftime("%H:%M")
    except: return t

def extract_game_info(tag, away_slug, home_slug):
    """
    링크 태그의 자식 노드들을 개별로 읽어서 시간/구장 추출
    구조: span.away_team | span.time | span.stadium | span.home_team
    또는 텍스트가 붙어있는 경우 slug에서만 홈/원정 판별
    """
    away = SLUG_MAP.get(away_slug, away_slug)
    home = SLUG_MAP.get(home_slug, home_slug)

    # 자식 span/div 텍스트를 리스트로 추출
    children = [c.get_text(strip=True) for c in tag.children
                if hasattr(c, 'get_text') and c.get_text(strip=True)]

    time_re = re.compile(r"^(\d+:\d+(?:am|pm))$", re.I)
    result_re = re.compile(r"\d+\s*:\s*\d+", re.I)
    status_re = re.compile(r"^(Final|Cancelled|Postponed|Suspended)$", re.I)

    time_val = ""
    stadium_val = HOME_STADIUM.get(home, "")
    is_scheduled = False
    is_result = False

    for ch in children:
        if time_re.match(ch):
            time_val = parse_time(ch)
            is_scheduled = True
        elif status_re.match(ch):
            is_result = True
        elif result_re.search(ch) and ":" in ch:
            # 스코어 포함 (결과 경기)
            is_result = True
        elif ch in STADIUM_MAP:
            stadium_val = STADIUM_MAP[ch]
        elif ch in TEAM_MAP:
            pass  # 팀명은 slug로 이미 처리

    # children이 모두 붙어있는 경우(공백 없음) → tag 전체 텍스트로 재시도
    full_text = tag.get_text(separator="|", strip=True)
    parts = [p.strip() for p in full_text.split("|") if p.strip()]

    for p in parts:
        if time_re.match(p):
            time_val = parse_time(p)
            is_scheduled = True
        elif p in STADIUM_MAP:
            stadium_val = STADIUM_MAP[p]
        elif status_re.match(p) or (result_re.search(p) and ":" in p):
            is_result = True

    return away, home, time_val, stadium_val, is_scheduled or is_result

def parse_html(html):
    soup = BeautifulSoup(html, "html.parser")
    games = []
    slug_re = re.compile(r"/games/\d+-(.+?)-vs-(.+?)-\d{8}")
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
            if not sm:
                continue
            away, home, time_val, stadium, valid = extract_game_info(
                tag, sm.group(1), sm.group(2)
            )
            if valid:
                games.append({
                    "date": current_date,
                    "home": home,
                    "away": away,
                    "stadium": stadium,
                    "time": time_val,
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
                    seen.add(k)
                    all_games.append(g)
                    new += 1
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

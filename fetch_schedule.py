"""
KBO 경기 일정 수집 스크립트 (mykbostats.com 기반)
GitHub Actions에서 매일 새벽 자동 실행됩니다.
"""

import json
import re
import requests
from datetime import datetime, timedelta

TEAM_MAP = {
    "Doosan Bears":  "두산",
    "Hanwha Eagles": "한화",
    "Kia Tigers":    "KIA",
    "Kiwoom Heroes": "키움",
    "KT Wiz":        "KT",
    "LG Twins":      "LG",
    "Lotte Giants":  "롯데",
    "NC Dinos":      "NC",
    "Samsung Lions": "삼성",
    "SSG Landers":   "SSG",
}

STADIUM_MAP = {
    "Seoul-Jamsil":   "잠실",
    "Suwon":          "수원",
    "Incheon":        "인천",
    "Incheon-Munhak": "인천",
    "Daejeon":        "대전",
    "Gwangju":        "광주",
    "Daegu":          "대구",
    "Busan-Sajik":    "사직",
    "Changwon":       "창원",
    "Seoul-Gocheok":  "고척",
    "Pohang":         "포항",
    "Ulsan":          "울산",
    "Cheongju":       "청주",
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
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def norm_team(name): return TEAM_MAP.get(name.strip(), name.strip())
def norm_stadium(name): return STADIUM_MAP.get(name.strip(), name.strip())
def parse_time(t):
    t = t.strip().lower()
    try: return datetime.strptime(t, "%I:%M%p").strftime("%H:%M")
    except: return t

def parse_html(html, debug=False):
    """mykbostats.com 마크다운 변환 HTML 파싱"""
    games = []
    current_date = None

    if debug:
        # 처음 50줄 출력해서 실제 구조 확인
        lines = html.splitlines()
        print(f"  [DEBUG] 총 {len(lines)}줄, 처음 60줄:")
        for i, l in enumerate(lines[:60]):
            if l.strip():
                print(f"    {i:3d}: {l[:120]}")

    date_re = re.compile(r"#{2,4}\s+\w+\s+(\w+)\s+(\d+),\s+(\d{4})")
    slug_re = re.compile(r"/games/\d+-(.+?)-vs-(.+?)-\d{8}")

    team_names = sorted(TEAM_MAP.keys(), key=len, reverse=True)
    tp = "|".join(re.escape(t) for t in team_names)

    # 예정 경기: [Away TIME STADIUM Home](url)
    sched_re = re.compile(
        rf"\[({tp})\s+(\d+:\d+(?:am|pm))\s+([A-Za-z\-]+)\s+({tp})\]\(([^)]+)\)"
    )
    # 결과 경기: [Team1 N : N Final Team2](url)
    result_re = re.compile(
        rf"\[({tp})\s+\d+\s*:\s*\d+\s*(?:Final|Cancelled|Postponed|Suspended)[^\]]*?({tp})\]\(([^)]+)\)"
    )

    matched_lines = 0
    for line in html.splitlines():
        line = line.strip()

        dm = date_re.search(line)
        if dm:
            month = MONTH_MAP.get(dm.group(1), 0)
            if month:
                current_date = f"{dm.group(3)}-{month:02d}-{int(dm.group(2)):02d}"
                if debug: print(f"  [DEBUG] 날짜: {current_date}")
            continue

        if not current_date:
            continue

        for m in sched_re.finditer(line):
            matched_lines += 1
            away = norm_team(m.group(1))
            home = norm_team(m.group(4))
            stadium = norm_stadium(m.group(3)) or HOME_STADIUM.get(home, "")
            games.append({"date": current_date, "home": home, "away": away,
                          "stadium": stadium, "time": parse_time(m.group(2))})

        for m in result_re.finditer(line):
            matched_lines += 1
            sm = slug_re.search(m.group(3))
            if sm:
                away = SLUG_MAP.get(sm.group(1), norm_team(m.group(1)))
                home = SLUG_MAP.get(sm.group(2), norm_team(m.group(2)))
            else:
                away, home = norm_team(m.group(1)), norm_team(m.group(2))
            games.append({"date": current_date, "home": home, "away": away,
                          "stadium": HOME_STADIUM.get(home, ""), "time": ""})

    if debug:
        print(f"  [DEBUG] 매칭된 경기 라인: {matched_lines}개, 파싱된 경기: {len(games)}개")

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

    seen = set()
    all_games = []

    for week_offset in range(8):
        target = now + timedelta(weeks=week_offset)
        monday = week_monday(target)
        date_str = monday.strftime("%Y-%m-%d")
        try:
            html = fetch_week(date_str)
            # 첫 번째 주만 디버그 출력
            debug = (week_offset == 0)
            games = parse_html(html, debug=debug)
            new = 0
            for g in games:
                key = (g["date"], g["home"], g["away"])
                if key not in seen:
                    seen.add(key)
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

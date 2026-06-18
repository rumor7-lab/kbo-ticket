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
    "Seoul-Jamsil":    "잠실",
    "Suwon":           "수원",
    "Incheon":         "인천",
    "Incheon-Munhak":  "인천",
    "Daejeon":         "대전",
    "Gwangju":         "광주",
    "Daegu":           "대구",
    "Busan-Sajik":     "사직",
    "Changwon":        "창원",
    "Seoul-Gocheok":   "고척",
    "Pohang":          "포항",
    "Ulsan":           "울산",
    "Cheongju":        "청주",
}

HOME_STADIUM = {
    "LG":"잠실","두산":"잠실","KT":"수원","SSG":"인천",
    "한화":"대전","KIA":"광주","삼성":"대구",
    "롯데":"사직","NC":"창원","키움":"고척",
}

MONTH_MAP = {
    "January":1,"February":2,"March":3,"April":4,"May":5,"June":6,
    "July":7,"August":8,"September":9,"October":10,"November":11,"December":12
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KBOScheduleBot/2.0)",
}

def norm_team(name):
    return TEAM_MAP.get(name.strip(), name.strip())

def norm_stadium(name):
    name = name.strip()
    return STADIUM_MAP.get(name, name)

def parse_time(t):
    """'6:30pm' → '18:30'"""
    t = t.strip().lower()
    try:
        return datetime.strptime(t, "%I:%M%p").strftime("%H:%M")
    except:
        return t

def parse_html(html):
    games = []
    current_date = None

    # 날짜 헤더: ### Tuesday June 19, 2026
    date_re = re.compile(r"#{2,4}\s+\w+\s+(\w+)\s+(\d+),\s+(\d{4})")

    # URL 슬러그에서 홈/원정 추출: games/ID-Away-vs-Home-DATE
    # 예) 13602-Kia-vs-KT-20260619 → away=Kia, home=KT
    slug_re = re.compile(r"/games/\d+-(.+?)-vs-(.+?)-\d{8}")

    # 팀명 역매핑 (슬러그용)
    SLUG_MAP = {
        "Kia":"KIA","KT":"KT","LG":"LG","NC":"NC","SSG":"SSG",
        "Doosan":"두산","Hanwha":"한화","Lotte":"롯데",
        "Samsung":"삼성","Kiwoom":"키움",
    }

    # 예정 경기: [Team1 TIME STADIUM Team2](url)
    # 예) [Kia Tigers 6:30pm Suwon KT Wiz](url)
    team_names = list(TEAM_MAP.keys())
    # 팀명 중 가장 긴 것부터 매칭하기 위해 정렬
    team_names_sorted = sorted(team_names, key=len, reverse=True)
    team_pattern = "|".join(re.escape(t) for t in team_names_sorted)

    # 예정 경기 패턴
    sched_re = re.compile(
        rf"\[({team_pattern})\s+(\d+:\d+(?:am|pm))\s+([A-Za-z\-]+)\s+({team_pattern})\]\((https?://[^)]+)\)"
    )
    # 결과 경기 패턴: [Team1 N : N Final Team2](url)
    result_re = re.compile(
        rf"\[({team_pattern})\s+\d+\s*:\s*\d+\s*(?:Final|Cancelled|Postponed|Suspended)[^]]*?({team_pattern})\]\((https?://[^)]+)\)"
    )

    for line in html.splitlines():
        line = line.strip()

        # 날짜 헤더
        dm = date_re.search(line)
        if dm:
            month = MONTH_MAP.get(dm.group(1), 0)
            day = int(dm.group(2))
            year = int(dm.group(3))
            if month:
                current_date = f"{year}-{month:02d}-{day:02d}"
            continue

        if not current_date:
            continue

        # 예정 경기
        for m in sched_re.finditer(line):
            away_en = m.group(1)
            time_raw = m.group(2)
            stadium_raw = m.group(3)
            home_en = m.group(4)
            url = m.group(5)

            away = norm_team(away_en)
            home = norm_team(home_en)
            stadium = norm_stadium(stadium_raw)
            if not stadium:
                stadium = HOME_STADIUM.get(home, "")
            time_fmt = parse_time(time_raw)

            games.append({
                "date": current_date,
                "home": home,
                "away": away,
                "stadium": stadium,
                "time": time_fmt,
            })

        # 결과 경기 (아직 stadium/time 정보 없으나 날짜는 있음)
        for m in result_re.finditer(line):
            team1_en = m.group(1)
            team2_en = m.group(2)
            url = m.group(3)

            # URL 슬러그로 홈/원정 판별
            sm = slug_re.search(url)
            if sm:
                away_slug = sm.group(1)
                home_slug = sm.group(2)
                away = SLUG_MAP.get(away_slug, norm_team(team1_en))
                home = SLUG_MAP.get(home_slug, norm_team(team2_en))
            else:
                away = norm_team(team1_en)
                home = norm_team(team2_en)

            stadium = HOME_STADIUM.get(home, "")
            games.append({
                "date": current_date,
                "home": home,
                "away": away,
                "stadium": stadium,
                "time": "",
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

    # 이번 주부터 7주 치 수집
    seen = set()
    all_games = []

    for week_offset in range(8):
        target = now + timedelta(weeks=week_offset)
        monday = week_monday(target)
        date_str = monday.strftime("%Y-%m-%d")
        try:
            html = fetch_week(date_str)
            games = parse_html(html)
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

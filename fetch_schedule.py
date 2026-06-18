"""
KBO 경기 일정 수집 스크립트 (mykbostats.com 기반)
GitHub Actions에서 매일 새벽 자동 실행됩니다.
"""

import json
import re
import requests
from datetime import datetime, timedelta

# ── 팀명 변환 (영문 → 한국어) ──────────────────────────
TEAM_MAP = {
    "Doosan Bears":   "두산",
    "Hanwha Eagles":  "한화",
    "Kia Tigers":     "KIA",
    "Kiwoom Heroes":  "키움",
    "KT Wiz":         "KT",
    "LG Twins":       "LG",
    "Lotte Giants":   "롯데",
    "NC Dinos":       "NC",
    "Samsung Lions":  "삼성",
    "SSG Landers":    "SSG",
}

# ── 구장명 변환 ────────────────────────────────────────
STADIUM_MAP = {
    "Seoul-Jamsil":  "잠실",
    "Suwon":         "수원",
    "Incheon":       "인천",
    "Daejeon":       "대전",
    "Gwangju":       "광주",
    "Daegu":         "대구",
    "Busan-Sajik":   "사직",
    "Changwon":      "창원",
    "Seoul-Gocheok": "고척",
    "Pohang":        "포항",
    "Ulsan":         "울산",
    "Cheongju":      "청주",
}

# 홈팀 기준 기본 구장 (구장 정보 없을 때 폴백)
HOME_STADIUM = {
    "LG": "잠실", "두산": "잠실", "KT": "수원", "SSG": "인천",
    "한화": "대전", "KIA": "광주", "삼성": "대구",
    "롯데": "사직", "NC": "창원", "키움": "고척",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KBOScheduleBot/2.0)",
    "Accept-Language": "en-US,en;q=0.9",
}

def normalize_team(name):
    name = name.strip()
    return TEAM_MAP.get(name, name)

def normalize_stadium(name):
    name = name.strip()
    for k, v in STADIUM_MAP.items():
        if k.lower() in name.lower():
            return v
    return name

def parse_time(time_str):
    """'6:30pm KST' → '18:30' 형태로 변환"""
    time_str = time_str.strip().lower().replace(" kst", "")
    try:
        t = datetime.strptime(time_str, "%I:%M%p")
        return t.strftime("%H:%M")
    except:
        return time_str

def fetch_week(date_str):
    """한 주치 전체 경기 일정 가져오기"""
    url = f"https://mykbostats.com/schedule/week_of/{date_str}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text

def parse_games_from_html(html):
    """
    mykbostats.com HTML에서 경기 파싱
    패턴 예시:
      ### Tuesday June 9, 2026
      [Doosan Bears 6 : 5 Final Lotte Giants](url)
      [Kia Tigers · 6:30pm · Daejeon · Hanwha Eagles](url)  ← 예정 경기
    """
    games = []
    current_date = None

    # 날짜 헤더 패턴
    date_pattern = re.compile(
        r"#{2,3}\s+\w+\s+(\w+)\s+(\d+),\s+(\d{4})"
    )
    # 결과 있는 경기: [Team1 N : N Final/Status Team2](url)
    result_pattern = re.compile(
        r"\[([A-Za-z\s]+?)\s+\d+\s*:\s*\d+\s*(?:Final|Cancelled|Postponed|Suspended)[^\]]*?([A-Za-z\s]+?)\]\(([^)]+)\)"
    )
    # 예정 경기: [Team1 · time · stadium · Team2](url)
    scheduled_pattern = re.compile(
        r"\[([A-Za-z\s]+?)\s*·\s*([\d:apm]+(?:\s*KST)?)\s*·\s*([^·\]]+?)\s*·\s*([A-Za-z\s]+?)\]\(([^)]+)\)"
    )

    MONTH_MAP = {
        "January":1,"February":2,"March":3,"April":4,"May":5,"June":6,
        "July":7,"August":8,"September":9,"October":10,"November":11,"December":12
    }

    for line in html.split("\n"):
        line = line.strip()

        # 날짜 파싱
        dm = date_pattern.search(line)
        if dm:
            month_name, day, year = dm.group(1), dm.group(2), dm.group(3)
            month = MONTH_MAP.get(month_name, 0)
            if month:
                current_date = f"{year}-{month:02d}-{int(day):02d}"
            continue

        if not current_date:
            continue

        # 예정 경기 파싱 (우선)
        sm = scheduled_pattern.search(line)
        if sm:
            away = normalize_team(sm.group(1))
            time_raw = sm.group(2)
            stadium_raw = sm.group(3)
            home = normalize_team(sm.group(4))
            time_fmt = parse_time(time_raw)
            stadium = normalize_stadium(stadium_raw)
            if not stadium:
                stadium = HOME_STADIUM.get(home, "")
            if home and away and home in TEAM_MAP.values() or away in TEAM_MAP.values():
                games.append({
                    "date": current_date,
                    "home": home,
                    "away": away,
                    "stadium": stadium,
                    "time": time_fmt,
                    "status": "scheduled"
                })
            continue

        # 결과 있는 경기 파싱
        rm = result_pattern.search(line)
        if rm:
            team1 = normalize_team(rm.group(1).strip())
            team2 = normalize_team(rm.group(2).strip())
            game_url = rm.group(3)
            # URL에서 구장 유추 불가 → 홈팀 기본 구장 사용
            # mykbostats에서는 첫 번째 팀이 원정, 두 번째가 홈 (또는 반대)
            # URL 슬러그에서 판별: games/ID-Away-vs-Home-DATE
            home, away = team2, team1  # 기본값
            stadium = HOME_STADIUM.get(home, "")
            games.append({
                "date": current_date,
                "home": home,
                "away": away,
                "stadium": stadium,
                "time": "",
                "status": "final"
            })

    return games

def get_mondays_for_range(start_date, end_date):
    """기간 내 모든 주의 월요일(또는 해당 주 시작일) 반환"""
    dates = []
    d = start_date - timedelta(days=start_date.weekday())  # 해당 주 월요일
    while d <= end_date:
        dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(weeks=1)
    return dates

def main():
    now = datetime.now()
    print(f"📅 KBO 일정 수집 시작 ({now.strftime('%Y-%m-%d %H:%M')})")

    # 오늘부터 6주 뒤까지 수집
    start = now
    end = now + timedelta(weeks=6)
    week_starts = get_mondays_for_range(start, end)

    all_games = []
    seen = set()

    for week_date in week_starts:
        try:
            html = fetch_week(week_date)
            games = parse_games_from_html(html)
            new = 0
            for g in games:
                key = (g["date"], g.get("home",""), g.get("away",""))
                if key not in seen:
                    seen.add(key)
                    all_games.append(g)
                    new += 1
            print(f"  {week_date}: {new}경기")
        except Exception as e:
            print(f"  {week_date}: 실패 - {e}")

    # 날짜순 정렬
    all_games.sort(key=lambda x: (x["date"], x.get("home","")))

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

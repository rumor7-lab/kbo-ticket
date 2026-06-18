"""
KBO 경기 일정 수집 스크립트
네이버 스포츠 API를 활용하여 당월 + 익월 일정을 가져와 schedule.json으로 저장합니다.
GitHub Actions에서 매일 새벽 자동 실행됩니다.
"""

import json
import requests
from datetime import datetime, timedelta
import sys

TEAM_NAME_MAP = {
    "LG": "LG", "KT": "KT", "SSG": "SSG", "NC": "NC",
    "두산": "두산", "KIA": "KIA", "롯데": "롯데",
    "삼성": "삼성", "한화": "한화", "키움": "키움",
    "LG트윈스": "LG", "KT위즈": "KT", "SSG랜더스": "SSG",
    "NC다이노스": "NC", "두산베어스": "두산", "KIA타이거즈": "KIA",
    "롯데자이언츠": "롯데", "삼성라이온즈": "삼성",
    "한화이글스": "한화", "키움히어로즈": "키움",
}

STADIUM_MAP = {
    "잠실": "잠실", "수원": "수원", "인천": "인천", "대전": "대전",
    "광주": "광주", "대구": "대구", "사직": "사직", "창원": "창원",
    "고척": "고척", "수원KT위즈파크": "수원", "인천SSG랜더스필드": "인천",
    "대전한화생명이글스파크": "대전", "광주기아챔피언스필드": "광주",
    "대구삼성라이온즈파크": "대구", "사직야구장": "사직",
    "창원NC파크": "창원", "고척스카이돔": "고척",
    "잠실야구장": "잠실",
}

def normalize_team(name):
    for k, v in TEAM_NAME_MAP.items():
        if k in name:
            return v
    return name.strip()

def normalize_stadium(name):
    for k, v in STADIUM_MAP.items():
        if k in name:
            return v
    return name.strip()

def fetch_naver_schedule(year, month):
    """네이버 스포츠 KBO 월별 일정 API"""
    url = f"https://sports.news.naver.com/kbaseball/schedule/index.nhn?month={month:02d}&year={year}"
    # 네이버 스포츠 내부 API (공개 JSON 엔드포인트)
    api_url = f"https://sports.news.naver.com/kbaseball/schedule/ajax.nhn?category=kbo&year={year}&month={month:02d}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; KBO-Schedule-Bot/1.0)",
        "Referer": "https://sports.news.naver.com/kbaseball/schedule/index.nhn",
    }
    
    resp = requests.get(api_url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.text

def parse_naver_html(html, year, month):
    """네이버 스포츠 HTML에서 경기 일정 파싱"""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, "html.parser")
    games = []
    
    # 날짜별 경기 행 파싱
    rows = soup.select("tr")
    current_date = None
    
    for row in rows:
        # 날짜 셀
        date_cell = row.select_one("td.td_date")
        if date_cell:
            day_text = date_cell.get_text(strip=True)
            try:
                day = int(''.join(filter(str.isdigit, day_text[:2])))
                current_date = f"{year}-{month:02d}-{day:02d}"
            except:
                pass
        
        if not current_date:
            continue
        
        # 경기 정보 셀
        game_cells = row.select("td.td_team")
        time_cell = row.select_one("td.td_time")
        stadium_cell = row.select_one("td.td_stadium")
        
        if not game_cells or len(game_cells) < 2:
            # 대안: 팀명이 포함된 다른 셀 구조 시도
            home_cell = row.select_one(".home em") or row.select_one(".team_home")
            away_cell = row.select_one(".away em") or row.select_one(".team_away")
            if home_cell and away_cell:
                home = normalize_team(home_cell.get_text(strip=True))
                away = normalize_team(away_cell.get_text(strip=True))
                time_text = time_cell.get_text(strip=True) if time_cell else "18:30"
                stadium_text = normalize_stadium(stadium_cell.get_text(strip=True)) if stadium_cell else ""
                
                if home and away and home != away:
                    games.append({
                        "date": current_date,
                        "home": home,
                        "away": away,
                        "stadium": stadium_text,
                        "time": time_text,
                    })
    
    return games

def fetch_month_games(year, month):
    """한 달치 경기 일정 가져오기"""
    try:
        html = fetch_naver_schedule(year, month)
        games = parse_naver_html(html, year, month)
        print(f"  {year}-{month:02d}: {len(games)}경기 파싱 완료")
        return games
    except Exception as e:
        print(f"  {year}-{month:02d}: 파싱 실패 - {e}", file=sys.stderr)
        return []

def main():
    now = datetime.now()
    all_games = []
    
    # 이번 달 + 다음 달 수집
    months_to_fetch = []
    for delta in range(0, 2):
        target = now + timedelta(days=delta * 31)
        months_to_fetch.append((target.year, target.month))
    
    # 중복 제거
    months_to_fetch = list(dict.fromkeys(months_to_fetch))
    
    print(f"📅 KBO 일정 수집 시작 ({now.strftime('%Y-%m-%d %H:%M')})")
    for year, month in months_to_fetch:
        games = fetch_month_games(year, month)
        all_games.extend(games)
    
    # 날짜순 정렬 & 중복 제거
    seen = set()
    unique_games = []
    for g in sorted(all_games, key=lambda x: (x["date"], x.get("home",""))):
        key = (g["date"], g.get("home",""), g.get("away",""))
        if key not in seen:
            seen.add(key)
            unique_games.append(g)
    
    output = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "count": len(unique_games),
        "games": unique_games,
    }
    
    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✅ schedule.json 저장 완료 (총 {len(unique_games)}경기)")

if __name__ == "__main__":
    main()

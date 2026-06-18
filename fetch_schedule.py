"""
KBO 경기 일정 + 순위 수집 스크립트 (mykbostats.com 기반)
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
    t = t.strip().lower().replace(" kst","")
    if re.match(r'^\d{1,2}:\d{2}$', t): return t
    try: return datetime.strptime(t, "%I:%M%p").strftime("%H:%M")
    except:
        try: return datetime.strptime(t, "%I:%M %p").strftime("%H:%M")
        except: return ""

# ── 순위 파싱 ────────────────────────────────────────────
def fetch_standings():
    r = requests.get("https://mykbostats.com/", headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    standings = []

    # 순위 테이블 찾기: "KBO 2026 Standings" h3 다음 table
    table = None
    for h3 in soup.find_all("h3"):
        if "Standings" in h3.get_text():
            table = h3.find_next("table")
            break

    if not table:
        print("  순위 테이블 없음")
        return []

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        try:
            rank_team = cells[0].get_text(separator=" ", strip=True)
            # "1 LG Twins" → rank=1, team_en="LG Twins"
            m = re.match(r"(\d+)\s+(.+)", rank_team)
            if not m:
                continue
            rank = int(m.group(1))
            team_en = m.group(2).strip()
            team_ko = TEAM_MAP.get(team_en, team_en)

            w   = int(cells[1].get_text(strip=True))
            l   = int(cells[2].get_text(strip=True))
            d   = int(cells[3].get_text(strip=True))
            pct = cells[4].get_text(strip=True)
            gb  = cells[5].get_text(strip=True)
            streak_raw = cells[6].get_text(strip=True) if len(cells) > 6 else ""

            # STRK/LAST10 파싱: "1L / 6W 0D 4L"
            streak, last10 = "", ""
            if "/" in streak_raw:
                parts = streak_raw.split("/")
                streak = parts[0].strip()    # "1L" or "3W"
                last10 = parts[1].strip()    # "6W 0D 4L"

            standings.append({
                "rank": rank,
                "team": team_ko,
                "w": w, "l": l, "d": d,
                "pct": pct,
                "gb": gb,
                "streak": streak,
                "last10": last10,
            })
        except Exception as e:
            continue

    print(f"  순위: {len(standings)}팀 파싱 완료")
    return standings

# ── 일정 파싱 ────────────────────────────────────────────
def parse_schedule_html(html):
    soup = BeautifulSoup(html, "html.parser")
    games = []
    slug_re = re.compile(r"/games/\d+-(.+?)-vs-(.+?)-\d{8}")
    time_re = re.compile(r"\b(\d{1,2}:\d{2}(?:am|pm))\b", re.I)
    score_re = re.compile(r"\b(\d+)\s*:\s*(\d+)\b")
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
        if not current_date: continue
        href = tag.get("href", "")
        sm = slug_re.search(href)
        if not sm: continue

        away = SLUG_MAP.get(sm.group(1), sm.group(1))
        home = SLUG_MAP.get(sm.group(2), sm.group(2))
        texts = list(tag.strings)
        full_text = tag.get_text(separator=" ", strip=True)

        time_val = ""
        for t in texts:
            tm = time_re.search(t.strip())
            if tm: time_val = parse_time(tm.group(1)); break
        if not time_val:
            tm = time_re.search(full_text)
            if tm: time_val = parse_time(tm.group(1))

        stadium_val = HOME_STADIUM.get(home, "")
        for t in texts:
            t = t.strip()
            if t in STADIUM_MAP: stadium_val = STADIUM_MAP[t]; break

        is_result = bool(score_re.search(full_text) and status_re.search(full_text))
        is_scheduled = bool(time_val and not is_result)

        score_away, score_home = None, None
        if is_result:
            sm2 = score_re.search(full_text)
            if sm2:
                score_away = int(sm2.group(1))
                score_home = int(sm2.group(2))

        if is_scheduled or is_result:
            game = {
                "date": current_date,
                "home": home, "away": away,
                "stadium": stadium_val,
                "time": time_val if is_scheduled else "",
            }
            if is_result and score_away is not None:
                game["score_away"] = score_away
                game["score_home"] = score_home
            games.append(game)
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
    print(f"📅 KBO 데이터 수집 시작 ({now.strftime('%Y-%m-%d %H:%M')})")

    # 순위 수집
    standings = []
    try:
        standings = fetch_standings()
    except Exception as e:
        print(f"  순위 수집 실패 - {e}")

    # 일정 수집
    seen, all_games = set(), []
    for week_offset in range(8):
        target = now + timedelta(weeks=week_offset)
        date_str = week_monday(target).strftime("%Y-%m-%d")
        try:
            html = fetch_week(date_str)
            games = parse_schedule_html(html)
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
        "standings": standings,
        "count": len(all_games),
        "games": all_games,
    }
    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ schedule.json 저장 완료 (총 {len(all_games)}경기, 순위 {len(standings)}팀)")

if __name__ == "__main__":
    main()

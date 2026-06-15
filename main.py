import asyncio
import time
import os
import json
import re
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

STREAMERS = {
    1: "Dunduk", 2: "F1ashko", 3: "GladValakas", 4: "KarmikKoala",
    5: "Lasqa", 6: "Maddyson", 7: "Melharucos", 8: "Nenormova",
    9: "Praden", 10: "ViktorZu", 11: "C_a_k_e", 12: "Arrowwoods"
}

STREAMERS_BY_NAME = {name.lower().strip(): num for num, name in STREAMERS.items()}
VALID_NAMES = {name.lower().strip() for name in STREAMERS.values()}

API_URL = "https://api-game.nassal.pro/api/public/player/list"
ACHIEVEMENTS_URL = "https://api-game.nassal.pro/api/public/achievements"
GROUPS_FILE = "monitoring_groups.json"
ADMINS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "417850992").split(",") if x.strip().isdigit()]

EVENT_END_MSK = datetime(2026, 6, 19, 19, 0, 0)
MSK_OFFSET = timedelta(hours=3)

NUMBERS_WORDS = {
    1: "одно", 2: "два", 3: "три", 4: "четыре", 5: "пять",
    6: "шесть", 7: "семь", 8: "восемь", 9: "девять", 10: "десять",
    11: "одиннадцать", 12: "двенадцать", 13: "тринадцать", 14: "четырнадцать",
    15: "пятнадцать", 16: "шестнадцать", 17: "семнадцать", 18: "восемнадцать",
    19: "девятнадцать", 20: "двадцать"
}


def format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0м"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}ч {m}м {s}с"
    elif m > 0:
        return f"{m}м {s}с"
    return f"{s}с"


def format_duration_short(seconds: int) -> str:
    if seconds <= 0:
        return "0м"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h}ч {m}м"
    elif m > 0:
        return f"{m}м"
    return f"{seconds}с"


def elapsed_since(iso_str: str) -> int:
    if not iso_str:
        return 0
    try:
        iso_str = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_str)
        return int((datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        return 0


class NassalMonitor:
    def __init__(self, bot_token: str):
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        self.previous_data: Dict = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.monitoring_groups: List[Dict] = self.load_groups()
        self.monitoring_active: bool = False
        self.player_cache: Dict[str, Dict] = {}
        self.monitor_loop_task: Optional[asyncio.Task] = None
        self.achievements_cache: Optional[Dict] = None
        self.achievements_cache_time: float = 0
        self.api_cache: Optional[Dict] = None
        self.api_cache_time: float = 0
        self.API_CACHE_TTL = 15
        self.event_sent_notifications: set = set()
        self.event_end_msk: datetime = EVENT_END_MSK

    def _now_msk(self) -> datetime:
        return datetime.now(timezone.utc) + MSK_OFFSET

    def _event_end_utc(self) -> datetime:
        return self.event_end_msk.replace(tzinfo=timezone(timedelta(hours=3)))

    def _time_until_event(self) -> timedelta:
        return self._event_end_utc() - datetime.now(timezone.utc)

    def _format_countdown(self, delta: timedelta) -> str:
        total_sec = int(delta.total_seconds())
        if total_sec <= 0:
            return "Ивент завершён!"
        days = total_sec // 86400
        hours = (total_sec % 86400) // 3600
        minutes = (total_sec % 3600) // 60
        seconds = total_sec % 60
        parts = []
        if days > 0:
            if days % 10 == 1 and days % 100 != 11:
                parts.append(f"{days} день")
            elif days % 10 in [2, 3, 4] and days % 100 not in [12, 13, 14]:
                parts.append(f"{days} дня")
            else:
                parts.append(f"{days} дней")
        if hours > 0:
            if hours % 10 == 1 and hours % 100 != 11:
                parts.append(f"{hours} час")
            elif hours % 10 in [2, 3, 4] and hours % 100 not in [12, 13, 14]:
                parts.append(f"{hours} часа")
            else:
                parts.append(f"{hours} часов")
        if minutes > 0:
            if minutes % 10 == 1 and minutes % 100 != 11:
                parts.append(f"{minutes} минута")
            elif minutes % 10 in [2, 3, 4] and minutes % 100 not in [12, 13, 14]:
                parts.append(f"{minutes} минуты")
            else:
                parts.append(f"{minutes} минут")
        if seconds > 0:
            if seconds % 10 == 1 and seconds % 100 != 11:
                parts.append(f"{seconds} секунда")
            elif seconds % 10 in [2, 3, 4] and seconds % 100 not in [12, 13, 14]:
                parts.append(f"{seconds} секунды")
            else:
                parts.append(f"{seconds} секунд")
        return ", ".join(parts) if parts else "Менее секунды"

    def _is_event_ended(self) -> bool:
        return datetime.now(timezone.utc) >= self._event_end_utc()

    def _is_final_day(self) -> bool:
        now_msk = self._now_msk()
        return now_msk.date() == self.event_end_msk.date()

    def _get_notification_key(self, kind: str, hour: int = -1) -> str:
        now_msk = self._now_msk()
        return f"{kind}_{now_msk.date()}_{hour}" if hour >= 0 else f"{kind}_{now_msk.date()}"

    def load_groups(self) -> List[Dict]:
        try:
            if os.path.exists(GROUPS_FILE):
                with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading groups: {e}")
        return []

    def save_groups(self):
        try:
            with open(GROUPS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.monitoring_groups, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving groups: {e}")

    def is_admin(self, user_id: int) -> bool:
        return user_id in ADMINS

    def get_streamer_keyboard(self) -> ReplyKeyboardMarkup:
        keyboard = []
        row = []
        for num, name in STREAMERS.items():
            row.append(KeyboardButton(text=f"{num}. {name}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    def _number_to_word(self, number: int) -> str:
        number = abs(number)
        return NUMBERS_WORDS.get(number, str(number))

    def _get_position_word(self, count: int) -> str:
        count = abs(count)
        if count % 10 == 1 and count % 100 != 11:
            return "место"
        elif count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]:
            return "места"
        return "мест"

    def _visible_len(self, text: str) -> int:
        clean = re.sub(r'<[^>]+>', '', text)
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251"
            "\U0001f926-\U0001f937\U00010000-\U0010ffff\u2640-\u2642"
            "\u2600-\u2B55\u200d\u23cf\u23e9\u231a\ufe0f\u3030]+", flags=re.UNICODE)
        clean = emoji_pattern.sub('', clean)
        return len(clean)

    def _parse_participant(self, item: dict) -> Optional[tuple]:
        player = item.get('player')

        if player is None:
            auction_result = item.get('currentAuctionResult') or {}
            player_id = auction_result.get('playerId', '')
            if player_id and player_id in self.player_cache:
                cached = self.player_cache[player_id]
                name = cached['name']
                points = cached['points']
            else:
                return None
        else:
            raw_name = player.get('name', '')
            name = raw_name.strip() if raw_name else ''
            if name.lower() not in VALID_NAMES:
                return None
            points = player.get('ggp', player.get('points', player.get('score', 0)))
            player_id = player.get('id', '')
            if player_id:
                self.player_cache[player_id] = {'name': name, 'points': points, 'timestamp': time.time()}

        auction_result = item.get('currentAuctionResult') or {}
        required_action = item.get('requiredAction') or {}
        action_kind = required_action.get('kind', '') if required_action else ''

        stream_info = item.get('stream') or []
        is_streaming = False
        streaming_platforms = []
        for stream in stream_info:
            if stream.get('online', False):
                is_streaming = True
                streaming_platforms.append({
                    'platform': stream.get('platform', 'unknown'),
                    'username': stream.get('username', '')
                })

        social_links = item.get('socialLinks') or []
        player_data = item.get('player') or {}
        inventory_effects = item.get('inventoryEffects') or []
        attached_effects = item.get('attachedEffects') or []
        auction_result_stats = item.get('auctionResultStats') or {}
        roll_impact_stats = item.get('rollImpactStats') or {}
        roll_kind_stats = item.get('rollKindStats') or {}

        ar = auction_result
        pd = player_data

        result = {
            'points': points,
            'selected': False,
            'game_title': ar.get('title', '') if ar else '',
            'game_type': ar.get('type', '') if ar else '',
            'game_reward': ar.get('ggpReward', 0) if ar else 0,
            'game_penalty': ar.get('ggpPenalty', 0) if ar else 0,
            'action_kind': action_kind,
            'timer_started': ar.get('timerStartedAt', '') if ar else '',
            'is_streaming': is_streaming,
            'streaming_platforms': streaming_platforms,
            'timestamp': time.time(),
            'hltb_seconds': ar.get('seconds', 0) if ar else 0,
            'hltb_game_id': ar.get('hltbGameId') if ar else None,
            'game_image': ar.get('imageUrl', '') if ar else '',
            'release_year': ar.get('releaseYear') if ar else None,
            'review_score': ar.get('reviewScore') if ar else None,
            'steam_app_id': ar.get('steamAppId') if ar else None,
            'fastest_time': ar.get('fastestFinalSpentSec') if ar else None,
            'fastest_player': ar.get('fastestPlayerName', '') if ar else '',
            'timer_accumulated': ar.get('timerAccumulatedSec', 0) if ar else 0,
            'auction_status': ar.get('status', '') if ar else '',
            'social_links': social_links,
            'inventory_effects': inventory_effects,
            'attached_effects': attached_effects,
            'turn': pd.get('turn', 0),
            'game_streak': pd.get('gameStreak', 0),
            'platinum_chips': pd.get('platinumChips', 0),
            'chips_spent_turn': pd.get('regularChipsSpentInTurn', 0),
            'chips_spent_total': pd.get('regularChipsSpentTotal', 0),
            'platinum_spent_total': pd.get('platinumChipsSpentTotal', 0),
            'slot_streak': pd.get('slotStreak', 0),
            'drop_count': pd.get('dropCount', 0),
            'ggp_lost_total': pd.get('ggpLostTotal', 0),
            'ggp_earned_total': pd.get('ggpEarnedTotal', 0),
            'gnus_available': pd.get('gnusAvailable', 0),
            'casino_phase': pd.get('casinoPhase'),
            'player_status': pd.get('status', ''),
            'player_achievements': pd.get('achievements') or [],
            'dropped': auction_result_stats.get('dropped', 0),
            'completed': auction_result_stats.get('completed', 0),
            'rerolled': auction_result_stats.get('rerolled', 0),
            'total_playtime': auction_result_stats.get('totalPlaytimeSec', 0),
            'ggp_net_games': auction_result_stats.get('ggpNetFromGames', 0),
            'roll_positive': roll_impact_stats.get('positive', 0),
            'roll_negative': roll_impact_stats.get('negative', 0),
            'roll_neutral': roll_impact_stats.get('neutral', 0),
            'roll_total': roll_kind_stats.get('total', 0),
            'roll_regular': roll_kind_stats.get('regular', 0),
            'roll_platinum': roll_kind_stats.get('platinum', 0),
            'avg_rolls_turn': roll_kind_stats.get('avgRollsPerTurn', 0),
            'player_review': ar.get('playerReview') if ar else None,
            'player_rating': ar.get('playerRating') if ar else None,
            'auction_id': ar.get('id') if ar else None,
        }

        return (name, result)

    async def get_participants_data(self) -> Dict:
        now = time.time()
        if self.api_cache and (now - self.api_cache_time) < self.API_CACHE_TTL:
            return self.api_cache

        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(API_URL) as response:
                if response.status != 200:
                    return self.api_cache or {}

                data = await response.json()
                participants = {}
                raw_array = data.get('data', {}).get('array', [])

                for idx, item in enumerate(raw_array):
                    try:
                        if item is None:
                            continue
                        result = self._parse_participant(item)
                        if result is None:
                            continue
                        name, info = result
                        participants[name] = info
                    except Exception as e:
                        logger.warning(f"[{idx}] Parse error: {e}")
                        continue

                if participants:
                    active_name = None
                    latest_time = ""
                    for name, info in participants.items():
                        timer = info.get('timer_started', '')
                        if timer and timer > latest_time:
                            latest_time = timer
                            active_name = name
                    if not active_name:
                        for name, info in participants.items():
                            action = info.get('action_kind', '')
                            if action and action != 'none':
                                active_name = name
                                break
                    if active_name:
                        participants[active_name]['selected'] = True

                self.api_cache = participants
                self.api_cache_time = now
                return participants

        except Exception as e:
            logger.error(f"Error getting data: {e}", exc_info=True)
            return self.api_cache or {}

    async def get_achievements_data(self) -> Dict:
        now = time.time()
        if self.achievements_cache and (now - self.achievements_cache_time) < 300:
            return self.achievements_cache

        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            async with self.session.get(ACHIEVEMENTS_URL) as response:
                if response.status != 200:
                    return self.achievements_cache or {}
                data = await response.json()
                self.achievements_cache = data.get('data', {})
                self.achievements_cache_time = now
                return self.achievements_cache
        except Exception as e:
            logger.error(f"Error getting achievements: {e}")
            return self.achievements_cache or {}

    async def search_hltb(self, query: str) -> Optional[Dict]:
        try:
            from howlongtobeatpy import HowLongToBeat
            hltb = HowLongToBeat()
            results = await hltb.async_search(query)
            if not results:
                return None
            best = max(results, key=lambda x: x.similarity)

            extra = {}
            try:
                if not self.session:
                    self.session = aiohttp.ClientSession()
                async with self.session.get(best.game_web_link, timeout=aiohttp.ClientTimeout(total=15), headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        import re as re_mod
                        dev = re_mod.findall(r'"profile_dev":"([^"]*)"', html)
                        pub = re_mod.findall(r'"profile_pub":"([^"]*)"', html)
                        genre = re_mod.findall(r'"profile_genre":"([^"]*)"', html)
                        platforms = re_mod.findall(r'"profile_platform":"([^"]*)"', html)
                        release = re_mod.findall(r'"release_world":(\d+)', html)
                        na_date = re_mod.findall(r'"release_na":"([^"]*)"', html)
                        eu_date = re_mod.findall(r'"release_eu":"([^"]*)"', html)
                        jp_date = re_mod.findall(r'"release_jp":"([^"]*)"', html)
                        if dev: extra["developer"] = dev[0]
                        if pub: extra["publisher"] = pub[0]
                        if genre: extra["genres"] = genre[0]
                        if platforms: extra["platforms"] = platforms[0]
                        if release: extra["release_year"] = release[0]
                        if na_date: extra["release_na"] = na_date[0]
                        if eu_date: extra["release_eu"] = eu_date[0]
                        if jp_date: extra["release_jp"] = jp_date[0]
            except Exception as e:
                logger.warning(f"HLTB page scrape failed: {e}")

            plat = extra.get("platforms", "")
            if not plat and hasattr(best, 'profile_platforms') and best.profile_platforms:
                plat = ", ".join(best.profile_platforms) if isinstance(best.profile_platforms, list) else str(best.profile_platforms)

            rel = extra.get("release_year", "")
            if not rel and hasattr(best, 'release_world') and best.release_world:
                rel = str(best.release_world)

            return {
                "name": best.game_name,
                "id": best.game_id,
                "main_time": int(best.main_story * 3600) if best.main_story else 0,
                "extra_time": int(best.main_extra * 3600) if best.main_extra else 0,
                "hundred_time": int(best.completionist * 3600) if best.completionist else 0,
                "url": best.game_web_link,
                "platforms": plat,
                "developer": extra.get("developer", ""),
                "publisher": extra.get("publisher", ""),
                "genres": extra.get("genres", ""),
                "release_year": rel,
                "release_na": extra.get("release_na", ""),
                "release_eu": extra.get("release_eu", ""),
                "release_jp": extra.get("release_jp", ""),
            }
        except ImportError:
            logger.warning("howlongtobeatpy not installed. Run: pip install howlongtobeatpy")
            return None
        except Exception as e:
            logger.error(f"HLTB search error: {e}")
            return None

    def _get_leaderboard(self, data: Dict) -> list:
        return sorted(data.items(), key=lambda x: x[1]['points'], reverse=True)

    def _get_real_position(self, data: Dict, streamer_name: str) -> int:
        for i, (name, _) in enumerate(self._get_leaderboard(data), 1):
            if name == streamer_name:
                return i
        return 0

    def _format_streaming_status(self, is_streaming: bool, platforms: List[Dict]) -> str:
        if not is_streaming or not platforms:
            return "\U0001f534 <b>Стрим:</b> Оффлайн"
        platform_emojis = {
            'twitch': '\U0001f7e3 Twitch', 'youtube': '\U0001f534 YouTube',
            'kick': '\U0001f7e2 Kick', 'telegram': '\u2708\ufe0f Telegram',
            'vk': '\U0001f535 VK', 'wtv': '\U0001f4fa WTV', 'vklive': '\U0001f535 VK Live'
        }
        names = [platform_emojis.get(p.get('platform', '').lower(), p.get('platform', '').capitalize()) for p in platforms]
        return f"\U0001f7e2 <b>Стрим:</b> Онлайн ({', '.join(names)})"

    def _format_streaming_status_short(self, is_streaming: bool, platforms: List[Dict]) -> str:
        return "\U0001f7e2" if is_streaming else "\U0001f534"

    def _format_activity_short(self, info: Dict) -> str:
        game_title = info.get('game_title', '')
        game_type = info.get('game_type', '')
        action_kind = info.get('action_kind', '')
        timer_started = info.get('timer_started', '')
        game_reward = info.get('game_reward', 0)
        game_penalty = info.get('game_penalty', 0)
        casino_phase = info.get('casino_phase')

        if game_title:
            reward_str = ""
            if game_reward or game_penalty:
                parts = []
                if game_reward:
                    parts.append(f"+{game_reward}")
                if game_penalty:
                    parts.append(f"-{game_penalty}")
                reward_str = f" ({'/'.join(parts)})"
            prefix = "\U0001f3ae" if game_type == 'game' else "\U0001f4fa"
            label = "Категория" if game_type == 'game' else "Смотрит"
            return f"{prefix} {label}: {game_title}{reward_str}"
        elif action_kind and action_kind == 'auction':
            return "\U0001f3af Категория: Аукцион"
        elif casino_phase:
            return "\U0001f3b0 Категория: В казино"
        elif timer_started or (action_kind and action_kind != 'none'):
            return "\U0001f3b1 Категория: Крутит колесо"
        return "\u26aa Категория: Ожидание"

    def _format_timer_line(self, info: Dict) -> str:
        timer_started = info.get('timer_started', '')
        if not timer_started:
            return ""
        accumulated = info.get('timer_accumulated', 0)
        elapsed = accumulated + elapsed_since(timer_started)
        hltb = info.get('hltb_seconds', 0)
        timer_str = format_duration(elapsed)
        game_type = info.get('game_type', '')
        timer_label = "Играет" if game_type == 'game' else "Смотрит"
        if hltb > 0:
            return f"\u23f1 <b>{timer_label}:</b> {timer_str}\n\U0001f552 <b>HLTB:</b> {format_duration(hltb)}"
        return f"\u23f1 <b>{timer_label}:</b> {timer_str}"

    def _resolve_streamer(self, query: str) -> Optional[str]:
        if query.isdigit():
            return STREAMERS.get(int(query))
        q = query.lower().strip()
        if q in STREAMERS_BY_NAME:
            return STREAMERS[STREAMERS_BY_NAME[q]]
        for name in STREAMERS.values():
            if q in name.lower():
                return name
        return None

    async def get_detailed_streamer_info(self, streamer_name: str) -> Optional[str]:
        try:
            if streamer_name not in STREAMERS.values():
                return None
            data = await self.get_participants_data()
            if streamer_name not in data:
                return None

            info = data[streamer_name]
            real_position = self._get_real_position(data, streamer_name)
            points = info['points']
            points_str = f"+{points}" if points > 0 else str(points)

            msg = f"\U0001f464 <b>{streamer_name}</b>\n"
            msg += f"\U0001f3c6 <b>Место:</b> {real_position} из {len(data)}\n"
            msg += f"\u2b50 <b>Очки:</b> {points_str}\n"
            msg += f"{self._format_streaming_status(info.get('is_streaming', False), info.get('streaming_platforms', []))}\n"

            game_title = info.get('game_title', '')
            game_type = info.get('game_type', '')
            action_kind = info.get('action_kind', '')
            timer_started = info.get('timer_started', '')
            game_reward = info.get('game_reward', 0)
            game_penalty = info.get('game_penalty', 0)

            if game_title:
                prefix = "\U0001f3ae <b>Игра:</b>" if game_type == 'game' else "\U0001f4fa <b>Смотрит:</b>"
                year = info.get('release_year')
                msg += f"\n{prefix} {game_title}"
                if year:
                    msg += f" ({year})"
                msg += "\n"

                review = info.get('review_score')
                if review is not None:
                    emoji = "\U0001f44d" if review >= 75 else ("\U0001f914" if review >= 50 else "\U0001f44e")
                    msg += f"  {emoji} Оценка: {review}/100\n"

                hltb = info.get('hltb_seconds', 0)
                hltb_id = info.get('hltb_game_id')

                hltb_data = None
                try:
                    hltb_data = await self.search_hltb(game_title)
                except Exception:
                    pass

                if hltb_data:
                    dev = hltb_data.get("developer", "")
                    pub = hltb_data.get("publisher", "")
                    genres = hltb_data.get("genres", "")
                    platforms = hltb_data.get("platforms", "")
                    if dev:
                        msg += f"  \U0001f3d7 Разработчик: {dev}\n"
                    if pub:
                        msg += f"  \U0001f4e2 Издатель: {pub}\n"
                    if genres:
                        msg += f"  \U0001f3a8 Жанры: {genres}\n"
                    if platforms:
                        msg += f"  \u2328 Платформы: {platforms}\n"
                elif hltb_id and hltb > 0:
                    pass

                if hltb_id and hltb > 0:
                    msg += f"  \U0001f552 HLTB: <a href='https://howlongtobeat.com/game/{hltb_id}'>{format_duration(hltb)}</a>\n"
                elif hltb_data and hltb_data.get("main_time", 0) > 0:
                    msg += f"  \U0001f552 HLTB: <a href='https://howlongtobeat.com/game/{hltb_data.get('id', '')}'>{format_duration(hltb_data['main_time'])}</a>\n"

                steam_id = info.get('steam_app_id')
                if steam_id:
                    msg += f"  \u2699\ufe0f Steam: <a href='https://store.steampowered.com/app/{steam_id}'>открыть</a>\n"

                ft = info.get('fastest_time')
                fp = info.get('fastest_player')
                if ft and fp:
                    msg += f"  \u26a1 Рекорд: {format_duration(ft)} ({fp})\n"

                ts = info.get('timer_started', '')
                acc = info.get('timer_accumulated', 0)
                if ts:
                    el = acc + elapsed_since(ts)
                    msg += f"\n\u23f1 <b>Текущее время:</b> {format_duration(el)}\n"
                    if hltb > 0:
                        msg += f"\U0001f552 <b>HLTB:</b> {format_duration(hltb)}\n"
                elif acc > 0:
                    msg += f"\n\u23f1 <b>На паузе:</b> {format_duration(acc)}\n"
                    if hltb > 0:
                        msg += f"\U0001f552 <b>HLTB:</b> {format_duration(hltb)}\n"

                if game_reward or game_penalty:
                    msg += f"\n\U0001f4b0 <b>Награда:</b> +{game_reward}\n"
                    msg += f"\U0001f494 <b>Штраф:</b> -{game_penalty}\n"

            elif action_kind and action_kind == 'auction':
                msg += f"\n\U0001f3af <b>Действие:</b> Аукцион\n"
            elif casino_phase:
                msg += f"\n\U0001f3b0 <b>Действие:</b> В казино\n"
            elif timer_started or (action_kind and action_kind != 'none'):
                msg += f"\n\U0001f3b1 <b>Действие:</b> Крутит колесо\n"
            else:
                msg += f"\n\u26aa <b>Статус:</b> Не активен\n"

            turn = info.get('turn', 0)
            streak = info.get('game_streak', 0)
            drops = info.get('drop_count', 0)
            completed = info.get('completed', 0)
            total_playtime = info.get('total_playtime', 0)
            earned = info.get('ggp_earned_total', 0)
            lost = info.get('ggp_lost_total', 0)

            if turn > 0 or streak > 0 or completed > 0:
                msg += f"\n\U0001f4ca <b>Статистика:</b>\n"
                msg += f"  \U0001f3b2 Ход: {turn}\n"
                msg += f"  \U0001f525 Серия без дропов: {streak}\n"
                msg += f"  \u2705 Пройдено: {completed} | \u274c Дропов: {drops}\n"
                if total_playtime > 0:
                    msg += f"  \U0001f553 Общее время: {format_duration(total_playtime)}\n"
                msg += f"  \U0001f4b5 Заработано: {earned} | Потеряно: {lost}\n"

            chips = info.get('platinum_chips', 0)
            chips_spent = info.get('chips_spent_total', 0)
            if chips > 0 or chips_spent > 0:
                msg += f"\n\U0001f3b4 Фишки: {chips} плат. | {chips_spent} обыч.\n"

            inventory = info.get('inventory_effects', [])
            attached = info.get('attached_effects', [])
            if inventory or attached:
                msg += f"\n\U0001f392 <b>Инвентарь:</b>\n"
                for e in inventory:
                    name = e.get('displayName', e.get('name', '?'))
                    impact = e.get('impact', '')
                    emoji = "\U0001f48e" if impact == 'positive' else ("\U0001f4a5" if impact == 'negative' else "\u26aa")
                    msg += f"  {emoji} {name}\n"
                if attached:
                    msg += f"  \U0001f6e1 Активные: {', '.join(e.get('displayName', e.get('name', '?')) for e in attached)}\n"

            p_ach = info.get('player_achievements', [])
            if p_ach:
                msg += f"\n\U0001f3c5 <b>Достижения ({len(p_ach)}):</b>\n"
                for ach in p_ach[:5]:
                    msg += f"  \U0001f31f {ach.get('title', '?')}\n"
                if len(p_ach) > 5:
                    msg += f"  ... и ещё {len(p_ach) - 5}\n"

            social = info.get('social_links', [])
            if social:
                msg += f"\n\U0001f517 <b>Ссылки:</b>\n"
                for link in social:
                    msg += f"  {link.get('platform', '')}: {link.get('url', '')}\n"

            return msg
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return None

    async def send_notification(self, message: str):
        if not self.monitoring_groups:
            return
        success = 0
        for group in self.monitoring_groups:
            try:
                await self.bot.send_message(
                    chat_id=group['chat_id'], text=message, parse_mode="HTML",
                    message_thread_id=group.get('thread_id')
                )
                success += 1
            except Exception as e:
                logger.error(f"Send error: {e}")
        logger.info(f"Sent to {success} groups")

    def start_monitoring(self):
        if self.monitoring_active or (self.monitor_loop_task and not self.monitor_loop_task.done()):
            return
        self.monitor_loop_task = asyncio.create_task(self.monitor_loop())

    async def start(self):
        @self.dp.message(Command("debug"))
        async def cmd_debug(message: types.Message):
            if not self.is_admin(message.from_user.id):
                return await message.answer("Только админ")
            await message.answer("Получаю данные...")
            if not self.session:
                self.session = aiohttp.ClientSession()
            try:
                async with self.session.get(API_URL) as response:
                    data = await response.json()
                    text = "<b>Данные API:</b>\n\n"
                    for idx, item in enumerate(data.get('data', {}).get('array', [])):
                        if item is None:
                            continue
                        player = item.get('player')
                        name = player.get('name', '???') if player else '???'
                        auction = item.get('currentAuctionResult') or {}
                        text += f"<b>{idx+1}. {name}</b>\n"
                        text += f"   Игра: {auction.get('title', '-')}\n"
                        text += f"   Статус: {auction.get('status', '-')}\n"
                        text += f"   Таймер: {auction.get('timerStartedAt', '-')}\n"
                        text += f"   Накоплено: {auction.get('timerAccumulatedSec', 0)}с\n"
                        text += f"   Рецензия: {(auction.get('playerReview') or '-')[:50]}\n"
                        text += f"   Оценка игрока: {auction.get('playerRating', '-')}\n"
                        text += f"   HLTB: {format_duration(auction.get('seconds', 0)) or '-'}\n"
                        text += f"   CasinoPhase: {player.get('casinoPhase', '-')}\n"
                        text += f"   PlayerStatus: {player.get('status', '-')}\n"
                        text += f"   Action: {item.get('requiredAction', {}).get('kind', '-') if item.get('requiredAction') else '-'}\n\n"
                    for i in range(0, len(text), 4000):
                        await message.answer(text[i:i+4000], parse_mode="HTML")
            except Exception as e:
                await message.answer(f"Ошибка: {e}")

        @self.dp.message(Command("add_group"))
        async def cmd_add_group(message: types.Message):
            if not self.is_admin(message.from_user.id):
                return await message.answer("Только админ")
            chat_id, thread_id = message.chat.id, message.message_thread_id
            for g in self.monitoring_groups:
                if g['chat_id'] == chat_id and g.get('thread_id') == thread_id:
                    return await message.answer("Уже добавлена")
            self.monitoring_groups.append({
                'chat_id': chat_id, 'chat_title': message.chat.title or 'Unknown',
                'thread_id': thread_id, 'added_at': time.time()
            })
            self.save_groups()
            await message.answer(f"Добавлена: {message.chat.title}")
            self.start_monitoring()

        @self.dp.message(Command("remove_group"))
        async def cmd_remove_group(message: types.Message):
            if not self.is_admin(message.from_user.id):
                return await message.answer("Только админ")
            args = message.text.split()[1:] if len(message.text.split()) > 1 else []
            if len(args) == 0:
                chat_id, thread_id = message.chat.id, message.message_thread_id
            elif len(args) == 1:
                try:
                    chat_id, thread_id = int(args[0]), None
                except:
                    return await message.answer("Неверный ID")
            elif len(args) == 2:
                try:
                    chat_id, thread_id = int(args[0]), int(args[1])
                except:
                    return await message.answer("Неверные ID")
            else:
                return await message.answer("Неверный формат")
            old_len = len(self.monitoring_groups)
            self.monitoring_groups = [g for g in self.monitoring_groups if not (g['chat_id'] == chat_id and g.get('thread_id') == thread_id)]
            if len(self.monitoring_groups) < old_len:
                self.save_groups()
                await message.answer(f"Удалена: {chat_id}")
            else:
                await message.answer("Группа не найдена")

        @self.dp.message(Command("clear_groups"))
        async def cmd_clear_groups(message: types.Message):
            if not self.is_admin(message.from_user.id):
                return await message.answer("Только админ")
            count = len(self.monitoring_groups)
            self.monitoring_groups = []
            self.save_groups()
            await message.answer(f"Очищено: {count} групп")

        @self.dp.message(Command("list_groups"))
        async def cmd_list_groups(message: types.Message):
            if not self.is_admin(message.from_user.id):
                return await message.answer("Только админ")
            if not self.monitoring_groups:
                return await message.answer("Пусто")
            text = "<b>Группы:</b>\n\n"
            for i, g in enumerate(self.monitoring_groups, 1):
                t = f" (ветка #{g['thread_id']})" if g.get('thread_id') else ""
                text += f"{i}. <b>{g['chat_title']}</b>{t}\n"
            await message.answer(text, parse_mode="HTML")

        @self.dp.message(Command("test_notify"))
        async def cmd_test_notify(message: types.Message):
            if not self.is_admin(message.from_user.id):
                return await message.answer("Только админ")
            await self.send_notification("<b>Тест</b>\n\nРаботает!")
            await message.answer("Отправлено")

        @self.dp.message(Command("my_id"))
        async def cmd_my_id(message: types.Message):
            if not self.is_admin(message.from_user.id):
                return await message.answer("Только админ")
            text = f"Chat ID: <code>{message.chat.id}</code>"
            if message.message_thread_id:
                text += f"\nThread ID: <code>{message.message_thread_id}</code>"
            await message.answer(text, parse_mode="HTML")

        @self.dp.message(Command("restart_monitor"))
        async def cmd_restart_monitor(message: types.Message):
            if not self.is_admin(message.from_user.id):
                return await message.answer("Только админ")
            self.monitoring_active = False
            if self.monitor_loop_task and not self.monitor_loop_task.done():
                self.monitor_loop_task.cancel()
                await asyncio.sleep(1)
            self.previous_data = {}
            self.api_cache = None
            self.monitor_loop_task = asyncio.create_task(self.monitor_loop())
            await message.answer("Мониторинг перезапущен!")

        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            admin_text = ""
            if self.is_admin(message.from_user.id):
                admin_text = "\n<b>Админ:</b>\n/add_group, /remove_group, /clear_groups, /list_groups\n/test_notify, /my_id, /debug\n/restart_monitor"
            status = 'активен' if self.monitoring_active else 'неактивен'
            await message.answer(
                "<b>Бот Nassal.pro</b>\n\n"
                "Напиши /help_event чтобы увидеть все команды"
                f"\n\n<b>Мониторинг:</b> {status}"
                + admin_text,
                reply_markup=self.get_streamer_keyboard()
            )

        @self.dp.message(Command("help_event"))
        async def cmd_help_event(message: types.Message):
            text = (
                "<b>Команды бота:</b>\n\n"
                "/event — статус ивента и обратный отсчёт\n"
                "/status — статус всех стримеров\n"
                "/rating — рейтинг\n"
                "/points — таблица очков\n"
                "/streamer [номер/имя] — инфо о стримере\n"
                "/list — список всех стримеров\n\n"
                "/timer — таймеры текущих игр\n"
                "/game [название] — инфо об игре\n"
                "/stats [имя] — статистика игрока\n"
                "/inventory [имя] — инвентарь\n"
                "/achievements — все достижения\n"
                "/social [имя] — ссылки стримера\n"
                "/nassal_top — топ с подробностями\n"
            )
            await message.answer(text, parse_mode="HTML")

        @self.dp.message(Command("event"))
        async def cmd_event(message: types.Message):
            now_msk = self._now_msk()
            delta = self._time_until_event()
            total_sec = int(delta.total_seconds())
            event_msk = self.event_end_msk.strftime("%d.%m.%Y в %H:%M:%S (МСК)")
            if total_sec <= 0:
                text = (
                    "<b>\U0001f3c6 ИВЕНТ ЗАВЕРШЁН!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"\U0001f4c5 Ивент завершился: {event_msk}\n"
                    f"\U0001f514 Мониторинг продолжается — возможны корректировки очков.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━"
                )
            else:
                countdown = self._format_countdown(delta)
                days_left = (self.event_end_msk.date() - now_msk.date()).days
                if days_left == 0:
                    status = "\U0001f525 <b>ФИНАЛЬНЫЙ ДЕНЬ!</b>"
                elif days_left == 1:
                    status = "\u26a0\ufe0f <b>Завтра — последний день!</b>"
                elif days_left <= 3:
                    status = f"\U0001f534 <b>Осталось {days_left} дня</b>"
                else:
                    status = f"\U0001f7e2 <b>Осталось {days_left} дней</b>"
                text = (
                    "<b>\U0001f3c6 СТАТУС ИВЕНТА</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{status}\n\n"
                    f"\U0001f4c5 Дата окончания: <b>{event_msk}</b>\n"
                    f"\u23f0 До окончания: <b>{countdown}</b>\n\n"
                )
                if days_left <= 1:
                    event_hour = self.event_end_msk.hour
                    event_min = self.event_end_msk.minute
                    text += (
                        f"\U0001f514 Авто-уведомления: <b>каждый час</b> (00:00–{event_hour - 1}:00)\n"
                        f"\U0001f525 Последний час ({event_hour - 1}:00): <b>финальная таблица</b>\n"
                        f"\U0001f3c6 Итоги ({event_hour}:{event_min:02d}): <b>финальная таблица + завершение</b>\n"
                    )
                elif days_left <= 7:
                    text += f"\U0001f514 Ежедневное напоминание в <b>19:00 (МСК)</b>\n"
                text += "\n━━━━━━━━━━━━━━━━━━━━"
            await message.answer(text, parse_mode="HTML")

        @self.dp.message(Command("status"))
        async def cmd_status(message: types.Message):
            try:
                await message.answer("Получаю статусы...")
                data = await self.get_participants_data()
                if not data:
                    return await message.answer("Не удалось получить данные с API")
                leaderboard = self._get_leaderboard(data)
                text = "<b>СТАТУС ВСЕХ СТРИМЕРОВ</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                for name, info in leaderboard:
                    pos = self._get_real_position(data, name)
                    pts = info['points']
                    pts_str = f"+{pts}" if pts > 0 else str(pts)
                    icon = self._format_streaming_status_short(info.get('is_streaming', False), info.get('streaming_platforms', []))

                    game = info.get('game_title', '')
                    ts = info.get('timer_started', '')
                    hltb = info.get('hltb_seconds', 0)
                    action = info.get('action_kind', '')

                    text += f"<b>{name}</b> {icon}  \U0001f3c6 {pos} | \u2b50 {pts_str}\n"

                    if game:
                        game_type = info.get('game_type', '')
                        game_icon = "\U0001f3ae" if game_type == 'game' else "\U0001f4fa"
                        timer_label = "Играет" if game_type == 'game' else "Смотрит"
                        text += f"  {game_icon} {game}\n"
                        if hltb > 0:
                            text += f"  \U0001f552 HLTB: {format_duration(hltb)}\n"
                        if ts:
                            el = info.get('timer_accumulated', 0) + elapsed_since(ts)
                            text += f"  \u23f1 {timer_label}: {format_duration(el)}\n"
                        elif info.get('timer_accumulated', 0) > 0:
                            text += f"  \u23f1 На паузе: {format_duration(info.get('timer_accumulated', 0))}\n"
                        rw, pn = info.get('game_reward', 0), info.get('game_penalty', 0)
                        if rw or pn:
                            text += f"  \U0001f4b0 +{rw} / -{pn}\n"
                        text += "\n"
                    elif action and action == 'auction':
                        text += f"  \U0001f3af Аукцион\n\n"
                    elif info.get('casino_phase'):
                        text += f"  \U0001f3b0 В казино\n\n"
                    elif action and action != 'none':
                        text += f"  \U0001f3b1 Крутит колесо\n\n"
                    else:
                        text += f"  \u26aa Ожидание\n\n"

                text += "━━━━━━━━━━━━━━━━━━━━\n\U0001f7e2 — онлайн | \U0001f534 — оффлайн"
                for i in range(0, len(text), 4000):
                    await message.answer(text[i:i+4000], parse_mode="HTML")
            except Exception as e:
                logger.error(f"/status error: {e}", exc_info=True)
                try:
                    await message.answer("Ошибка при получении статуса")
                except Exception:
                    pass

        @self.dp.message(Command("list"))
        async def cmd_list(message: types.Message):
            text = "<b>Участники:</b>\n\n"
            for num, name in STREAMERS.items():
                text += f"{num}. <b>{name}</b>\n"
            await message.answer(text, parse_mode="HTML")

        @self.dp.message(Command("rating"))
        async def cmd_rating(message: types.Message):
            await message.answer("Получаю рейтинг...")
            data = await self.get_participants_data()
            if not data:
                return await message.answer("Не удалось")
            leaderboard = self._get_leaderboard(data)
            medals = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}
            text = "<b>РЕЙТИНГ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for i, (name, info) in enumerate(leaderboard, 1):
                pts = info['points']
                pts_str = f"+{pts}" if pts > 0 else str(pts)
                medal = medals.get(i, f"{i}.")
                icon = "\U0001f7e2" if info.get('is_streaming', False) else "\U0001f534"
                base = f"{medal} {name} {pts_str}"
                vis = self._visible_len(base)
                spaces = " " * max(28 - vis, 1)
                text += f"{base}{spaces}{icon}\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\U0001f7e2 — онлайн  |  \U0001f534 — оффлайн"
            await message.answer(text, parse_mode="HTML")

        @self.dp.message(Command("points"))
        async def cmd_points(message: types.Message):
            await message.answer("Получаю...")
            data = await self.get_participants_data()
            if not data:
                return await message.answer("Не удалось")
            text = "<b>ОЧКИ</b>\n━━━━━━━━━━━━\n\n"
            for i, (name, info) in enumerate(self._get_leaderboard(data), 1):
                pts = info['points']
                pts_str = f"+{pts}" if pts > 0 else str(pts)
                text += f"{i}. <b>{name}</b> — {pts_str}\n"
            await message.answer(text, parse_mode="HTML")

        @self.dp.message(Command("streamer"))
        async def cmd_streamer(message: types.Message):
            if len(message.text.split()) < 2:
                return await message.answer("Пример: /streamer 1")
            query = message.text.split(maxsplit=1)[1].strip()
            name = self._resolve_streamer(query)
            if not name:
                return await message.answer(f"'{query}' не найден")
            await message.answer("Загрузка...")
            info = await self.get_detailed_streamer_info(name)
            await message.answer(info or "Не удалось", parse_mode="HTML", disable_web_page_preview=True)

        @self.dp.message(Command("monitor"))
        async def cmd_monitor(message: types.Message):
            args = message.text.split()[1:] if len(message.text.split()) > 1 else []
            if len(args) == 0:
                chat_id, thread_id = message.chat.id, message.message_thread_id
                title = message.chat.title or 'Unknown'
            elif len(args) == 1 and self.is_admin(message.from_user.id):
                try:
                    chat_id, thread_id, title = int(args[0]), None, f"Group {args[0]}"
                except:
                    return await message.answer("Неверный ID")
            elif len(args) == 2 and self.is_admin(message.from_user.id):
                try:
                    chat_id, thread_id, title = int(args[0]), int(args[1]), f"Group {args[0]}"
                except:
                    return await message.answer("Неверные ID")
            else:
                return await message.answer("Только админ может указывать ID")
            for g in self.monitoring_groups:
                if g['chat_id'] == chat_id and g.get('thread_id') == thread_id:
                    return await message.answer("Уже активен")
            self.monitoring_groups.append({'chat_id': chat_id, 'chat_title': title, 'thread_id': thread_id, 'added_at': time.time()})
            self.save_groups()
            await message.answer("<b>Мониторинг включен!</b>", parse_mode="HTML")
            self.start_monitoring()

        @self.dp.message(Command("stop"))
        async def cmd_stop(message: types.Message):
            if not self.is_admin(message.from_user.id):
                return await message.answer("Только админ")
            self.monitoring_active = False
            if self.monitor_loop_task and not self.monitor_loop_task.done():
                self.monitor_loop_task.cancel()
            await message.answer("Остановлен")
            if self.session:
                await self.session.close()
            await self.bot.close()

        @self.dp.message(Command("timer"))
        async def cmd_timer(message: types.Message):
            await message.answer("Получаю таймеры...")
            data = await self.get_participants_data()
            if not data:
                return await message.answer("Не удалось")
            text = "<b>\U0001f552 ТАЙМЕРЫ ТЕКУЩИХ ИГР</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            active = [(n, i) for n, i in data.items() if i.get('timer_started', '')]
            if not active:
                text += "Никто сейчас не играет\n"
            else:
                for name, info in active:
                    acc = info.get('timer_accumulated', 0)
                    el = acc + elapsed_since(info.get('timer_started', ''))
                    hltb = info.get('hltb_seconds', 0)
                    game = info.get('game_title', '?')
                    game_type = info.get('game_type', '')
                    game_icon = "\U0001f3ae" if game_type == 'game' else "\U0001f4fa"
                    timer_label = "Играет" if game_type == 'game' else "Смотрит"
                    text += f"<b>{name}</b>\n  {game_icon} {game}\n  \u23f1 {timer_label}: <b>{format_duration(el)}</b>\n"
                    if hltb > 0:
                        text += f"  \U0001f552 HLTB: {format_duration(hltb)}\n"
                    rw, pn = info.get('game_reward', 0), info.get('game_penalty', 0)
                    if rw or pn:
                        text += f"  \U0001f4b0 +{rw} / -{pn}\n"
                    text += "\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\U0001f7e2 — онлайн | \U0001f534 — оффлайн"
            await message.answer(text, parse_mode="HTML")

        @self.dp.message(Command("game"))
        async def cmd_game(message: types.Message):
            if len(message.text.split()) < 2:
                return await message.answer("Пример: /game Total Overdose\nИли: /game Lasqa (покажет текущую игру)")
            query = message.text.split(maxsplit=1)[1].strip()
            query_lower = query.lower()
            data = await self.get_participants_data()

            name = self._resolve_streamer(query)
            if name and name in data:
                info = data[name]
                gt = info.get('game_title', '')
                if gt:
                    found = (name, info)
                else:
                    return await message.answer(f"<b>{name}</b> сейчас не в игре", parse_mode="HTML")
            else:
                found = None
                for n, info in data.items():
                    gt = info.get('game_title', '')
                    if gt and query_lower in gt.lower():
                        found = (n, info)
                        break

            if not found:
                await message.answer(f"Ищу '<b>{query}</b>' на HLTB...", parse_mode="HTML")
                hltb_result = await self.search_hltb(query)

                if hltb_result:
                    name_hltb = hltb_result.get("name", query)
                    game_id = hltb_result.get("id", "")
                    main_time = hltb_result.get("main_time", 0)
                    extra_time = hltb_result.get("extra_time", 0)
                    c100 = hltb_result.get("hundred_time", 0)
                    developer = hltb_result.get("developer", "")
                    publisher = hltb_result.get("publisher", "")
                    genres = hltb_result.get("genres", "")
                    platforms = hltb_result.get("platforms", "")
                    release = hltb_result.get("release_year", "")
                    release_na = hltb_result.get("release_na", "")
                    release_eu = hltb_result.get("release_eu", "")
                    release_jp = hltb_result.get("release_jp", "")

                    text = f"\U0001f3ae <b>{name_hltb}</b>\n"
                    if release:
                        text += f"\U0001f4c5 Год: {release}\n"
                    if release_na and release_na != "0000-00-00":
                        text += f"  \U0001f1fa\U0001f1f8 NA: {release_na}\n"
                    if release_eu and release_eu != "0000-00-00":
                        text += f"  \U0001f1ea\U0001f1fa EU: {release_eu}\n"
                    if release_jp and release_jp != "0000-00-00":
                        text += f"  \U0001f1ef\U0001f1f5 JP: {release_jp}\n"
                    if developer:
                        text += f"\U0001f3d7 Разработчик: {developer}\n"
                    if publisher:
                        text += f"\U0001f4e2 Издатель: {publisher}\n"
                    if genres:
                        text += f"\U0001f3a8 Жанры: {genres}\n"
                    if platforms:
                        text += f"\u2328 Платформы: {platforms}\n"
                    text += "\n"

                    if game_id:
                        text += f"\U0001f552 <a href='https://howlongtobeat.com/game/{game_id}'>страница на HLTB</a>\n\n"

                    if main_time > 0:
                        text += f"\u23f1 Основная история: {format_duration(main_time)}\n"
                    if extra_time > 0:
                        text += f"\u23f1 С дополнениями: {format_duration(extra_time)}\n"
                    if c100 > 0:
                        text += f"\u23f1 100% прохождение: {format_duration(c100)}\n"

                    text += f"\n<i>Данные с HLTB. Инфо от стримеров пока нет.</i>"
                    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
                else:
                    hltb_q = query.replace(' ', '+')
                    text = (
                        f"\u2753 Игра '<b>{query}</b>' не найдена\n\n"
                        f"<a href='https://howlongtobeat.com/?q={hltb_q}'>Поискать на HLTB вручную</a>"
                    )
                    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
                return

            name, info = found
            gt = info.get('game_title', '')
            emoji = "\U0001f3ae" if info.get('game_type') == 'game' else "\U0001f4fa"
            text = f"{emoji} <b>{gt}</b>\nСтример: <b>{name}</b>\n\n"

            hltb_data = None
            try:
                hltb_data = await self.search_hltb(gt)
            except Exception:
                pass

            yr = info.get('release_year')
            if not yr and hltb_data:
                yr = hltb_data.get("release_year", "")
            if yr: text += f"\U0001f4c5 Год: {yr}\n"
            if hltb_data:
                na = hltb_data.get("release_na", "")
                eu = hltb_data.get("release_eu", "")
                jp = hltb_data.get("release_jp", "")
                if na and na != "0000-00-00": text += f"  \U0001f1fa\U0001f1f8 NA: {na}\n"
                if eu and eu != "0000-00-00": text += f"  \U0001f1ea\U0001f1fa EU: {eu}\n"
                if jp and jp != "0000-00-00": text += f"  \U0001f1ef\U0001f1f5 JP: {jp}\n"

            if hltb_data:
                dev = hltb_data.get("developer", "")
                pub = hltb_data.get("publisher", "")
                genres = hltb_data.get("genres", "")
                platforms = hltb_data.get("platforms", "")
                if dev: text += f"\U0001f3d7 Разработчик: {dev}\n"
                if pub: text += f"\U0001f4e2 Издатель: {pub}\n"
                if genres: text += f"\U0001f3a8 Жанры: {genres}\n"
                if platforms: text += f"\u2328 Платформы: {platforms}\n"

            rs = info.get('review_score')
            if rs is not None:
                se = "\U0001f44d" if rs >= 75 else ("\U0001f914" if rs >= 50 else "\U0001f44e")
                text += f"{se} Оценка: {rs}/100\n"

            hltb = info.get('hltb_seconds', 0)
            hid = info.get('hltb_game_id')
            if hltb > 0:
                text += f"\U0001f552 HLTB: {format_duration(hltb)}\n"
                if hid: text += f"    <a href='https://howlongtobeat.com/game/{hid}'>открыть на HLTB</a>\n"
            elif hltb_data and hltb_data.get("main_time", 0) > 0:
                text += f"\U0001f552 HLTB: <a href='https://howlongtobeat.com/game/{hltb_data.get('id', '')}'>{format_duration(hltb_data['main_time'])}</a>\n"

            sid = info.get('steam_app_id')
            if sid: text += f"\u2699\ufe0f Steam: <a href='https://store.steampowered.com/app/{sid}'>магазин</a>\n"
            rw, pn = info.get('game_reward', 0), info.get('game_penalty', 0)
            if rw or pn: text += f"\n\U0001f4b0 Награда: +{rw}\n\U0001f494 Штраф: -{pn}\n"
            ft, fp = info.get('fastest_time'), info.get('fastest_player')
            if ft and fp: text += f"\n\u26a1 Рекорд: {format_duration(ft)} — {fp}\n"
            ts = info.get('timer_started', '')
            if ts:
                el = info.get('timer_accumulated', 0) + elapsed_since(ts)
                text += f"\n\u23f1 Играет: <b>{format_duration(el)}</b>\n"
            await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

        @self.dp.message(Command("stats"))
        async def cmd_stats(message: types.Message):
            if len(message.text.split()) < 2:
                return await message.answer("Пример: /stats Lasqa")
            query = message.text.split(maxsplit=1)[1].strip()
            name = self._resolve_streamer(query)
            if not name:
                return await message.answer(f"'{query}' не найден")
            data = await self.get_participants_data()
            if name not in data:
                return await message.answer("Данные не найдены")
            info = data[name]
            pos = self._get_real_position(data, name)
            pts = info['points']
            pts_str = f"+{pts}" if pts > 0 else str(pts)
            text = f"<b>\U0001f4ca СТАТИСТИКА: {name}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            text += f"\U0001f3c6 Место: {pos} из {len(data)}\n\u2b50 Очки: {pts_str}\n\n"
            text += "<b>\U0001f3ae Игры:</b>\n"
            text += f"  Ход: {info.get('turn', 0)}\n"
            text += f"  \u2705 Пройдено: {info.get('completed', 0)} | \u274c Дропов: {info.get('drop_count', 0)} | \U0001f504 Рероллов: {info.get('rerolled', 0)}\n"
            text += f"  \U0001f525 Серия без дропов: {info.get('game_streak', 0)}\n"
            tp = info.get('total_playtime', 0)
            if tp > 0: text += f"  \U0001f553 Общее время в играх: {format_duration(tp)}\n"

            game = info.get('game_title', '')
            if game:
                text += f"\n  Сейчас играет: <b>{game}</b>\n"
            text += f"\n<b>\u2b50 Очки:</b>\n  Заработано: +{info.get('ggp_earned_total', 0)} | Потеряно: -{info.get('ggp_lost_total', 0)}\n  Чистый: {info.get('ggp_net_games', 0)}\n"
            text += f"\n<b>\U0001f3b4 Фишки:</b>\n  Платиновые: {info.get('platinum_chips', 0)} | Потрачено: {info.get('chips_spent_total', 0)}\n  Серия слотов: {info.get('slot_streak', 0)} | Гнусы: {info.get('gnus_available', 0)}\n"
            cp = info.get('casino_phase')
            if cp: text += f"  Казино: {cp}\n"
            text += f"\n<b>\U0001f3b0 Роллы:</b>\n  Всего: {info.get('roll_total', 0)} (обыч: {info.get('roll_regular', 0)}, плат: {info.get('roll_platinum', 0)})\n"
            text += f"  \U0001f49a +{info.get('roll_positive', 0)} | \U0001f494 -{info.get('roll_negative', 0)} | \u26aa {info.get('roll_neutral', 0)}\n"
            text += f"  Среднее за ход: {info.get('avg_rolls_turn', 0)}\n"

            p_ach = info.get('player_achievements', [])
            if p_ach:
                text += f"\n<b>\U0001f3c5 Достижения ({len(p_ach)}):</b>\n"
                for ach in p_ach[:8]:
                    text += f"  \U0001f31f {ach.get('title', '?')}\n"
                if len(p_ach) > 8:
                    text += f"  ... и ещё {len(p_ach) - 8}\n"

            text += f"\n\U0001f517 <a href='https://nassal.pro/'>Полная статистика на сайте</a>"
            await message.answer(text, parse_mode="HTML")

        @self.dp.message(Command("inventory"))
        async def cmd_inventory(message: types.Message):
            if len(message.text.split()) < 2:
                return await message.answer("Пример: /inventory Lasqa")
            query = message.text.split(maxsplit=1)[1].strip()
            name = self._resolve_streamer(query)
            if not name:
                return await message.answer(f"'{query}' не найден")
            data = await self.get_participants_data()
            if name not in data:
                return await message.answer("Данные не найдены")
            info = data[name]
            inv = info.get('inventory_effects', [])
            att = info.get('attached_effects', [])
            text = f"<b>\U0001f392 ИНВЕНТАРЬ: {name}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            if inv:
                text += "<b>Предметы:</b>\n"
                for e in inv:
                    en = e.get('displayName', e.get('name', '?'))
                    desc = e.get('description', '')
                    if isinstance(desc, list): desc = ' '.join(desc)
                    imp = e.get('impact', '')
                    em = "\U0001f48e" if imp == 'positive' else ("\U0001f4a5" if imp == 'negative' else "\u26aa")
                    text += f"{em} <b>{en}</b>\n"
                    if desc: text += f"  <i>{desc}</i>\n"
                    text += "\n"
            else:
                text += "\U0001f4e6 Пусто\n\n"
            if att:
                text += "<b>\U0001f6e1 Активные:</b>\n"
                for e in att:
                    text += f"  \U0001f48e <b>{e.get('displayName', e.get('name', '?'))}</b>\n"
            else:
                text += "\U0001f6e1 Нет активных эффектов\n"
            await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

        @self.dp.message(Command("achievements"))
        async def cmd_achievements(message: types.Message):
            await message.answer("Получаю достижения...")
            ach_data = await self.get_achievements_data()
            if not ach_data:
                return await message.answer("Не удалось")
            achievements = ach_data.get('achievements', [])
            total = ach_data.get('totalCount', 0)
            revealed = ach_data.get('revealedCount', 0)
            text = f"<b>\U0001f3c5 ДОСТИЖЕНИЯ ({revealed}/{total})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for ach in achievements:
                title = ach.get('title', '?')
                desc = ach.get('description', '')
                all_players = [p.get('name', '?') for p in ach.get('achievedPlayers', [])]
                text += f"\U0001f31f <b>{title}</b>\n  <i>{desc}</i>\n"
                if all_players:
                    text += f"  \U0001f464 {', '.join(f'<b>{p}</b>' for p in all_players)}\n"
                text += "\n"
                if len(text) > 3500:
                    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
                    text = ""
            if text.strip():
                await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

        @self.dp.message(Command("social"))
        async def cmd_social(message: types.Message):
            if len(message.text.split()) < 2:
                return await message.answer("Пример: /social Lasqa")
            query = message.text.split(maxsplit=1)[1].strip()
            name = self._resolve_streamer(query)
            if not name:
                return await message.answer(f"'{query}' не найден")
            data = await self.get_participants_data()
            if name not in data:
                return await message.answer("Данные не найдены")
            info = data[name]
            social = info.get('social_links', [])
            streaming = info.get('streaming_platforms', [])
            text = f"<b>\U0001f517 ССЫЛКИ: {name}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            if streaming:
                text += "<b>\U0001f534 Онлайн сейчас:</b>\n"
                for s in streaming:
                    text += f"  \U0001f7e2 {s.get('platform', '')}: {s.get('username', '')}\n"
                text += "\n"
            if social:
                text += "<b>Соцсети:</b>\n"
                emojis = {'twitch': '\U0001f7e3', 'youtube': '\U0001f534', 'kick': '\U0001f7e2', 'telegram': '\u2708\ufe0f', 'vk': '\U0001f535', 'vklive': '\U0001f535'}
                for link in social:
                    em = emojis.get(link.get('platform', ''), '\U0001f517')
                    text += f"{em} {link.get('platform', '')}: <a href='{link.get('url', '')}'>{link.get('url', '')}</a>\n"
            else:
                text += "Нет ссылок\n"
            await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

        @self.dp.message(Command("top"))
        @self.dp.message(Command("nassal_top"))
        async def cmd_nassal_top(message: types.Message):
            await message.answer("Получаю...")
            data = await self.get_participants_data()
            if not data:
                return await message.answer("Не удалось")
            medals = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}
            text = "<b>\U0001f3c6 ТОП NASSAL</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for i, (name, info) in enumerate(self._get_leaderboard(data), 1):
                pts = info['points']
                pts_str = f"+{pts}" if pts > 0 else str(pts)
                medal = medals.get(i, f"{i}.")
                icon = "\U0001f7e2" if info.get('is_streaming', False) else "\U0001f534"
                text += f"{medal} <b>{name}</b> {icon}\n  \u2b50 {pts_str} | \u2705 {info.get('completed', 0)} игр | \u274c {info.get('drop_count', 0)} дропов\n  \U0001f525 Серия: {info.get('game_streak', 0)}"
                tp = info.get('total_playtime', 0)
                if tp > 0: text += f" | \U0001f553 {format_duration_short(tp)}"
                text += "\n\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            for i in range(0, len(text), 4000):
                await message.answer(text[i:i+4000], parse_mode="HTML")

        @self.dp.message()
        async def handle_keyboard(message: types.Message):
            text = message.text.strip()
            for num, name in STREAMERS.items():
                if text == f"{num}. {name}" or text == name:
                    await message.answer("Загрузка...")
                    info = await self.get_detailed_streamer_info(name)
                    await message.answer(info or "Не удалось", parse_mode="HTML", disable_web_page_preview=True)
                    return

        logger.info("Bot started!")
        if self.monitoring_groups:
            self.start_monitoring()
        await self.dp.start_polling(self.bot)

    async def monitor_loop(self):
        if self.monitoring_active:
            return
        self.monitoring_active = True
        initial_data = await self.get_participants_data()
        if not initial_data:
            self.monitoring_active = False
            return
        self.previous_data = initial_data

        while self.monitoring_active:
            try:
                self.api_cache = None
                current_data = await self.get_participants_data()
                if current_data and self.previous_data:
                    changes = self.compare_data(self.previous_data, current_data)
                    if changes:
                        await self.send_notification(self._format_notification(changes))
                if current_data:
                    self.previous_data = current_data
                await self._check_event_notifications()
            except Exception as e:
                logger.error(f"Error: {e}")
            await asyncio.sleep(10)

    def _format_notification(self, changes: list) -> str:
        return "<b>\U0001f514 ИЗМЕНЕНИЯ НА NASSAL.PRO</b>\n━━━━━━━━━━━━━━━━━━━━\n\n" + "\n\n".join(changes) + "\n\n━━━━━━━━━━━━━━━━━━━━"

    async def _check_event_notifications(self):
        now_msk = self._now_msk()
        event_end = self._event_end_utc()
        delta = event_end - datetime.now(timezone.utc)
        total_sec = int(delta.total_seconds())

        if total_sec <= 0:
            key = self._get_notification_key("event_ended")
            if key not in self.event_sent_notifications:
                self.event_sent_notifications.add(key)
                data = await self.get_participants_data()
                if data:
                    msg = self._build_leaderboard_table(data)
                    header = "<b>\U0001f3c6 ИВЕНТ ЗАВЕРШЁН!</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                    await self.send_notification(header + msg + "\n\n━━━━━━━━━━━━━━━━━━━━")
                    logger.info("Event ended notification sent")
            return

        now_hour = now_msk.hour
        now_date = now_msk.date()
        event_date = self.event_end_msk.date()
        event_hour = self.event_end_msk.hour

        if now_date == event_date:
            last_hour = event_hour - 1
            if now_hour == last_hour and last_hour >= 0:
                key = self._get_notification_key("last_hour", last_hour)
                if key not in self.event_sent_notifications:
                    self.event_sent_notifications.add(key)
                    data = await self.get_participants_data()
                    if data:
                        msg = self._build_leaderboard_table(data)
                        header = (
                            "<b>\u23f0 \U0001f525 ПОСЛЕДНИЙ ЧАС!</b>\n"
                            "━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"\u23f0 До окончания ивента: <b>{self._format_countdown(delta)}</b>\n\n"
                        )
                        await self.send_notification(header + msg + "\n\n━━━━━━━━━━━━━━━━━━━━")
                        logger.info("Last hour notification sent")
            elif 0 <= now_hour < last_hour:
                key = self._get_notification_key("hourly", now_hour)
                if key not in self.event_sent_notifications:
                    self.event_sent_notifications.add(key)
                    data = await self.get_participants_data()
                    if data:
                        msg = self._build_leaderboard_table(data)
                        header = (
                            "<b>\U0001f552 ИВЕНТ — ФИНАЛЬНЫЙ ДЕНЬ</b>\n"
                            "━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"\u23f0 До окончания: <b>{self._format_countdown(delta)}</b>\n\n"
                        )
                        await self.send_notification(header + msg + "\n\n━━━━━━━━━━━━━━━━━━━━")
                        logger.info(f"Hourly notification sent ({now_hour}:00)")
        else:
            event_day = event_date.day
            event_month = event_date.month
            days_left = (event_date - now_date).days
            event_time_str = self.event_end_msk.strftime("%H:%M")
            if now_hour == event_hour:
                key = self._get_notification_key("daily_countdown", event_hour)
                if key not in self.event_sent_notifications:
                    self.event_sent_notifications.add(key)
                    countdown_str = self._format_countdown(delta)
                    month_names = {1: "января", 2: "февраля", 3: "марта", 4: "апреля",
                                   5: "мая", 6: "июня", 7: "июля", 8: "августа",
                                   9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"}
                    month_name = month_names.get(event_month, str(event_month))
                    if days_left == 1:
                        text = (
                            "<b>\U0001f514 НАПОМИНАНИЕ</b>\n"
                            "━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"\u26a0\ufe0f До окончания ивента остался <b>один день</b>!\n"
                            f"\u23f0 Завтра в {event_time_str} (МСК) ивент завершается.\n"
                            f"\U0001f4a1 Финальный день — последний шанс набрать очки!\n\n"
                            "━━━━━━━━━━━━━━━━━━━━"
                        )
                    else:
                        word_days = self._number_to_word(days_left) if days_left <= 20 else str(days_left)
                        text = (
                            "<b>\U0001f514 НАПОМИНАНИЕ</b>\n"
                            "━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"\u23f0 До окончания ивента: <b>{countdown_str}</b>\n"
                            f"\U0001f4c5 Ивент завершается <b>{event_day} {month_name} в {event_time_str} (МСК)</b>\n\n"
                            "━━━━━━━━━━━━━━━━━━━━"
                        )
                    await self.send_notification(text)
                    logger.info(f"Daily countdown sent ({days_left} days left)")

    def _build_leaderboard_table(self, data: Dict) -> str:
        leaderboard = self._get_leaderboard(data)
        medals = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}
        lines = []
        for i, (name, info) in enumerate(leaderboard, 1):
            pts = info['points']
            pts_str = f"+{pts}" if pts > 0 else str(pts)
            medal = medals.get(i, f"{i}.")
            icon = "\U0001f7e2" if info.get('is_streaming', False) else "\U0001f534"
            completed = info.get('completed', 0)
            drops = info.get('drop_count', 0)
            lines.append(f"{medal} <b>{name}</b> {icon}  \u2b50 {pts_str} | \u2705 {completed} | \u274c {drops}")
        return "\n".join(lines)

    def compare_data(self, old_data: Dict, new_data: Dict) -> list:
        changes = []
        old_pos = {n: i for i, (n, _) in enumerate(self._get_leaderboard(old_data), 1)}
        new_pos = {n: i for i, (n, _) in enumerate(self._get_leaderboard(new_data), 1)}

        pos_changes = []
        for name in new_data:
            if name in old_pos and name in new_pos and old_pos[name] != new_pos[name]:
                diff = old_pos[name] - new_pos[name]
                if diff > 0:
                    pos_changes.append(f"\U0001f680 <b>{name}</b>: {old_pos[name]} \u2192 {new_pos[name]} (поднялся на {self._number_to_word(diff)} {self._get_position_word(diff)})")
                else:
                    pos_changes.append(f"\U0001f4c9 <b>{name}</b>: {old_pos[name]} \u2192 {new_pos[name]} (упал на {self._number_to_word(abs(diff))} {self._get_position_word(abs(diff))})")
        if pos_changes:
            changes.append("\U0001f4ca <b>ПОЗИЦИИ:</b>\n\n" + "\n\n".join(pos_changes))

        pts_changes = []
        for name, nd in new_data.items():
            if name in old_data:
                op, np_ = old_data[name].get('points', 0), nd.get('points', 0)
                if op != np_:
                    d = np_ - op
                    em = "\U0001f49a" if d > 0 else "\U0001f494"
                    pts_changes.append(f"{em} <b>{name}</b>: {op} \u2192 {np_} ({'+' if d>0 else ''}{d})")
        if pts_changes:
            changes.append("\U0001f4b0 <b>ОЧКИ:</b>\n\n" + "\n\n".join(pts_changes))

        game_changes = []
        for name, nd in new_data.items():
            if name in old_data:
                od = old_data[name]
                og, ng = od.get('game_title', ''), nd.get('game_title', '')
                if og != ng:
                    old_drops = od.get('drop_count', 0)
                    new_drops = nd.get('drop_count', 0)
                    op, np_ = od.get('points', 0), nd.get('points', 0)
                    pts_delta = np_ - op
                    pts_str = f" ({'+' if pts_delta > 0 else ''}{pts_delta} очков)" if pts_delta != 0 else ""
                    ot = od.get('game_type', '')
                    nt = nd.get('game_type', '')
                    is_video = ot not in ('game', '') or nt not in ('game', '')
                    if is_video:
                        if not og and ng:
                            game_changes.append(f"\U0001f4fa <b>{name}</b> начал смотреть: <b>{ng}</b>")
                        elif og and not ng:
                            old_pts = od.get('points', 0)
                            new_pts = nd.get('points', 0)
                            if new_pts > old_pts:
                                game_changes.append(f"\u2705 <b>{name}</b> посмотрел: <b>{og}</b>{pts_str}")
                            else:
                                game_changes.append(f"\U0001f4a9 <b>{name}</b> дропнул просмотр: <b>{og}</b>{pts_str}")
        if game_changes:
            changes.append("\U0001f4fa <b>ВИДЕО:</b>\n\n" + "\n\n".join(game_changes))

        review_changes = []
        for name, nd in new_data.items():
            if name not in old_data:
                continue
            od = old_data[name]
            old_review = od.get('player_review')
            new_review = nd.get('player_review')
            if new_review and new_review != old_review:
                game = nd.get('game_title', '') or od.get('game_title', '')
                rating = nd.get('player_rating')
                rating_str = f"{rating}/10" if rating is not None else ""
                emoji = "\u2705" if rating and rating >= 5 else "\u274c"
                line = f"{emoji} <b>{name}</b> оставил рецензию на <b>{game}</b> [{rating_str}]:\n\n<i>{new_review}</i>"
                review_changes.append(line)
        if review_changes:
            changes.append("\U0001f4dd <b>РЕЦЕНЗИИ:</b>\n\n" + "\n\n".join(review_changes))

        action_changes = []
        game_start_changes = []
        casino_changes = []
        for name, nd in new_data.items():
            if name not in old_data:
                continue
            od = old_data[name]
            old_action = od.get('action_kind', '')
            new_action = nd.get('action_kind', '')
            old_auction_status = od.get('auction_status', '')
            new_auction_status = nd.get('auction_status', '')
            old_game = od.get('game_title', '')
            new_game = nd.get('game_title', '')
            old_casino = od.get('casino_phase')
            new_casino = nd.get('casino_phase')
            in_casino = bool(new_casino)

            if new_auction_status and new_auction_status != old_auction_status:
                if new_auction_status == 'start':
                    action_changes.append(f"\U0001f3af <b>{name}</b>: аукцион начался")
                elif new_auction_status == 'timer':
                    action_changes.append(f"\u23f0 <b>{name}</b>: торги идут")
                elif new_auction_status == 'finish':
                    action_changes.append(f"\U0001f3c6 <b>{name}</b>: аукцион завершён")

            if new_casino != old_casino:
                if new_casino and not old_casino:
                    casino_changes.append(f"\U0001f3b0 <b>{name}</b> зашёл в казино")

            if not in_casino and old_action != new_action:
                if new_action == 'auction' and old_action != 'auction':
                    action_changes.append(f"\U0001f3af <b>{name}</b> проводит аукцион")
                elif not new_action and old_action == 'auction':
                    action_changes.append(f"\U0001f3af <b>{name}</b> завершил аукцион")

            old_timer = od.get('timer_started', '')
            new_timer = nd.get('timer_started', '')
            if not old_timer and new_timer and new_game:
                game_start_changes.append(f"\U0001f3ae <b>{name}</b> начал играть: <b>{new_game}</b>")

            if old_game and not new_game:
                old_pts = od.get('points', 0)
                new_pts = nd.get('points', 0)
                if new_pts > old_pts:
                    action_changes.append(f"\u2705 <b>{name}</b> прошёл: <b>{old_game}</b>")
                else:
                    action_changes.append(f"\U0001f4a9 <b>{name}</b> дропнул: <b>{old_game}</b>")



        if game_start_changes:
            changes.append("\U0001f3ae <b>ИГРЫ:</b>\n\n" + "\n\n".join(game_start_changes))

        if casino_changes:
            changes.append("\U0001f3b0 <b>КАЗИНО:</b>\n\n" + "\n\n".join(casino_changes))

        if action_changes:
            changes.append("\U0001f3af <b>АУКЦИОН / РУЛЕТКА:</b>\n\n" + "\n\n".join(action_changes))

        return changes


async def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found!")
        return
    monitor = NassalMonitor(BOT_TOKEN)
    await monitor.start()


if __name__ == "__main__":
    asyncio.run(main())

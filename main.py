import asyncio
import time
import os
import json
import aiohttp
from typing import Dict, Optional, List
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

STREAMERS = {
    1: "Dunduk",
    2: "F1ashko",
    3: "GladValakas",
    4: "KarmikKoala",
    5: "Lasqa",
    6: "Maddyson",
    7: "Melharucos",
    8: "Nenormova",
    9: "Praden",
    10: "ViktorZu",
    11: "C_a_k_e",
    12: "Arrowwoods"
}

STREAMERS_BY_NAME = {name.lower().strip(): num for num, name in STREAMERS.items()}
VALID_NAMES = {name.lower().strip() for name in STREAMERS.values()}

API_URL = "https://api-game.nassal.pro/api/public/player/list"

GROUPS_FILE = "monitoring_groups.json"

ADMINS = [417850992]

class NassalMonitor:
    def __init__(self, bot_token: str):
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        self.previous_data: Dict = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.monitoring_groups: List[Dict] = self.load_groups()
        self.monitoring_active: bool = False
        
        # Кэш игроков: playerId -> данные
        self.player_cache: Dict[str, Dict] = {}
    
    def load_groups(self) -> List[Dict]:
        try:
            if os.path.exists(GROUPS_FILE):
                with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
                    groups = json.load(f)
                logger.info(f"📂 Загружено групп из файла: {len(groups)}")
                return groups
        except Exception as e:
            logger.error(f"Ошибка загрузки групп: {e}")
        return []
    
    def save_groups(self):
        try:
            with open(GROUPS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.monitoring_groups, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 Сохранено групп: {len(self.monitoring_groups)}")
        except Exception as e:
            logger.error(f"Ошибка сохранения групп: {e}")
    
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
    
    async def get_participants_data(self) -> Dict:
        """Получает данные всех участников через API с кэшированием"""
        try:
            logger.info("🌐 Запрашиваю данные с API...")
            
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(API_URL) as response:
                if response.status != 200:
                    logger.error(f"❌ Ошибка API: {response.status}")
                    return {}
                
                data = await response.json()
                participants = {}
                raw_count = data.get('data', {}).get('count', 0)
                raw_array = data.get('data', {}).get('array', [])
                
                logger.info(f"📊 API вернул {raw_count} участников (массив: {len(raw_array)})")
                
                for idx, item in enumerate(raw_array):
                    try:
                        if item is None:
                            logger.warning(f"⚠️ [{idx}] item равен None, пропускаем")
                            continue
                        
                        player = item.get('player')
                        
                        # Если player = null, пытаемся найти в кэше
                        if player is None:
                            auction_result = item.get('currentAuctionResult') or {}
                            player_id = auction_result.get('playerId', '')
                            
                            if player_id and player_id in self.player_cache:
                                cached = self.player_cache[player_id]
                                name = cached['name']
                                points = cached['points']
                                logger.info(f" [{idx}] {name} - используем кэш (player=null)")
                                
                                # Получаем актуальную игру из auction_result
                                game_title = auction_result.get('title', '')
                                game_type = auction_result.get('type', '')
                                game_reward = auction_result.get('ggpReward', 0)
                                game_penalty = auction_result.get('ggpPenalty', 0)
                                timer_started = auction_result.get('timerStartedAt', '')
                                
                                required_action = item.get('requiredAction') or {}
                                action_kind = required_action.get('kind', '') if required_action else ''
                                
                                participants[name] = {
                                    'points': points,
                                    'selected': False,
                                    'game_title': game_title,
                                    'game_type': game_type,
                                    'game_reward': game_reward,
                                    'game_penalty': game_penalty,
                                    'action_kind': action_kind,
                                    'timer_started': timer_started,
                                    'timestamp': time.time()
                                }
                            else:
                                logger.warning(f"⚠️ [{idx}] player=null и нет в кэше, пропускаем")
                                continue
                        else:
                            # Нормальный случай - обновляем кэш
                            raw_name = player.get('name', '')
                            name = raw_name.strip() if raw_name else ''
                            name_lower = name.lower()
                            
                            if not name:
                                logger.warning(f"⚠️ [{idx}] Пропущен участник без имени")
                                continue
                            
                            if name_lower not in VALID_NAMES:
                                logger.warning(f"⚠️ [{idx}] Неизвестный участник: '{raw_name}'")
                                continue
                            
                            points = player.get('ggp', player.get('points', player.get('score', 0)))
                            
                            # Сохраняем в кэш
                            player_id = player.get('id', '')
                            if player_id:
                                self.player_cache[player_id] = {
                                    'name': name,
                                    'points': points,
                                    'timestamp': time.time()
                                }
                            
                            # Информация об игре/действии
                            auction_result = item.get('currentAuctionResult') or {}
                            game_title = auction_result.get('title', '') if auction_result else ''
                            game_type = auction_result.get('type', '') if auction_result else ''
                            game_reward = auction_result.get('ggpReward', 0) if auction_result else 0
                            game_penalty = auction_result.get('ggpPenalty', 0) if auction_result else 0
                            
                            # Время начала
                            timer_started = auction_result.get('timerStartedAt', '') if auction_result else ''
                            
                            required_action = item.get('requiredAction') or {}
                            action_kind = required_action.get('kind', '') if required_action else ''
                            
                            participants[name] = {
                                'points': points,
                                'selected': False,
                                'game_title': game_title,
                                'game_type': game_type,
                                'game_reward': game_reward,
                                'game_penalty': game_penalty,
                                'action_kind': action_kind,
                                'timer_started': timer_started,
                                'timestamp': time.time()
                            }
                            
                            logger.debug(f"  [{idx}] {name}: очки={points}, игра='{game_title}'")
                        
                    except Exception as e:
                        logger.warning(f"⚠️ [{idx}] Ошибка парсинга: {e}")
                        try:
                            logger.warning(f"   Сырые данные: {json.dumps(item, ensure_ascii=False)[:300] if item else 'None'}")
                        except:
                            pass
                        continue
                
                # Определяем активного стримера (у кого самый свежий timerStartedAt)
                if participants:
                    active_name = None
                    latest_time = ""
                    
                    for name, info in participants.items():
                        timer = info.get('timer_started', '')
                        if timer and timer > latest_time:
                            latest_time = timer
                            active_name = name
                    
                    if active_name:
                        participants[active_name]['selected'] = True
                        logger.info(f"✅ Активный стример: {active_name} (время: {latest_time})")
                    else:
                        logger.info("⚪ Активный стример не найден")
                
                # Проверяем что все 12 стримеров на месте
                missing = [name for name in STREAMERS.values() if name not in participants]
                if missing:
                    logger.warning(f"️ Отсутствуют стримеры: {missing}")
                else:
                    logger.info(f"✅ Все 12 стримеров на месте!")
                
                logger.info(f"✅ Обработано {len(participants)} участников")
                return participants
                
        except Exception as e:
            logger.error(f"❌ Ошибка при получении данных: {e}", exc_info=True)
            return {}
    
    def _get_leaderboard(self, data: Dict) -> list:
        return sorted(data.items(), key=lambda x: x[1]['points'], reverse=True)
    
    def _get_real_position(self, data: Dict, streamer_name: str) -> int:
        leaderboard = self._get_leaderboard(data)
        for i, (name, _) in enumerate(leaderboard, 1):
            if name == streamer_name:
                return i
        return 0
    
    async def get_detailed_streamer_info(self, streamer_name: str) -> Optional[str]:
        """Получает подробную информацию о стримере с отображением игры для всех"""
        try:
            if streamer_name not in STREAMERS.values():
                return None
            
            data = await self.get_participants_data()
            
            if streamer_name not in data:
                logger.warning(f"⚠️ Стример '{streamer_name}' не найден в данных API")
                logger.warning(f"   Доступные: {list(data.keys())}")
                return None
            
            info = data[streamer_name]
            real_position = self._get_real_position(data, streamer_name)
            
            message = f"👤 <b>{streamer_name}</b>\n"
            message += f"🏆 <b>Место в топе:</b> {real_position} из {len(data)}\n"
            message += f"⭐ <b>Очки:</b> {info['points']}\n"
            
            # Показываем игру для ВСЕХ у кого есть game_title (независимо от selected)
            if info.get('game_title'):
                game_title = info['game_title']
                game_type = info.get('game_type', '')
                game_reward = info.get('game_reward', 0)
                game_penalty = info.get('game_penalty', 0)
                
                if game_type == 'game':
                    message += f"\n🎮 <b>Игра:</b> {game_title}"
                else:
                    message += f"\n⚡ <b>Действие:</b> {game_title}"
                
                if game_reward:
                    message += f"\n💰 Награда: +{game_reward}"
                if game_penalty:
                    message += f"\n💔 Штраф: -{game_penalty}"
                
                # Для активного стримера показываем дополнительный статус
                if info.get('selected'):
                    message += f"\n🔥 <b>Статус:</b> Активен (главный)"
            else:
                message += f"\n⚪ <b>Статус:</b> Не активен"
            
            return message
            
        except Exception as e:
            logger.error(f" Ошибка: {e}", exc_info=True)
            return None
    
    async def send_notification(self, message: str):
        if not self.monitoring_groups:
            logger.warning("⚠️ Нет групп для отправки уведомлений")
            return
        
        success_count = 0
        for group in self.monitoring_groups:
            try:
                chat_id = group['chat_id']
                thread_id = group.get('thread_id')
                
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="HTML",
                    message_thread_id=thread_id
                )
                success_count += 1
                logger.info(f"📤 Отправлено в {chat_id}" + (f" (thread: {thread_id})" if thread_id else ""))
            except Exception as e:
                logger.error(f"❌ Ошибка отправки в {group}: {e}")
        
        logger.info(f"✅ Успешно отправлено в {success_count} из {len(self.monitoring_groups)} групп")
    
    async def start(self):
        @self.dp.message(Command("debug"))
        async def cmd_debug(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer(" Только для администраторов")
                return
            
            await message.answer("🔍 Получаю сырые данные из API...")
            
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            try:
                async with self.session.get(API_URL) as response:
                    data = await response.json()
                    
                    text = f" <b>Сырые данные API:</b>\n\n"
                    text += f"Всего: {data.get('data', {}).get('count', 0)}\n"
                    text += f"Массив: {len(data.get('data', {}).get('array', []))}\n\n"
                    
                    for idx, item in enumerate(data.get('data', {}).get('array', [])):
                        if item is None:
                            text += f"<b>{idx+1}. [NULL ITEM]</b>\n\n"
                            continue
                        
                        player = item.get('player')
                        if player is None:
                            auction = item.get('currentAuctionResult') or {}
                            player_id = auction.get('playerId', '')
                            game = auction.get('title', '')
                            
                            text += f"<b>{idx+1}. ??? (player=null!)</b>\n"
                            text += f"   playerId: {player_id}\n"
                            text += f"   Игра: {game or 'нет'}\n"
                            
                            # Показываем из кэша если есть
                            if player_id and player_id in self.player_cache:
                                cached_name = self.player_cache[player_id]['name']
                                text += f"   Кэш: {cached_name}\n"
                            text += "\n"
                        else:
                            name = player.get('name', '???')
                            points = player.get('ggp', 0)
                            auction = item.get('currentAuctionResult') or {}
                            game = auction.get('title', '')
                            timer = auction.get('timerStartedAt', '')
                            
                            text += f"<b>{idx+1}. {name}</b>\n"
                            text += f"   Очки: {points}\n"
                            text += f"   Игра: {game or 'нет'}\n"
                            text += f"   Таймер: {timer or 'нет'}\n\n"
                    
                    if len(text) > 4000:
                        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
                        for part in parts:
                            await message.answer(part, parse_mode="HTML")
                    else:
                        await message.answer(text, parse_mode="HTML")
                        
            except Exception as e:
                await message.answer(f"❌ Ошибка: {e}")
        
        @self.dp.message(Command("add_group"))
        async def cmd_add_group(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только для администраторов")
                return
            
            chat_id = message.chat.id
            thread_id = message.message_thread_id
            
            for group in self.monitoring_groups:
                if group['chat_id'] == chat_id and group.get('thread_id') == thread_id:
                    await message.answer("⚠️ Уже добавлена")
                    return
            
            group_info = {
                'chat_id': chat_id,
                'chat_title': message.chat.title or 'Unknown',
                'thread_id': thread_id,
                'added_at': time.time()
            }
            
            self.monitoring_groups.append(group_info)
            self.save_groups()
            
            thread_info = f"\n Ветка ID: {thread_id}" if thread_id else ""
            await message.answer(
                f"✅ <b>Группа добавлена!</b>\n\n"
                f"👥 {message.chat.title}\n"
                f"🆔 {chat_id}"
                f"{thread_info}"
            )
            
            if not self.monitoring_active:
                asyncio.create_task(self.monitor_loop())
        
        @self.dp.message(Command("remove_group"))
        async def cmd_remove_group(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только для администраторов")
                return
            
            chat_id = message.chat.id
            thread_id = message.message_thread_id
            
            self.monitoring_groups = [
                g for g in self.monitoring_groups 
                if not (g['chat_id'] == chat_id and g.get('thread_id') == thread_id)
            ]
            
            self.save_groups()
            await message.answer("✅ Удалена из мониторинга")
        
        @self.dp.message(Command("list_groups"))
        async def cmd_list_groups(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только для администраторов")
                return
            
            if not self.monitoring_groups:
                await message.answer("📋 Пусто")
                return
            
            text = "📋 <b>Группы мониторинга:</b>\n\n"
            for i, group in enumerate(self.monitoring_groups, 1):
                thread_info = f" (ветка #{group['thread_id']})" if group.get('thread_id') else ""
                text += f"{i}. <b>{group['chat_title']}</b>{thread_info}\n"
                text += f"    {group['chat_id']}\n\n"
            
            text += f"\n🟢 Мониторинг: {'активен' if self.monitoring_active else 'неактивен'}"
            
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("test_notify"))
        async def cmd_test_notify(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только для администраторов")
                return
            
            await message.answer(" Отправляю тест...")
            
            test_message = (
                "🔔 <b>Тест</b>\n\n"
                "✅ Всё работает!"
            )
            await self.send_notification(test_message)
            await message.answer("✅ Отправлено")
        
        @self.dp.message(Command("my_id"))
        async def cmd_my_id(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только для администраторов")
                return
            
            chat_id = message.chat.id
            thread_id = message.message_thread_id
            
            text = f"🆔 <b>Информация:</b>\n\n"
            text += f"👥 {message.chat.title}\n"
            text += f"📍 Chat ID: <code>{chat_id}</code>\n"
            
            if thread_id:
                text += f"📌 Ветка ID: <code>{thread_id}</code>\n"
                text += f"\n💡 <code>/monitor {chat_id} {thread_id}</code>"
            else:
                text += f"\n💡 <code>/monitor {chat_id}</code>"
            
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            admin_text = ""
            if self.is_admin(message.from_user.id):
                admin_text = (
                    "\n <b>Админ:</b>\n"
                    "/add_group ➕ добавить группу\n"
                    "/remove_group ➖ удалить\n"
                    "/list_groups 📋 список\n"
                    "/test_notify 🧪 тест\n"
                    "/my_id 🆔 ID чата\n"
                    "/debug 🔍 сырые данные\n"
                )
            
            status_text = f"\n📡 <b>Мониторинг:</b> {'🟢' if self.monitoring_active else '🔴'}"
            
            await message.answer(
                "🤖 <b>Бот Nassal.pro</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "📋 <b>Команды:</b>\n\n"
                "/rating 🏆 рейтинг\n"
                "/points 📊 таблица\n"
                "/streamer [номер/имя] 👤 инфо\n"
                "/list  список\n"
                "/monitor 🔔 мониторинг"
                + status_text
                + admin_text,
                reply_markup=self.get_streamer_keyboard()
            )
        
        @self.dp.message(Command("list"))
        async def cmd_list(message: types.Message):
            text = "📋 <b>Список участников:</b>\n\n"
            for num, name in STREAMERS.items():
                text += f"{num}. <b>{name}</b>\n"
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("rating"))
        async def cmd_rating(message: types.Message):
            await message.answer("🔄 Получаю рейтинг...")
            data = await self.get_participants_data()
            
            if not data:
                await message.answer("❌ Не удалось получить данные")
                return
            
            leaderboard = self._get_leaderboard(data)
            
            text = "🏆 <b>РЕЙТИНГ</b>\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n\n"
            
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            
            for i, (name, info) in enumerate(leaderboard, 1):
                points = info['points']
                medal = medals.get(i, f"{i}.")
                marker = "" if info.get('selected') else ""
                
                if points > 0:
                    points_str = f"+{points}"
                    points_emoji = "🟢"
                elif points < 0:
                    points_str = str(points)
                    points_emoji = "🔴"
                else:
                    points_str = "0"
                    points_emoji = "⚪"
                
                if i <= 3:
                    text += f"{medal} <b>{marker}{name}</b> — {points_emoji} <b>{points_str}</b>\n"
                else:
                    text += f"{i}. {marker}{name} — {points_emoji} <b>{points_str}</b>\n"
            
            text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
            text += f"👥 Всего: {len(data)}"
            
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("points"))
        async def cmd_points(message: types.Message):
            await message.answer("🔄 Получаю очки...")
            data = await self.get_participants_data()
            
            if not data:
                await message.answer("❌ Не удалось получить данные")
                return
            
            text = "📊 <b>ТАБЛИЦА ОЧКОВ</b>\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n\n"
            
            leaderboard = self._get_leaderboard(data)
            
            for i, (name, info) in enumerate(leaderboard, 1):
                points = info['points']
                selected = info.get('selected', False)
                
                if points > 0:
                    emoji = ""
                    points_str = f"+{points}"
                elif points < 0:
                    emoji = "🔴"
                    points_str = str(points)
                else:
                    emoji = ""
                    points_str = "0"
                
                marker = "🔥" if selected else ""
                text += f"{i}. {marker} <b>{name}</b> — {emoji} <b>{points_str}</b>\n"
            
            text += "\n━━━━━━━━━━━━━━━━━━━━\n"
            text += "🔥 — активен"
            
            await message.answer(text, parse_mode="HTML")
        
        @self.dp.message(Command("streamer"))
        async def cmd_streamer(message: types.Message):
            if len(message.text.split()) < 2:
                await message.answer("❌ Укажите номер или имя\nПример: /streamer 1")
                return
            
            query = message.text.split(maxsplit=1)[1].strip()
            streamer_name = None
            
            if query.isdigit():
                num = int(query)
                streamer_name = STREAMERS.get(num)
            else:
                query_lower = query.lower().strip()
                if query_lower in STREAMERS_BY_NAME:
                    streamer_name = STREAMERS[STREAMERS_BY_NAME[query_lower]]
                else:
                    for name in STREAMERS.values():
                        if query_lower in name.lower():
                            streamer_name = name
                            break
            
            if not streamer_name:
                await message.answer(f"❌ '{query}' не найден")
                return
            
            await message.answer(f"⏳ Загрузка <b>{streamer_name}</b>...", parse_mode="HTML")
            info = await self.get_detailed_streamer_info(streamer_name)
            
            if info:
                await message.answer(info, parse_mode="HTML")
            else:
                await message.answer(
                    f"❌ Не удалось получить информацию\n\n"
                    f"💡 Попробуй /debug"
                )
        
        @self.dp.message(Command("monitor"))
        async def cmd_monitor(message: types.Message):
            args = message.text.split()[1:] if len(message.text.split()) > 1 else []
            
            if len(args) == 0:
                chat_id = message.chat.id
                thread_id = message.message_thread_id
                chat_title = message.chat.title or 'Unknown'
            elif len(args) == 1 and self.is_admin(message.from_user.id):
                try:
                    chat_id = int(args[0])
                    thread_id = None
                    chat_title = f"Группа {chat_id}"
                except ValueError:
                    await message.answer("❌ Неверный chat_id")
                    return
            elif len(args) == 2 and self.is_admin(message.from_user.id):
                try:
                    chat_id = int(args[0])
                    thread_id = int(args[1])
                    chat_title = f"Группа {chat_id}, ветка {thread_id}"
                except ValueError:
                    await message.answer("❌ Неверные ID")
                    return
            else:
                if not self.is_admin(message.from_user.id):
                    await message.answer("❌ Только админ может указывать ID\n\nИспользуй: /monitor")
                    return
                else:
                    await message.answer("❌ Неверный формат")
                    return
            
            for group in self.monitoring_groups:
                if group['chat_id'] == chat_id and group.get('thread_id') == thread_id:
                    await message.answer("✅ Уже активен")
                    return
            
            group_info = {
                'chat_id': chat_id,
                'chat_title': chat_title,
                'thread_id': thread_id,
                'added_at': time.time()
            }
            
            self.monitoring_groups.append(group_info)
            self.save_groups()
            
            thread_info = f"\n📌 Ветка: {thread_id}" if thread_id else ""
            
            await message.answer(
                f"🔔 <b>Мониторинг активирован!</b>\n"
                f"\n👥 {chat_title}"
                f"\n🆔 {chat_id}"
                f"{thread_info}\n\n"
                f"Буду присылать:\n"
                f"• 💰 Изменения очков\n"
                f"• 🎮 Смену игр\n"
                f"• 📊 Изменения позиций",
                parse_mode="HTML"
            )
            
            if not self.monitoring_active:
                logger.info("🚀 Запускаю мониторинг...")
                asyncio.create_task(self.monitor_loop())
        
        @self.dp.message(Command("stop"))
        async def cmd_stop(message: types.Message):
            if not self.is_admin(message.from_user.id):
                await message.answer("❌ Только для администраторов")
                return
            
            self.monitoring_active = False
            await message.answer("👋 Остановлен")
            if self.session:
                await self.session.close()
            await self.bot.close()
        
        @self.dp.message()
        async def handle_keyboard(message: types.Message):
            text = message.text.strip()
            for num, name in STREAMERS.items():
                if text == f"{num}. {name}" or text == name:
                    await message.answer(f"⏳ Загрузка <b>{name}</b>...", parse_mode="HTML")
                    info = await self.get_detailed_streamer_info(name)
                    if info:
                        await message.answer(info, parse_mode="HTML")
                    else:
                        await message.answer(f"❌ Не удалось получить информацию\n\n💡 /debug")
                    return
        
        logger.info("🚀 Бот запущен!")
        logger.info(f"👥 Админы: {ADMINS}")
        logger.info(f"📋 Групп: {len(self.monitoring_groups)}")
        
        if self.monitoring_groups:
            logger.info("🔄 Запускаю мониторинг автоматически...")
            asyncio.create_task(self.monitor_loop())
        else:
            logger.info("⚠️ Нет групп. Вызовите /monitor")
        
        await self.dp.start_polling(self.bot)
    
    async def monitor_loop(self):
        logger.info("🔄 Запуск monitor_loop...")
        self.monitoring_active = True
        
        logger.info("📊 Получаю начальное состояние...")
        initial_data = await self.get_participants_data()
        
        if not initial_data:
            logger.error("❌ Не удалось получить начальное состояние")
            self.monitoring_active = False
            return
        
        self.previous_data = initial_data
        logger.info(f"✅ Запомнено ({len(initial_data)} участников)")
        logger.info("🔍 Слежу за изменениями...")
        
        cycle_count = 0
        while self.monitoring_active:
            try:
                cycle_count += 1
                if cycle_count % 6 == 0:
                    logger.info(f"🔄 Цикл #{cycle_count}, групп: {len(self.monitoring_groups)}")
                
                current_data = await self.get_participants_data()
                
                if not current_data:
                    logger.warning("⚠️ Нет данных, пропускаю")
                    await asyncio.sleep(10)
                    continue
                
                if self.previous_data:
                    changes = self.compare_data(self.previous_data, current_data)
                    
                    if changes:
                        logger.info(f"📢 Найдено изменений: {len(changes)}")
                        notification = self._format_notification(changes)
                        await self.send_notification(notification)
                        logger.info(f"📤 Отправлено")
                    else:
                        logger.debug("✓ Нет изменений")
                
                self.previous_data = current_data
                
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле: {e}", exc_info=True)
            
            await asyncio.sleep(10)
        
        logger.info("⏹️ Мониторинг остановлен")
    
    def _format_notification(self, changes: list) -> str:
        notification = "🔔 <b>ИЗМЕНЕНИЯ НА NASSAL.PRO</b>\n"
        notification += "━━━━━━━━━━━━━━━━━━━━\n\n"
        notification += "\n".join(changes)
        notification += "\n\n━━━━━━━━━━━━━━━━━━━━"
        return notification
    
    def compare_data(self, old_data: Dict, new_data: Dict) -> list:
        changes = []
        
        old_positions = {}
        new_positions = {}
        
        old_leaderboard = self._get_leaderboard(old_data)
        new_leaderboard = self._get_leaderboard(new_data)
        
        for i, (name, _) in enumerate(old_leaderboard, 1):
            old_positions[name] = i
        
        for i, (name, _) in enumerate(new_leaderboard, 1):
            new_positions[name] = i
        
        # 1. Изменения позиций
        position_changes = []
        for name in new_data.keys():
            if name in old_positions and name in new_positions:
                old_pos = old_positions[name]
                new_pos = new_positions[name]
                
                if old_pos != new_pos:
                    diff = old_pos - new_pos
                    if diff > 0:
                        arrow = "⬆️"
                        direction = "поднялся"
                        emoji = "🚀"
                    else:
                        arrow = "️"
                        direction = "упал"
                        emoji = "📉"
                        diff = abs(diff)
                    
                    position_changes.append(
                        f"{emoji} <b>{name}</b> {direction} на {diff} {self._get_position_word(diff)}!\n"
                        f"{arrow} Было: {old_pos} → Стало: {new_pos}"
                    )
        
        if position_changes:
            changes.append("📊 <b>ИЗМЕНЕНИЯ В ПОЗИЦИЯХ:</b>\n\n" + "\n\n".join(position_changes))
        
        # 2. Изменения очков
        points_changes = []
        for name, data in new_data.items():
            if name in old_data:
                old_points = old_data[name].get('points', 0)
                new_points = data.get('points', 0)
                
                if old_points != new_points:
                    diff = new_points - old_points
                    if diff > 0:
                        arrow = "⬆️"
                        emoji = "💚"
                        sign = "+"
                    else:
                        arrow = "⬇️"
                        emoji = "💔"
                        sign = ""
                    
                    points_changes.append(
                        f"{emoji} <b>{name}</b>\n"
                        f"{arrow} Очки: {old_points} → {new_points} ({sign}{diff})"
                    )
        
        if points_changes:
            changes.append("💰 <b>ИЗМЕНЕНИЯ В ОЧКАХ:</b>\n\n" + "\n\n".join(points_changes))
        
        # 3. Смена игр
        game_changes = []
        for name, data in new_data.items():
            if name in old_data:
                old_game = old_data[name].get('game_title', '')
                new_game = data.get('game_title', '')
                
                if old_game != new_game and new_game:
                    game_changes.append(
                        f"🎮 <b>{name}</b>\n"
                        f"❌ Было: {old_game or 'Нет'}\n"
                        f"✅ Стало: {new_game}"
                    )
        
        if game_changes:
            changes.append("🎮 <b>СМЕНА ИГР:</b>\n\n" + "\n\n".join(game_changes))
        
        return changes
    
    def _get_position_word(self, count: int) -> str:
        if count == 1:
            return "позицию"
        elif 2 <= count <= 4:
            return "позиции"
        else:
            return "позиций"


async def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден!")
        return
    
    logger.info(f"✅ Запуск бота")
    monitor = NassalMonitor(BOT_TOKEN)
    await monitor.start()


if __name__ == "__main__":
    asyncio.run(main())

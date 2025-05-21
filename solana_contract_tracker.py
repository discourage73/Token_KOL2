from telethon import TelegramClient, events
import asyncio
import logging
import sys
import re
import json
import os
import time
import signal
from datetime import datetime, timedelta
import pandas as pd  # Добавляем импорт pandas для работы с Excel

# Исправляем кодировку для Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Для Python 3.6, который не имеет метода reconfigure
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)

# Настройка безопасного логирования с обработкой ошибок кодировки
class UnicodeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except UnicodeEncodeError:
            # Заменяем проблемные символы на '?'
            msg = self.format(record)
            try:
                stream = self.stream
                stream.write(msg.encode(stream.encoding, errors='replace').decode(stream.encoding) + self.terminator)
                self.flush()
            except (UnicodeError, IOError):
                self.handleError(record)
        except Exception:
            self.handleError(record)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_log.txt", encoding='utf-8'),  # Файл с UTF-8
    ]
)
# Добавляем собственный обработчик для консоли
console_handler = UnicodeStreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger = logging.getLogger(__name__)
logger.addHandler(console_handler)

# Безопасное преобразование строк для логирования
def safe_str(text):
    """Безопасное преобразование текста с эмодзи для логирования."""
    if text is None:
        return "None"
    try:
        # Ограничиваем длину и безопасно представляем текст
        return str(text[:100]).replace('\n', ' ') + "..."
    except:
        return "[Текст содержит непечатаемые символы]"

# Импортируем конфигурацию
from config import TELEGRAM_TOKEN, DEXSCREENER_API_URL, API_ID, API_HASH, TARGET_BOT

# Минимальное количество каналов для отправки сигнала в RadarDexBot
MIN_SIGNALS = 8  # Токен должен появиться минимум в 7 каналах

# Канал для отправки токенов прошедших Rule1
MOON_CRYPTO_MONKEY_CHANNEL = "MoonCryptoMonkey"

# Словарь соответствия тегов и эмодзи
TAG_EMOJI_MAP = {
    "snipeKOL": "🎯",     # дартс
    "snipeGEM": "💎",     # бриллиант
    "TG_KOL": "🍀",       # клевер
    "EarlyGEM": "💎",     # бриллиант
    "EarlyKOL": "⚡",      # молния
    "SmartMoney": "💵",   # доллар
    "Whale Bought": "🐋", # кит
    "Volume alert": "🚀", # ракета
    "AlphAI_KOL": "🐂"    # бык
}

# Каналы для мониторинга (ID канала -> имя)
SOURCE_CHANNELS = {
    2234923591: {"name": "@Tanjirocall", "tag": "TG_KOL"},
    1853203827: {"name": "@CryptoMafiaPlays", "tag": "TG_KOL"},
    2121262250: {"name": "@DoctoreDegens", "tag": "TG_KOL"},
    2010667852: {"name": "@SONIC_SPEED_CALLS", "tag": "TG_KOL"},
    1975976600: {"name": "@smartmaxidegens", "tag": "TG_KOL"},
    2055101998: {"name": "@metagambler", "tag": "TG_KOL"},
    1500214409: {"name": "@GemsmineEth", "tag": "TG_KOL"},
    1794471884: {"name": "@MineGems", "tag": "TG_KOL"},
    1603469217: {"name": "@ZionGems", "tag": "TG_KOL"},
    2366686880: {"name": "@Ranma_Calls_Solana", "tag": "snipeKOL"},
    1510769567: {"name": "@BatmanGamble", "tag": "TG_KOL"},
    1818702441: {"name": "@michiosuzukiofsatoshicalls", "tag": "TG_KOL"},
    1763265784: {"name": "@MarkDegens", "tag": "TG_KOL"},
    1983450418: {"name": "@shitcoinneverland", "tag": "TG_KOL"},
    2284638367: {"name": "@GemDynasty", "tag": "TG_KOL"},
    1554385364: {"name": "@SultanPlays", "tag": "TG_KOL"},
    1869537526: {"name": "@POSEIDON_DEGEN_CALLS", "tag": "TG_KOL"},
    1631609672: {"name": "@lowtaxcrypto", "tag": "TG_KOL"},
    2276696688: {"name": "@CrikeyCallz", "tag": "TG_KOL"},
    1851567457: {"name": "@Insider_ECA", "tag": "TG_KOL"},
    1756488143: {"name": "@lowtaxsolana", "tag": "TG_KOL"},
    1883929251: {"name": "@gogetagambles", "tag": "TG_KOL"},
    1711812162: {"name": "@Chadleycalls", "tag": "TG_KOL"},
    2362597228: {"name": "@Parkergamblles", "tag": "EarlyKOL"},
    2000078706: {"name": "@NIKOLA_CALLS", "tag": "TG_KOL"}, 
    2696740432: {"name": "@cringemonke2", "tag": "SmartMoney"},
    2051055592: {"name": "@Mrbigbagcalls", "tag": "TG_KOL"},
    2299508637: {"name": "@BaddiesAi", "tag": "TG_KOL"},
    1671616196: {"name": "@veigargambles", "tag": "TG_KOL"},
    2441888429: {"name": "@BasedchadsGamble", "tag": "TG_KOL"},
    1915368269: {"name": "@NFG_GAMBLES", "tag": "TG_KOL"},
    2514471362: {"name": "@cringemonke", "tag": "Whale Bought"},
    2144494116: {"name": "@GM_Degencalls", "tag": "TG_KOL"},
    2030684366: {"name": "@uranusX100", "tag": "TG_KOL"},
    1903316574: {"name": "@x666calls", "tag": "TG_KOL"},
    # Добавляем недостающие каналы
    2441746747: {"name": "@DegenRaydiumSig", "tag": "TG_KOL"},
    2458682762: {"name": "@heracatusspread", "tag": "TG_KOL"},
    2497100790: {"name": "@DegenPumpfunSig", "tag": "TG_KOL"},
    2141713314: {"name": "@TheDegenBoysLounge", "tag": "TG_KOL"},
    1988420013: {"name": "@SAVANNAHCALLS", "tag": "TG_KOL"},
    2318939340: {"name": "@SolanaXpertWallet", "tag": "SmartMoney"},
    2352003756: {"name": "@SolanaWhalesMarket", "tag": "Whale Bought"},
     # Добавляем недостающие каналы
    2531914184: {"name": "@astrasolcalls", "tag": "TG_KOL"},
    1159025019: {"name": "@TopWhaleCalls", "tag": "TG_KOL"},
    2420387755: {"name": "@degenhistory", "tag": "TG_KOL"},
    1758611100: {"name": "@mad_apes_gambles", "tag": "TG_KOL"},
    1695560898: {"name": "@feihuziben", "tag": "TG_KOL"},
    2536988241: {"name": "@AlphaONE_volumealerts", "tag": "Volume alert"},
    2534842510: {"name": "@AlphAI_signals_sol_en", "tag": "AlphAI_KOL"}
}

# Словарь для динамического хранения имен каналов
channel_names_cache = {}

# Файлы базы данных
DB_FILE = 'tokens_database.json'
TRACKER_DB_FILE = 'tokens_tracker_database.json'
TRACKER_EXCEL_FILE = 'tokens_tracker_database.xlsx'

# Хранилище токенов
tokens_db = {}
tracker_db = {}  # Хранилище для токенов, достигших MIN_SIGNALS

# Получение имени канала по ID
async def get_channel_name_async(client, chat_id):
    """Асинхронно получает имя канала по ID, с кэшированием."""
    # Сначала проверяем кэш и словарь
    str_id = str(chat_id)
    
    # Обрабатываем ID с префиксом '-100'
    if str_id.startswith('-100'):
        # Для каналов с ID вида -1001234567890
        orig_id = chat_id
        stripped_id = int(str_id[4:])  # Удаляем -100 из начала
    else:
        orig_id = chat_id
        stripped_id = chat_id
    
    # Проверяем наш словарь каналов
    if stripped_id in SOURCE_CHANNELS:
        channel_info = SOURCE_CHANNELS[stripped_id]
        if isinstance(channel_info, dict):
            return channel_info["name"]
        return channel_info
    
    # Пробуем получить из кэша
    if str_id in channel_names_cache:
        return channel_names_cache[str_id]
    
    # Пробуем получить от Telegram API
    try:
        entity = await client.get_entity(orig_id)
        if hasattr(entity, 'username') and entity.username:
            name = f"@{entity.username}"
        elif hasattr(entity, 'title'):
            name = f"@{entity.title}"
        else:
            name = f"@channel_{abs(stripped_id)}"
        
        # Сохраняем в кэш
        channel_names_cache[str_id] = name
        return name
    except Exception as e:
        logger.error(f"Ошибка при получении имени канала {chat_id}: {e}")
        return f"@channel_{abs(stripped_id)}"

def get_channel_name(chat_id):
    """Синхронная обертка для получения имени канала из словаря."""
    # Обрабатываем ID с префиксом '-100'
    if str(chat_id).startswith('-100'):
        # Для каналов с ID вида -1001234567890
        stripped_id = int(str(chat_id)[4:])  # Удаляем -100 из начала
    else:
        stripped_id = chat_id
    
    # Пытаемся найти в словаре
    channel_info = SOURCE_CHANNELS.get(stripped_id)
    if channel_info:
        if isinstance(channel_info, dict):
            return channel_info["name"]
        return channel_info
    else:
        # Если не нашли, возвращаем общее обозначение
        return f"@channel_{abs(stripped_id)}"

def get_channel_emojis_by_names(channel_names):
    """Получает эмодзи каналов по их именам."""
    emojis = ""
    for name in channel_names:
        # Ищем канал по имени
        for chat_id, info in SOURCE_CHANNELS.items():
            if isinstance(info, dict) and info["name"] == name:
                tag = info["tag"]
                emoji = TAG_EMOJI_MAP.get(tag, "🍀")  # Используем клевер по умолчанию
                emojis += emoji
                break
            elif info == name:  # Для обратной совместимости
                emojis += "🍀"  # Используем клевер по умолчанию
                break
    
    return emojis

def extract_solana_contracts(text):
    """Извлекает адреса контрактов Solana из текста."""
    if not text:
        return []
        
    # Паттерн для контрактов Solana: начинаются обычно с определенных букв и имеют 32-44 символа
    pattern = r"\b[a-zA-Z0-9]{32,44}\b"
    potential_contracts = re.findall(pattern, text)
    
    # Отфильтровываем кошельки разработчиков и оставляем только контракты токенов
    filtered_contracts = []
    for contract in potential_contracts:
        # Преобразуем в нижний регистр для проверок на содержимое
        contract_lower = contract.lower()
        
        # Проверяем основные ключевые слова
        if ('pump' in contract_lower or 
            'moon' in contract_lower or 
            'bonk' in contract_lower or
            re.match(r'^[0-9]', contract)):
            filtered_contracts.append(contract)
            continue
            
        # Дополнительные признаки токенов:
        
        # 1. Начинается с заглавной буквы и имеет определенные паттерны заглавных букв
        if re.match(r'^[A-Z]', contract) and len(re.findall(r'[A-Z]', contract)) >= 3:
            # Паттерн начинается с заглавной буквы и имеет не менее 3 заглавных букв
            filtered_contracts.append(contract)
            continue
            
        # 2. Имеет чередование регистров (маленькая-большая буква)
        if re.search(r'[a-z][A-Z][a-z]', contract) or re.search(r'[A-Z][a-z][A-Z]', contract):
            filtered_contracts.append(contract)
            continue
            
        # 3. Содержит много цифр (не менее 5) и много заглавных букв (не менее 5)
        digit_count = sum(c.isdigit() for c in contract)
        upper_count = sum(c.isupper() for c in contract)
        if digit_count >= 5 and upper_count >= 5:
            filtered_contracts.append(contract)
            continue
            
        # 4. Проверка на специфичные последовательности
        if any(seq in contract for seq in ['Fg', 'Hc', 'Dk', 'CHL', 'GukM']):
            filtered_contracts.append(contract)
            continue
    
    return filtered_contracts

# Функция загрузки базы данных
def load_database():
    global tokens_db, tracker_db
    try:
        # Загружаем основную базу данных
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                tokens_db = json.load(f)
            logger.info(f"Загружено {len(tokens_db)} токенов из базы данных")
        else:
            logger.info("База данных не найдена, создаем новую")
            tokens_db = {}
            
        # Загружаем базу данных с отслеживаемыми токенами
        if os.path.exists(TRACKER_DB_FILE):
            with open(TRACKER_DB_FILE, 'r', encoding='utf-8') as f:
                tracker_db = json.load(f)
            logger.info(f"Загружено {len(tracker_db)} отслеживаемых токенов из базы данных")
            
            # Обновляем токены эмодзи, если это необходимо
            update_tracker_with_emojis()
        else:
            logger.info("База данных отслеживаемых токенов не найдена, создаем новую")
            tracker_db = {}
    except Exception as e:
        logger.error(f"Ошибка при загрузке базы данных: {e}")
        tokens_db = {}
        tracker_db = {}

# Функция для добавления эмодзи к существующим токенам при загрузке базы данных
def update_tracker_with_emojis():
    """
    Проверяет токены в базе трекера и добавляет поле 'emojis',
    если его нет, на основе тегов каналов.
    """
    try:
        updates_count = 0
        for contract, data in tracker_db.items():
            # Если поле emojis отсутствует, добавляем его
            if 'emojis' not in data or not data['emojis']:
                # Получаем эмодзи для каналов
                emojis = get_channel_emojis_by_names(data.get('channels', []))
                
                # Добавляем эмодзи в данные трекера
                tracker_db[contract]['emojis'] = emojis
                updates_count += 1
                logger.info(f"Добавлены эмодзи '{emojis}' для токена {contract}")
                
                # Обновляем channel_count, если он не соответствует
                channels = data.get('channels', [])
                if data.get('channel_count', 0) != len(channels):
                    tracker_db[contract]['channel_count'] = len(channels)
                    logger.info(f"Обновлен channel_count для токена {contract}: {len(channels)}")
        
        # Если были обновления, сохраняем базу данных
        if updates_count > 0:
            logger.info(f"Обновлено {updates_count} токенов с эмодзи")
            save_tracker_database()
            save_tracker_excel()
    
    except Exception as e:
        logger.error(f"Ошибка при обновлении эмодзи в базе трекера: {e}")
        import traceback
        logger.error(traceback.format_exc())

# Функция сохранения базы данных
def save_database():
    try:
        # Сохраняем основную базу данных
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(tokens_db, f, ensure_ascii=False, indent=4)
        logger.info(f"Сохранено {len(tokens_db)} токенов в базу данных")
        
        # Сохраняем базу данных отслеживаемых токенов
        save_tracker_database()
    except Exception as e:
        logger.error(f"Ошибка при сохранении базы данных: {e}")

# Функция сохранения базы данных отслеживаемых токенов (JSON)
def save_tracker_database():
    try:
        with open(TRACKER_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(tracker_db, f, ensure_ascii=False, indent=4)
        logger.info(f"Сохранено {len(tracker_db)} отслеживаемых токенов в JSON базу данных")
    except Exception as e:
        logger.error(f"Ошибка при сохранении базы данных отслеживаемых токенов: {e}")

# Функция сохранения базы данных отслеживаемых токенов в Excel
def save_tracker_excel():
    try:
        # Подготавливаем данные для Excel
        excel_data = []
        for contract, data in tracker_db.items():
            # Создаем запись для каждого токена
            row = {
                'contract': contract,
                'first_seen': data.get('first_seen', ''),
                'signal_reached_time': data.get('signal_reached_time', ''),
                'channel_count': data.get('channel_count', 0),
                'channels': ', '.join(data.get('channels', [])),
                'emojis': data.get('emojis', ''),  # Добавляем поле с эмодзи
                'Signals15': data.get('Signals15', 0),  # Добавляем поле Signals15
                'Age': data.get('Age', 0),  # Добавляем поле Age в минутах
                'Rule1_passed': data.get('Rule1_passed', False)  # Добавляем поле для Rule1
            }
            
            # Добавляем времена обнаружения по каналам
            channel_times = data.get('channel_times', {})
            for channel, time in channel_times.items():
                row[f'time_{channel}'] = time
                
            excel_data.append(row)
            
        # Создаем DataFrame и сохраняем в Excel
        df = pd.DataFrame(excel_data)
        df.to_excel(TRACKER_EXCEL_FILE, index=False)
        logger.info(f"Сохранено {len(tracker_db)} отслеживаемых токенов в Excel базу данных")
    except Exception as e:
        logger.error(f"Ошибка при сохранении Excel базы данных отслеживаемых токенов: {e}")

# Функция анализа токена для Rule1
def analyze_token_for_rule1(contract, token_data):
    """Анализирует токен для применения правила Rule1."""
    try:
        # Получаем время первого появления и достижения сигнала
        first_seen_str = token_data.get('first_seen', '')
        signal_reached_time_str = token_data.get('signal_reached_time', '')
        
        if not first_seen_str or not signal_reached_time_str:
            logger.info(f"Токен {contract}: нет данных о времени для анализа Rule1")
            return False
        
        # Преобразуем строки времени в datetime объекты
        first_seen = datetime.strptime(first_seen_str, "%H:%M:%S")
        signal_reached = datetime.strptime(signal_reached_time_str, "%Y-%m-%d %H:%M:%S")
        
        # Для расчета Age используем только время
        first_seen_time = first_seen.time()
        signal_reached_time = signal_reached.time()
        
        # Преобразуем в секунды для вычисления разности
        first_seen_seconds = first_seen_time.hour * 3600 + first_seen_time.minute * 60 + first_seen_time.second
        signal_reached_seconds = signal_reached_time.hour * 3600 + signal_reached_time.minute * 60 + signal_reached_time.second
        
        # Обрабатываем случай, когда signal_reached < first_seen (переход через полночь)
        if signal_reached_seconds < first_seen_seconds:
            signal_reached_seconds += 24 * 3600  # Добавляем сутки
        
        age_seconds = signal_reached_seconds - first_seen_seconds
        age_minutes = age_seconds / 60.0
        
        # Получаем каналы и времена их появления
        channels = token_data.get('channels', [])
        channel_times = token_data.get('channel_times', {})
        
        # Считаем Signals15
        signals15 = 0
        for channel in channels:
            if channel in channel_times:
                channel_time_str = channel_times[channel]
                channel_time = datetime.strptime(channel_time_str, "%H:%M:%S").time()
                channel_seconds = channel_time.hour * 3600 + channel_time.minute * 60 + channel_time.second
                
                # Обрабатываем случай перехода через полночь
                if channel_seconds < first_seen_seconds:
                    channel_seconds += 24 * 3600
                
                time_diff_seconds = channel_seconds - first_seen_seconds
                time_diff_minutes = time_diff_seconds / 60.0
                
                if time_diff_minutes <= 15:
                    signals15 += 1
        
        # Обновляем данные токена
        tracker_db[contract]['Signals15'] = signals15
        tracker_db[contract]['Age'] = age_minutes
        
        # Применяем Rule1
        rule1_passed = signals15 >= 8 and age_minutes <= 5
        tracker_db[contract]['Rule1_passed'] = rule1_passed
        
        logger.info(f"Токен {contract}: Signals15={signals15}, Age={age_minutes:.2f} минут, Rule1={rule1_passed}")
        
        return rule1_passed
        
    except Exception as e:
        logger.error(f"Ошибка при анализе токена {contract} для Rule1: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

# Функция добавления токена в базу отслеживания
def add_to_tracker(contract, token_data, emojis):
    """Добавляет токен, достигший MIN_SIGNALS, в базу отслеживания."""
    try:
        # Проверяем, есть ли уже этот токен в базе
        if contract in tracker_db:
            logger.info(f"Токен {contract} уже есть в базе отслеживания")
            return False
        
        # Формируем данные для трекера
        tracker_data = {
            'contract': contract,
            'first_seen': token_data.get('first_seen', ''),
            'signal_reached_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'channel_count': token_data.get('channel_count', 0),
            'channels': token_data.get('channels', []),
            'channel_times': token_data.get('channel_times', {}),
            'emojis': emojis  # Добавляем эмодзи в трекер
        }
        
        # Добавляем в базу отслеживания
        tracker_db[contract] = tracker_data
        logger.info(f"Токен {contract} добавлен в базу отслеживания с эмодзи: {emojis}")
        
        # Анализируем токен для Rule1 и сохраняем результат
        rule1_passed = analyze_token_for_rule1(contract, tracker_data)
        
        # Сохраняем базы данных
        save_tracker_database()
        save_tracker_excel()
        
        return rule1_passed
    except Exception as e:
        logger.error(f"Ошибка при добавлении токена в базу отслеживания: {e}")
        return False

# Упрощенная функция форматирования времени
def format_time_diff(first_seen_str, signal_reached_time):
    """Форматирует разницу времени между первым сигналом и достижением MIN_SIGNALS."""
    try:
        # Преобразуем строки времени в объекты datetime
        first_seen = datetime.strptime(first_seen_str, "%H:%M:%S")
        now = datetime.now()
        
        # Устанавливаем время из first_seen в сегодняшний день
        first_datetime = datetime.combine(now.date(), first_seen.time())
        
        # Если first_seen позже текущего времени, значит это было вчера
        if first_datetime > now:
            first_datetime = first_datetime - timedelta(days=1)
        
        # Вычисляем разницу
        diff = now - first_datetime
        
        # Разбиваем на дни, часы, минуты, секунды
        days = diff.days
        seconds = diff.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        
        # Форматируем результат
        if days > 0:
            return f"{days}d {hours}:{minutes:02d} h"
        elif hours > 0:
            return f"{hours}:{minutes:02d} h"
        else:
            return f"{minutes}:{seconds:02d} min"
            
    except Exception as e:
        logger.error(f"Ошибка при форматировании времени: {e}")
        return "unknown time"

async def main():
    # Явный вывод о запуске программы
    print("Скрипт запущен! Проверьте логи в файле bot_log.txt")
    logger.info("Скрипт запущен!")
    
    # Загружаем базу данных токенов
    load_database()
    
    # Подключаемся к Telegram с улучшенными параметрами
    client = TelegramClient(
        'test_session', 
        API_ID, 
        API_HASH,
        connection_retries=10,
        retry_delay=5,
        auto_reconnect=True,
        request_retries=10
    )
    
    await client.start()
    
    logger.info("Подключение к Telegram успешно установлено")
    
    # Отправляем тестовое сообщение
    try:
        await client.send_message(
            TARGET_BOT, 
            f"🔄 Бот запущен и отслеживает каналы: {len(SOURCE_CHANNELS)}\n\n"
            f"ℹ️ Минимальное количество каналов для сигнала: {MIN_SIGNALS}\n"
            f"🎯 Rule1 фильтр для {MOON_CRYPTO_MONKEY_CHANNEL}: Signals15 >= 10 и Age <= 5 минут"
        )
        logger.info(f"Тестовое сообщение отправлено боту {TARGET_BOT}")
    except Exception as e:
        logger.error(f"Ошибка при отправке тестового сообщения: {e}")
        return
    
    # Регистрируем обработчик событий
    @client.on(events.NewMessage(chats=list(SOURCE_CHANNELS.keys())))
    async def handler(event):
        try:
            # Получаем имя канала из нашего словаря
            channel_name = get_channel_name(event.chat_id)
            logger.info(f"Получено новое сообщение из канала {channel_name} (ID: {event.chat_id})")
            
            # Безопасно логируем текст сообщения
            text = getattr(event.message, 'text', None)
            logger.info(f"Текст сообщения: {safe_str(text)}")
            
            # Извлекаем контракты Solana из текста
            contracts = extract_solana_contracts(text)
            
            if contracts:
                logger.info(f"Найдены контракты: {contracts}")
                current_time = datetime.now().strftime("%H:%M:%S")
                
                for contract in contracts:
                    logger.info(f"Обрабатываем контракт: {contract}")
                    
                    # Проверяем, существует ли уже этот токен в базе
                    if contract in tokens_db:
                        # Если этот канал еще не зарегистрирован для этого токена
                        if channel_name not in tokens_db[contract]["channels"]:
                            tokens_db[contract]["channels"].append(channel_name)
                            tokens_db[contract]["channel_times"][channel_name] = current_time
                            tokens_db[contract]["channel_count"] += 1
                            
                            logger.info(f"Токен {contract} появился в новом канале. Всего каналов: {tokens_db[contract]['channel_count']}")
                            
                            # Обновляем эмодзи при каждом новом канале
                            emojis = get_channel_emojis_by_names(tokens_db[contract]["channels"])
                            tokens_db[contract]["emojis"] = emojis
                            logger.info(f"Обновлены эмодзи для токена {contract}: {emojis}")
                            
                            # Если токен в трекере, обновляем и там
                            if contract in tracker_db:
                                tracker_db[contract]["channels"] = tokens_db[contract]["channels"].copy()
                                tracker_db[contract]["channel_count"] = tokens_db[contract]["channel_count"]
                                tracker_db[contract]["channel_times"] = tokens_db[contract]["channel_times"].copy()
                                tracker_db[contract]["emojis"] = emojis
                                logger.info(f"Обновлены данные в трекере для токена {contract}: каналы={tokens_db[contract]['channel_count']}, эмодзи={emojis}")
                                
                                # Пересчитываем Rule1 для обновленного токена
                                rule1_passed = analyze_token_for_rule1(contract, tracker_db[contract])
                                save_tracker_database()
                                save_tracker_excel()
                            
                            # Если токен набрал нужное количество каналов и сообщение еще не отправлено в RadarDexBot
                            if tokens_db[contract]["channel_count"] >= MIN_SIGNALS and not tokens_db[contract]["message_sent"]:
                                # Вычисляем время от первого сигнала до текущего момента
                                time_diff = format_time_diff(tokens_db[contract]["first_seen"], datetime.now())
                                # Отправляем номер контракта и эмодзи в RadarDexBot (как было раньше)
                                try:
                                    sent_message = await client.send_message(
                                        TARGET_BOT,
                                        f"Контракт: {contract}\n{emojis} ({time_diff})"
                                    )
                                    tokens_db[contract]["message_sent"] = True
                                    tokens_db[contract]["message_id"] = sent_message.id
                                    logger.info(f"Номер контракта {contract} с эмодзи {emojis} отправлен боту {TARGET_BOT}, ID сообщения: {sent_message.id}")
                                    
                                    # Добавляем токен в базу отслеживания и проверяем Rule1
                                    rule1_passed = add_to_tracker(contract, tokens_db[contract], emojis)
                                    
                                    # ВАЖНО: Если токен прошел Rule1, отправляем его в MoonCryptoMonkey
                                    if rule1_passed:
                                        try:
                                            await client.send_message(
                                                MOON_CRYPTO_MONKEY_CHANNEL,
                                                f"🎯 Rule1 Passed\nКонтракт: {contract}\n{emojis}\n\nSignals15: {tracker_db[contract]['Signals15']}\nAge: {tracker_db[contract]['Age']:.2f} минут"
                                            )
                                            logger.info(f"Токен {contract} прошел Rule1 и отправлен в {MOON_CRYPTO_MONKEY_CHANNEL}")
                                        except Exception as e:
                                            logger.error(f"Ошибка при отправке в {MOON_CRYPTO_MONKEY_CHANNEL}: {e}")
                                except Exception as e:
                                    logger.error(f"Ошибка при отправке номера контракта: {e}")
                            
                            # Сохраняем базу данных после обновления
                            save_database()
                    else:
                        # Создаем новую запись о токене
                        tokens_db[contract] = {
                            "channels": [channel_name],
                            "channel_times": {channel_name: current_time},
                            "channel_count": 1,
                            "first_seen": current_time,
                            "message_sent": False,
                            "emojis": ""  # Добавляем поле для эмодзи
                        }
                        
                        logger.info(f"Новый токен {contract} добавлен. Обнаружен в 1 из {MIN_SIGNALS} необходимых каналов")
                        
                        # Проверяем, достаточно ли одного канала (если MIN_SIGNALS = 1)
                        if MIN_SIGNALS <= 1:
                            # Получаем тег текущего канала
                            channel_info = SOURCE_CHANNELS.get(event.chat_id)
                            if isinstance(channel_info, dict) and "tag" in channel_info:
                                tag = channel_info["tag"]
                                emoji = TAG_EMOJI_MAP.get(tag, "🍀")  # Используем клевер по умолчанию
                            else:
                                emoji = "🍀"  # Используем клевер по умолчанию
                            
                            # Отправляем номер контракта с эмодзи в RadarDexBot
                            try:
                                sent_message = await client.send_message(
                                    TARGET_BOT,
                                    f"Контракт: {contract}\n{emoji}"
                                )
                                tokens_db[contract]["message_sent"] = True
                                tokens_db[contract]["message_id"] = sent_message.id
                                tokens_db[contract]["emojis"] = emoji  # Сохраняем эмодзи в базе
                                logger.info(f"Номер контракта {contract} с эмодзи {emoji} отправлен боту {TARGET_BOT}, ID сообщения: {sent_message.id}")
                                
                                # Добавляем токен в базу отслеживания и проверяем Rule1
                                rule1_passed = add_to_tracker(contract, tokens_db[contract], emoji)
                                
                                # ВАЖНО: Если токен прошел Rule1, отправляем его в MoonCryptoMonkey
                                if rule1_passed:
                                    try:
                                        await client.send_message(
                                            MOON_CRYPTO_MONKEY_CHANNEL,
                                            f"🎯 Rule1 Passed\nКонтракт: {contract}\n{emoji}\n\nSignals15: {tracker_db[contract]['Signals15']}\nAge: {tracker_db[contract]['Age']:.2f} минут"
                                        )
                                        logger.info(f"Токен {contract} прошел Rule1 и отправлен в {MOON_CRYPTO_MONKEY_CHANNEL}")
                                    except Exception as e:
                                        logger.error(f"Ошибка при отправке в {MOON_CRYPTO_MONKEY_CHANNEL}: {e}")
                            except Exception as e:
                                logger.error(f"Ошибка при отправке номера контракта: {e}")                        
                        # Сохраняем базу данных после добавления нового токена
                        save_database()
            else:
                logger.info("Контракты Solana в сообщении не найдены")
                
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    # Запускаем периодическое сохранение базы данных
    async def periodic_save():
        while True:
            try:
                await asyncio.sleep(300)  # Каждые 5 минут
                save_database()
            except Exception as e:
                logger.error(f"Ошибка в задаче сохранения: {e}")
                await asyncio.sleep(60)  # Подождем минуту перед следующей попыткой
    
    # Запускаем фоновую задачу сохранения
    asyncio.ensure_future(periodic_save())
    
    logger.info(f"Бот запущен и отслеживает каналы: {len(SOURCE_CHANNELS)} шт. MIN_SIGNALS={MIN_SIGNALS}")
    logger.info(f"Rule1 фильтр для {MOON_CRYPTO_MONKEY_CHANNEL}: Signals15 >= 10 и Age <= 5 минут")
    
    # Держим соединение активным
    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка в основном цикле: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # Сохраняем базу данных перед выходом
        save_database()
        await client.disconnect()
        logger.info("Соединение закрыто")
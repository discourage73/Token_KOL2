from telethon import TelegramClient, events
import asyncio
import logging
import sys
import re
import json
import os
import time
import signal
from datetime import datetime
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
from config import TELEGRAM_TOKEN, logger, DEXSCREENER_API_URL, API_ID, API_HASH, TARGET_BOT

# Минимальное количество каналов для отправки сигнала
MIN_SIGNALS = 5  # Токен должен появиться минимум в 5 каналах

# Каналы для мониторинга (ID канала -> имя)
SOURCE_CHANNELS = {
    2234923591: "@Tanjirocall",
    1853203827:"@CryptoMafiaPlays",
    2121262250:"@DoctoreDegens",
    2015299550:"@hardy_trades",
    1975976600:"@smartmaxidegens",
    2054466090:"@casgem",
    2055101998:"@metagambler",
    1500214409:"@GemsmineEth",
    1794471884:"@MineGems",
    1662909092:"@QuartzETH",
    1603469217:"@ZionGems",
    2366686880:"@Ranma_Calls_Solana",
    1510769567:"@BatmanGamble",
    1818702441:"@michiosuzukiofsatoshicalls",
    1763265784:"@MarkDegens",
    1712900374:"@JeetyCall",
    1983450418:"@shitcoinneverland",
    2284638367:"@GemDynasty",
    1554385364:"@SultanPlays",
    1913209050:"@gigacalls",
    1869537526:"@POSEIDON_DEGEN_CALLS",
    1631609672:"@lowtaxcrypto",
    2088887132:"@sadcatgamble",
    1851567457:"@Insider_ECA",
    1756488143:"@lowtaxsolana",
    1883929251:"@gogetagambles",
    1964665140:"@joyboykingETH",
    2181107335:"@spacemanalphas",
    1597328515:"@KradsCalls",
    2000078706:"@NIKOLA_CALLS", 
    1601300719:"@piggiescall",
    2051055592:"@Mrbigbagcalls",
    1975392115:"@FrenzGems",
    1671616196:"@veigargambles",
    2219396784:"@Minion_Degen_Call",
    1628177089:"explorer_gems",
    2441888429:"BasedchadsGamble",
    1915368269:"NFG_GAMBLES",
    1294164024:"fortehculture",
    2144494116:"GM_Degencalls",
    2030684366:"uranusX100",
    1903316574:"x666calls",
    2350707840:"solanadaovolumealerts",
    2534842510:"@AlphAI_signals_sol_en"
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
        return SOURCE_CHANNELS[stripped_id]
    
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
    channel_name = SOURCE_CHANNELS.get(stripped_id)
    if channel_name:
        return channel_name
    else:
        # Если не нашли, возвращаем общее обозначение
        return f"@channel_{abs(stripped_id)}"

# Функция поиска контрактов Solana
def extract_solana_contracts(text):
    """Извлекает адреса контрактов Solana из текста."""
    if not text:
        return []
        
    # Паттерн для контрактов Solana: начинаются обычно с определенных букв и имеют 32-44 символа
    pattern = r"\b[a-zA-Z0-9]{32,44}\b"
    potential_contracts = re.findall(pattern, text)
    
    # Отфильтровываем кошельки разработчиков (обычно начинаются с определенных буквенных паттернов)
    filtered_contracts = []
    for contract in potential_contracts:
        # Токены Solana часто содержат слова pump, moon, или заканчиваются на pump
        if (contract.lower().endswith('pump') or 
            'pump' in contract.lower() or 
            'moon' in contract.lower() or
            # Добавьте другие характерные признаки контрактов Solana
            # которые отличают их от адресов кошельков
            re.match(r'^[0-9]', contract)):  # Многие контракты начинаются с цифры
            filtered_contracts.append(contract)
    
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
        else:
            logger.info("База данных отслеживаемых токенов не найдена, создаем новую")
            tracker_db = {}
    except Exception as e:
        logger.error(f"Ошибка при загрузке базы данных: {e}")
        tokens_db = {}
        tracker_db = {}

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

# Функция добавления токена в базу отслеживания
def add_to_tracker(contract, token_data):
    """Добавляет токен, достигший MIN_SIGNALS, в базу отслеживания."""
    try:
        # Проверяем, есть ли уже этот токен в базе
        if contract in tracker_db:
            logger.info(f"Токен {contract} уже есть в базе отслеживания")
            return
        
        # Формируем данные для трекера
        tracker_data = {
            'contract': contract,
            'first_seen': token_data.get('first_seen', ''),
            'signal_reached_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'channel_count': token_data.get('channel_count', 0),
            'channels': token_data.get('channels', []),
            'channel_times': token_data.get('channel_times', {})
        }
        
        # Добавляем в базу отслеживания
        tracker_db[contract] = tracker_data
        logger.info(f"Токен {contract} добавлен в базу отслеживания")
        
        # Сохраняем базы данных
        save_tracker_database()
        save_tracker_excel()
    except Exception as e:
        logger.error(f"Ошибка при добавлении токена в базу отслеживания: {e}")

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
            f"ℹ️ Минимальное количество каналов для сигнала: {MIN_SIGNALS}"
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
                            
                            # Если токен набрал нужное количество каналов или больше, и сообщение еще не отправлялось
                            if tokens_db[contract]["channel_count"] >= MIN_SIGNALS and not tokens_db[contract]["message_sent"]:
                                # Отправляем только номер контракта
                                try:
                                    await client.send_message(
                                        TARGET_BOT,
                                        f"Контракт: {contract}"
                                    )
                                    tokens_db[contract]["message_sent"] = True
                                    logger.info(f"Номер контракта {contract} отправлен боту {TARGET_BOT}")
                                    
                                    # Добавляем токен в базу отслеживания
                                    add_to_tracker(contract, tokens_db[contract])
                                except Exception as e:
                                    logger.error(f"Ошибка при отправке номера контракта: {e}")
                            else:
                                logger.info(f"Токен {contract} обнаружен в {tokens_db[contract]['channel_count']} из {MIN_SIGNALS} необходимых каналов")
                            
                            # Сохраняем базу данных после обновления
                            save_database()
                    else:
                        # Создаем новую запись о токене
                        tokens_db[contract] = {
                            "channels": [channel_name],
                            "channel_times": {channel_name: current_time},
                            "channel_count": 1,
                            "first_seen": current_time,
                            "message_sent": False
                        }
                        
                        logger.info(f"Новый токен {contract} добавлен. Обнаружен в 1 из {MIN_SIGNALS} необходимых каналов")
                        
                        # Проверяем, достаточно ли одного канала (если MIN_SIGNALS = 1)
                        if MIN_SIGNALS <= 1:
                            # Отправляем только номер контракта
                            try:
                                await client.send_message(
                                    TARGET_BOT,
                                    f"Контракт: {contract}"
                                )
                                tokens_db[contract]["message_sent"] = True
                                logger.info(f"Номер контракта {contract} отправлен боту {TARGET_BOT}")
                                
                                # Добавляем токен в базу отслеживания
                                add_to_tracker(contract, tokens_db[contract])
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

# Обработчик сигнала прерывания
def signal_handler(sig, frame):
    logger.info("Получен сигнал прерывания, выполняется выход...")
    save_database()  # Сохраняем базу данных перед выходом
    sys.exit(0)

if __name__ == "__main__":
    try:
        # Регистрируем обработчик прерывания
        signal.signal(signal.SIGINT, signal_handler)
        
        # Решение проблемы с event loop в новых версиях Python
        if sys.version_info >= (3, 10):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        # Запускаем бота с возможностью перезапуска
        while True:
            try:
                # Используем новый event loop для каждого запуска
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(main())
                break  # Выход из цикла при нормальном завершении
            except KeyboardInterrupt:
                logger.info("Бот остановлен пользователем")
                save_database()
                break
            except Exception as e:
                logger.error(f"Критическая ошибка, перезапуск через 10 секунд: {e}")
                import traceback
                logger.error(traceback.format_exc())
                save_database()
                time.sleep(10)  # Ждем 10 секунд перед перезапуском
    except Exception as e:
        print(f"Критическая ошибка при запуске: {e}")
        import traceback
        print(traceback.format_exc())
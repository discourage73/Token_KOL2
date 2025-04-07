from telethon import TelegramClient, events
import asyncio
import logging
import sys
import re
import os
import time
import signal
import shutil
from datetime import datetime

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

# Импортируем конфигурацию
try:
    from config import (API_ID, API_HASH, SOURCE_BOTS, TARGET_CHANNEL, 
                        NEWS_CHANNELS, NEWS_TARGET_CHANNEL, logger)
    # Используем логгер из config.py
    USING_CONFIG_LOGGER = True
except ImportError:
    # Значения для независимого запуска (замените на свои!)
    API_ID = 25308063
    API_HASH = "458e1315175e0103f19d925204b690a5"
    SOURCE_BOTS = ["AlphAI_Signals_Bot", "ray_aqua_bot"]
    TARGET_CHANNEL = "cringemonke"
    NEWS_CHANNELS = ["cointelegraph", "coindesk", "WatcherGuru"]
    NEWS_TARGET_CHANNEL = "MoonCryptoMonkey"
    
    USING_CONFIG_LOGGER = False
    # Создаем директорию для логов, если она не существует
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f"logs/forwarder_{datetime.now().strftime('%Y%m%d-%H%M%S')}.log", encoding='utf-8'),
        ]
    )

    # Добавляем собственный обработчик для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger = logging.getLogger(__name__)
    logger.addHandler(console_handler)
    
    logger.warning("Не удалось импортировать config.py, используются встроенные значения")

# Хранилище для исключения дубликатов сообщений
message_hashes = set()
MAX_HASH_CACHE = 1000  # Максимальное количество хешей в кэше

# Глобальная переменная для отслеживания статуса работы
is_running = True


def hash_message(message):
    """Создает хеш сообщения для определения дубликатов."""
    if hasattr(message, 'text') and message.text:
        # Используем текст сообщения и время для хеширования
        return hash(f"{message.text}{message.date}")
    elif hasattr(message, 'message') and message.message:
        # Для случаев, когда сообщение вложено
        return hash(f"{message.message}{message.date}")
    else:
        # Если нет текста, используем только время
        return hash(f"{message.date}")


async def extract_and_format_alphai_data(message):
    """
    Извлекает и форматирует ключевую информацию из сообщений AlphAI_Signals_Bot.
    Возвращает отформатированный текст или None, если данные не найдены.
    """
    if not hasattr(message, 'text') or not message.text:
        return None
        
    text = message.text
    
    # Проверяем, что это сообщение от AlphAI_Signals_Bot с KOL Calls
    if "**KOL Calls**" not in text and "KOL Call:" not in text:
        return None
        
    # Пробуем извлечь основные данные с помощью регулярных выражений
    
    # Извлекаем CA (Contract Address)
    ca_match = re.search(r'CA:[\s`]*([a-zA-Z0-9]+)', text)
    ca = ca_match.group(1) if ca_match else "N/A"
    
    # Извлекаем Tag
    tag_match = re.search(r'Tag:([^\n]+)', text)
    tag = tag_match.group(1).strip() if tag_match else "N/A"
    
    # Извлекаем Market Cap
    mcap_match = re.search(r'Market Cap:[\s]*(\$[0-9.]+[KMB]?)', text)
    mcap = mcap_match.group(1) if mcap_match else "N/A"
    
    # Извлекаем Liquidity
    liq_match = re.search(r'Liq:[\s]*(\$[0-9.]+[KMB]?)', text)
    liq = liq_match.group(1) if liq_match else "N/A"
    
    # Извлекаем Holders
    holders_match = re.search(r'Holders:[\s]*([0-9.]+[KMB]?)', text)
    holders = holders_match.group(1) if holders_match else "N/A"
    
    # Извлекаем Score
    score_match = re.search(r'Score:[\s]*([0-9]+/[0-9]+)', text)
    score = score_match.group(1) if score_match else "N/A"
    
    # Извлекаем Age
    age_match = re.search(r'Age:[\s]*([^\n]+)', text)
    age = age_match.group(1).strip() if age_match else "N/A"
    
    # Извлекаем Smart Money Holders
    sm_match = re.search(r'([0-9]+)[\s]*Smart Money Holders', text)
    smart_money = sm_match.group(1) if sm_match else "N/A"
    
    # Извлекаем информацию о Permission и Top Holders
    permission_match = re.search(r'(Permission Revoked[^0-9]*Top 10 Holders:[^%]*%)', text)
    permissions = permission_match.group(1).strip() if permission_match else "N/A"
    
    # Извлекаем KOL Call и информацию о просмотрах
    kol_match = re.search(r'KOL Call:[\s]*([0-9]+)[\s]*\|[\s]*Fans:[\s]*([0-9.]+[KMB]?)[\s]*\|[\s]*Views:[\s]*([0-9.]+[KMB]?)', text)
    if kol_match:
        kol_count = kol_match.group(1)
        fans = kol_match.group(2)
        views = kol_match.group(3)
    else:
        kol_count = "N/A"
        fans = "N/A"
        views = "N/A"
    
    # Формируем сокращенное сообщение с важной информацией
    formatted_text = f"""CA: {ca}
Tag: {tag}
Market Cap: {mcap}
💧 Liq: {liq}
👥 Holders: {holders} | Score: {score}
⏰ Age: {age}
🧠 {smart_money} Smart Money Holders
{permissions}
KOL Call: {kol_count} | Fans: {fans} | Views: {views}"""

    return formatted_text


async def safe_forward_message(client, message, target):
    """Обрабатывает сообщения от источников и отправляет в целевой канал."""
    try:
        # Создаем хеш сообщения для проверки дубликатов
        msg_hash = hash_message(message)
        
        # Проверяем, не является ли сообщение дубликатом
        if msg_hash in message_hashes:
            logger.info(f"Пропуск дубликата сообщения: {message.id}")
            return None
        
        # Добавляем хеш в кэш и очищаем кэш, если он слишком большой
        message_hashes.add(msg_hash)
        if len(message_hashes) > MAX_HASH_CACHE:
            # Удаляем самый старый хеш (итерация по set непредсказуема, но это не критично)
            message_hashes.pop()
        
        # Получаем источник сообщения
        source = None
        if hasattr(message.chat, 'username'):
            source = message.chat.username
        
        # Обрабатываем сообщение в зависимости от источника
        text_to_send = None
        
        # Обработка сообщений от AlphAI_Signals_Bot
        if source == "AlphAI_Signals_Bot":
            logger.info(f"Обработка сообщения от AlphAI_Signals_Bot (ID: {message.id})")
            # Извлекаем только нужные данные
            text_to_send = await extract_and_format_alphai_data(message)
            
            if not text_to_send:
                logger.info(f"Сообщение от AlphAI_Signals_Bot не содержит нужных данных, пропускаем")
                return None
        
        # Обработка сообщений от ray_aqua_bot - просто копируем текст
        elif source == "ray_aqua_bot":
            logger.info(f"Обработка сообщения от ray_aqua_bot (ID: {message.id})")
            if hasattr(message, 'text') and message.text:
                text_to_send = message.text
            elif hasattr(message, 'caption') and message.caption:
                text_to_send = message.caption
        
        # Если текст для отправки не был определен, пропускаем сообщение
        if not text_to_send:
            logger.info(f"Не удалось извлечь текст для отправки из сообщения {message.id}")
            return None
        
        # Отправляем подготовленный текст
        logger.info(f"Отправка обработанного текста в канал @{target}")
        result = await client.send_message(
            target,
            text_to_send,
            parse_mode=None,  # Сохраняем исходное форматирование
            link_preview=True  # Сохраняем превью ссылок
        )
        
        logger.info(f"Текст успешно отправлен, новый ID: {result.id if result else 'N/A'}")
        
        # Добавляем небольшую задержку после отправки
        await asyncio.sleep(1)
        
        return result
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения {message.id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def copy_news_message(client, message, target):
    """Копирует сообщение из новостного канала вместе с медиафайлами, сохраняя форматирование."""
    try:
        # Создаем хеш сообщения для проверки дубликатов
        msg_hash = hash_message(message)
        
        # Проверяем, не является ли сообщение дубликатом
        if msg_hash in message_hashes:
            logger.info(f"Пропуск дубликата новостного сообщения: {message.id}")
            return None
        
        # Добавляем хеш в кэш и очищаем кэш, если он слишком большой
        message_hashes.add(msg_hash)
        if len(message_hashes) > MAX_HASH_CACHE:
            # Удаляем самый старый хеш (итерация по set непредсказуема, но это не критично)
            message_hashes.pop()
        
        # Получаем имя источника
        source_name = message.chat.username if hasattr(message.chat, 'username') else f"chat_{message.chat_id}"
        logger.info(f"Копирование новостного сообщения из {source_name} (ID: {message.id})")
        
        # Вместо обработки, пересылаем сообщение напрямую с сохранением форматирования
        # Это обеспечит точное копирование форматирования сообщения и медиа
        try:
            result = await client.forward_messages(target, message)
            logger.info(f"Сообщение успешно переслано в {target}, новый ID: {result[0].id if result else 'N/A'}")
            return result
        except Exception as e:
            logger.error(f"Ошибка при прямой пересылке сообщения: {e}")
            # Если прямая пересылка не удалась, попробуем другой способ
            logger.info("Попытка альтернативного копирования сообщения...")
        
        # Извлекаем текст сообщения из разных возможных полей
        text = None
        if hasattr(message, 'message') and message.message:
            text = message.message
        elif hasattr(message, 'text') and message.text:
            text = message.text
        elif hasattr(message, 'caption') and message.caption:
            text = message.caption
        
        # Проверяем наличие медиа
        has_media = False
        
        # Создаем временную директорию для медиафайлов, если ее нет
        if not os.path.exists('temp'):
            os.makedirs('temp')
        
        # Путь к медиафайлу, если он будет скачан
        file_path = None
        
        # Проверяем различные типы медиа
        if hasattr(message, 'photo') and message.photo:
            has_media = True
            try:
                file_path = await message.download_media(file="temp/")
                logger.info(f"Скачано фото из сообщения {message.id}: {file_path}")
            except Exception as e:
                logger.error(f"Ошибка при скачивании фото: {e}")
                has_media = False
                
        elif hasattr(message, 'video') and message.video:
            has_media = True
            try:
                file_path = await message.download_media(file="temp/")
                logger.info(f"Скачано видео из сообщения {message.id}: {file_path}")
            except Exception as e:
                logger.error(f"Ошибка при скачивании видео: {e}")
                has_media = False
                
        elif hasattr(message, 'document') and message.document:
            has_media = True
            try:
                file_path = await message.download_media(file="temp/")
                logger.info(f"Скачан документ из сообщения {message.id}: {file_path}")
            except Exception as e:
                logger.error(f"Ошибка при скачивании документа: {e}")
                has_media = False
        
        # Теперь отправляем сообщение с медиа или без
        result = None
        
        if has_media and file_path:
            # Отправляем медиафайл с подписью (если есть текст)
            try:
                result = await client.send_file(
                    target,
                    file_path,
                    caption=text if text else None,
                    parse_mode='html'  # Используем HTML для сохранения форматирования
                )
                logger.info(f"Отправлено сообщение с медиа в {target}, новый ID: {result.id if result else 'N/A'}")
            except Exception as e:
                logger.error(f"Ошибка при отправке медиафайла: {e}")
                # В случае ошибки, попробуем отправить только текст
                if text:
                    try:
                        result = await client.send_message(
                            target,
                            text,
                            parse_mode='html'
                        )
                        logger.info(f"Отправлен только текст (без медиа) в {target}")
                    except Exception as text_error:
                        logger.error(f"Не удалось отправить даже текст: {text_error}")
            
            # Удаляем временный файл
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Удален временный файл: {file_path}")
            except Exception as e:
                logger.error(f"Ошибка при удалении временного файла: {e}")
                
        elif text:
            # Если нет медиа, но есть текст, отправляем только текст
            try:
                result = await client.send_message(
                    target,
                    text,
                    parse_mode='html'  # Используем HTML для сохранения форматирования
                )
                logger.info(f"Отправлено текстовое сообщение в {target}, новый ID: {result.id if result else 'N/A'}")
            except Exception as e:
                logger.error(f"Ошибка при отправке текста: {e}")
        else:
            # Если нет ни медиа, ни текста, логируем это
            logger.warning(f"Сообщение {message.id} не содержит ни медиа, ни текста. Пропускаем.")
            return None
        
        # Добавляем небольшую задержку после отправки
        await asyncio.sleep(1)
        
        return result
    except Exception as e:
        logger.error(f"Ошибка при копировании новостного сообщения {message.id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def start_forwarding():
    """Основная функция для запуска копирования сообщений."""
    # Явный вывод о запуске программы
    print("Сервис копирования сообщений запущен!")
    logger.info("Сервис копирования сообщений запущен!")
    
    # Создаем директорию для временных файлов, если ее нет
    if not os.path.exists('temp'):
        os.makedirs('temp')
        logger.info("Создана директория для временных файлов")
    else:
        # Очищаем директорию от старых файлов
        try:
            for file in os.listdir('temp'):
                file_path = os.path.join('temp', file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    logger.error(f"Ошибка при удалении файла {file_path}: {e}")
            logger.info("Временная директория очищена")
        except Exception as e:
            logger.error(f"Ошибка при очистке временной директории: {e}")
    
    # Подключаемся к Telegram с улучшенными параметрами
    client = TelegramClient(
        'forwarder_session', 
        API_ID, 
        API_HASH,
        connection_retries=10,
        retry_delay=5,
        auto_reconnect=True,
        request_retries=10
    )
    
    await client.start()
    
    logger.info("Подключение к Telegram успешно установлено")
    
    # Отправляем тестовое сообщение в канал для ботов
    try:
        await client.send_message(
            TARGET_CHANNEL, 
            f"🔄 Сервис копирования текстов сообщений запущен и отслеживает боты: {', '.join(['@' + bot for bot in SOURCE_BOTS])}"
        )
        logger.info(f"Тестовое сообщение отправлено в канал @{TARGET_CHANNEL}")
    except Exception as e:
        logger.error(f"Ошибка при отправке тестового сообщения в канал ботов: {e}")
    
    # Отправляем тестовое сообщение в канал для новостей
    try:
        await client.send_message(
            NEWS_TARGET_CHANNEL, 
            f"🔄 Сервис копирования новостей запущен и отслеживает каналы: {', '.join(['@' + channel for channel in NEWS_CHANNELS])}"
        )
        logger.info(f"Тестовое сообщение отправлено в канал @{NEWS_TARGET_CHANNEL}")
    except Exception as e:
        logger.error(f"Ошибка при отправке тестового сообщения в канал новостей: {e}")
    
    # Получаем идентификаторы ботов
    bot_entities = []
    for bot_username in SOURCE_BOTS:
        try:
            entity = await client.get_entity(bot_username)
            bot_entities.append(entity)
            logger.info(f"Бот @{bot_username} найден, ID: {entity.id}")
        except Exception as e:
            logger.error(f"Ошибка при получении сущности бота @{bot_username}: {e}")
    
    # Получаем идентификаторы новостных каналов
    news_entities = []
    for channel_username in NEWS_CHANNELS:
        try:
            entity = await client.get_entity(channel_username)
            news_entities.append(entity)
            logger.info(f"Канал @{channel_username} найден, ID: {entity.id}")
        except Exception as e:
            logger.error(f"Ошибка при получении сущности канала @{channel_username}: {e}")
    
    # Регистрируем обработчик событий для сообщений от ботов
    @client.on(events.NewMessage(from_users=bot_entities))
    async def bot_handler(event):
        global is_running
        if not is_running:
            return  # Прекращаем обработку, если получен сигнал остановки
            
        try:
            # Получаем имя источника
            source_name = event.chat.username if hasattr(event.chat, 'username') else f"chat_{event.chat_id}"
            logger.info(f"Получено новое сообщение от бота @{source_name} (ID: {event.message.id})")
            
            # Обрабатываем и отправляем сообщение
            await safe_forward_message(client, event.message, TARGET_CHANNEL)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения от бота: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    # Регистрируем обработчик событий для сообщений из новостных каналов
    @client.on(events.NewMessage(from_users=news_entities))
    async def news_handler(event):
        global is_running
        if not is_running:
            return  # Прекращаем обработку, если получен сигнал остановки
            
        try:
            # Получаем имя источника
            source_name = event.chat.username if hasattr(event.chat, 'username') else f"chat_{event.chat_id}"
            logger.info(f"Получено новое сообщение из новостного канала @{source_name} (ID: {event.message.id})")
            
            # Копируем сообщение в целевой канал новостей
            await copy_news_message(client, event.message, NEWS_TARGET_CHANNEL)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке новостного сообщения: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    # Держим соединение активным
    try:
        total_sources = len(bot_entities) + len(news_entities)
        logger.info(f"Ожидание новых сообщений от {total_sources} источников...")
        while is_running:
            await asyncio.sleep(1)  # Проверяем состояние is_running каждую секунду
        
    except KeyboardInterrupt:
        logger.info("Сервис остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка в основном цикле: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # Очищаем временные файлы перед выходом
        try:
            if os.path.exists('temp'):
                for file in os.listdir('temp'):
                    file_path = os.path.join('temp', file)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                    except Exception as e:
                        logger.error(f"Ошибка при удалении файла {file_path}: {e}")
            logger.info("Временная директория очищена перед выходом")
        except Exception as e:
            logger.error(f"Ошибка при очистке временной директории: {e}")
            
        await client.disconnect()
        logger.info("Соединение закрыто")


# Обработчик сигнала прерывания
def signal_handler(sig, frame):
    global is_running
    logger.info("Получен сигнал прерывания, выполняется выход...")
    print("Остановка сервиса копирования сообщений...")
    
    # Устанавливаем флаг для остановки основного цикла
    is_running = False


async def main():
    """Точка входа для асинхронного запуска."""
    # Запускаем копирование сообщений
    await start_forwarding()


if __name__ == "__main__":
    try:
        # Регистрируем обработчик прерывания
        signal.signal(signal.SIGINT, signal_handler)
        
        # Решение проблемы с event loop в новых версиях Python
        if sys.version_info >= (3, 10):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        # Запускаем сервис с возможностью перезапуска
        while True:
            try:
                # Сбрасываем флаг при перезапуске
                is_running = True
                
                # Используем новый event loop для каждого запуска
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(main())
                
                # Если сервис был остановлен штатно, выходим из цикла
                if not is_running:
                    break
                    
            except KeyboardInterrupt:
                logger.info("Сервис остановлен пользователем")
                break
            except Exception as e:
                logger.error(f"Критическая ошибка, перезапуск через 10 секунд: {e}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(10)  # Ждем 10 секунд перед перезапуском
    except Exception as e:
        print(f"Критическая ошибка при запуске: {e}")
        import traceback
        print(traceback.format_exc())
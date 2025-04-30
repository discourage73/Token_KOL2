from telethon import TelegramClient, events
import asyncio
import logging
import sys
import re
import os
import time
import signal
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
    SOURCE_BOTS = ["TheMobyBot", "ray_cyan_bot"]
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

# Глобальная переменная для отслеживания статуса работы
is_running = True

async def extract_and_format_ray_cyan_data(message):
    """
    Извлекает и форматирует ключевую информацию из сообщений ray_cyan_bot.
    Возвращает отформатированный текст с только необходимой информацией.
    """
    if not hasattr(message, 'text') or not message.text:
        return None
        
    text = message.text
    
    # Проверяем, что это сообщение о покупке токена
    if "BUY" not in text:
        # Если это не сообщение о покупке, возвращаем None, чтобы использовалась стандартная обработка
        return None
    
    try:
        # Извлекаем название токена
        buy_match = re.search(r'BUY ([^\s\(\)]+)', text)
        token_name = buy_match.group(1) if buy_match else "UNKNOWN"
        
        # ИСПРАВЛЕНИЕ: Правильно извлекаем платформу
        # Вначале ищем в строке вида "BUY TOKEN on PLATFORM"
        platform_match = re.search(r'BUY [^\s\(\)]+ on ([A-Z\s]+)', text)
        platform = platform_match.group(1).strip() if platform_match else ""
        
        # Если не нашли или платформа является точно PumpSwap/PUMP FUN, то оставляем пустой строкой 
        # (по требованию: "можно вообще удалить и не писать")
        if not platform or platform == "PumpSwap" or platform == "PUMP FUN":
            platform = ""
        else:
            platform = f" on {platform}"
        
        # Извлекаем процент и числа
        percent_match = re.search(r'([0-9.]+%) ([0-9,]+)/([0-9,]+)', text)
        percent = percent_match.group(1) if percent_match else ""
        numbers = f"{percent_match.group(2)}/{percent_match.group(3)}" if percent_match else ""
        
        # Извлекаем информацию о свопе SOL
        swap_match = re.search(r'swapped\s+([0-9.]+)\s+SOL', text)
        sol_amount = swap_match.group(1) if swap_match else ""
        
        # Если не нашли в первом регулярном выражении, ищем другой формат
        if not sol_amount:
            alt_swap_match = re.search(r'([0-9.]+)\s*SOL for', text)
            sol_amount = alt_swap_match.group(1) if alt_swap_match else ""
        
        # Извлекаем Market Cap (MC)
        mc_match = re.search(r'MC:?\s*(\$[0-9.]+[KMB]?)', text)
        mc_value = mc_match.group(1) if mc_match else ""
        
        # Извлекаем информацию о времени (Seen)
        seen_match = re.search(r'Seen:?\s*([0-9]+[mhd][:\s]*[0-9]*[mhd]?)', text)
        seen_value = seen_match.group(1) if seen_match else ""
        
        # ИСПРАВЛЕНИЕ: Лучший способ извлечь адрес контракта
        # 1. Сначала ищем адрес в последней строке, где только буквы и цифры
        lines = text.split('\n')
        address = ""
        
        # Ищем в обратном порядке (снизу вверх)
        for line in reversed(lines):
            line = line.strip()
            # Проверяем, что строка содержит только буквы и цифры и имеет нужную длину
            if re.match(r"^[A-Za-z0-9]{32,44}$", line):
                address = line
                break
        
        # 2. Если не нашли в отдельной строке, ищем любой подходящий адрес в тексте
        if not address:
            # Общий поиск адреса в любой части текста
            addr_matches = re.findall(r'[A-Za-z0-9]{32,44}', text)
            if addr_matches:
                # Берем последний найденный адрес (обычно самый релевантный)
                address = addr_matches[-1]
        
        # 3. Если всё еще не нашли, пробуем специфичные для PumpFun форматы
        if not address:
            # Ищем адреса в формате токенов с "pump" в конце
            pump_addr_match = re.search(r'([A-Za-z0-9]{6,}[A-Za-z0-9]*pump)["\s\)]', text)
            address = pump_addr_match.group(1) if pump_addr_match else ""
            
            # Если не нашли по шаблону выше, ищем в URL ссылках
            if not address:
                addr_url_match = re.search(r'/token/([A-Za-z0-9]{6,}[A-Za-z0-9]*pump)', text)
                address = addr_url_match.group(1) if addr_url_match else ""
        
        # Логируем найденный адрес для отладки - ИСПРАВЛЕНО
        logger.info("Извлеченный адрес контракта: {}".format(address))
        
        # Проверяем, удалось ли извлечь адрес
        if not address:
            logger.warning("Не удалось извлечь адрес контракта из сообщения")
        
        # Формируем дополнительную информацию
        additional_info = ""
        if mc_value:
            additional_info += f" | MC: {mc_value}"
        if seen_value:
            additional_info += f" | Seen: {seen_value}"
        
        # Форматируем сообщение согласно требованиям
        formatted_text = f"""🟢 BUY {token_name}{platform}

🔹 {percent} {numbers} swapped {sol_amount} SOL{additional_info}

{address}"""

        return formatted_text
    except Exception as e:
        logger.error("Ошибка при извлечении данных из сообщения ray_cyan_bot: {}".format(e))
        import traceback
        logger.error(traceback.format_exc())
        return None


async def extract_and_format_whale_alerts(message):
    """
    Извлекает и форматирует информацию из сообщений о китах (Whale Alerts).
    Возвращает отформатированный текст с только необходимой информацией.
    Обрабатывает только сообщения с "just bought", игнорирует "just sold".
    """
    if not hasattr(message, 'text') or not message.text:
        return None
        
    text = message.text
    
    # Проверяем, что это сообщение о покупке кита (только "just bought")
    if "New Token Whale Alert" in text and "just bought" in text and "just sold" not in text:
        try:
            # Извлекаем основную информацию о покупке кита (с учетом разных форматов из скриншотов)
            whale_info_match = re.search(r'(A .+? Whale just bought \$[\d.]+[KMB]? of .+?)(?=\(|\n|$)', text)
            whale_info = whale_info_match.group(1).strip() if whale_info_match else ""
            
            # Если не нашли информацию о ките, значит, это не интересующее нас сообщение
            if not whale_info:
                return None
            
            # Проверяем, есть ли "just sold" в тексте сообщения (дополнительная проверка)
            if "just sold" in whale_info:
                return None
                
            # Извлекаем информацию о маркет капе
            mc_match = re.search(r'\(MC:?\s*\$([\d.]+[KMB]?)\)', text)
            mc_info = f"(MC: ${mc_match.group(1)})" if mc_match else ""
            
            # Извлекаем адрес контракта - ищем длинную строку из букв и цифр
            contract_match = re.search(r'([A-Za-z0-9]{30,})', text)
            contract_address = contract_match.group(1) if contract_match else ""
            
            # Форматируем сообщение по требуемому шаблону
            formatted_text = f"""New Token Whale Alert
🟢 {whale_info} {mc_info}

{contract_address}"""
            
            return formatted_text
            
        except Exception as e:
            logger.error("Ошибка при извлечении данных из сообщения о ките: {}".format(e))
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    # Если это не сообщение о покупке кита, возвращаем None
    return None

async def start_forwarding():
    """Основная функция для запуска пересылки сообщений."""
    print("Сервис пересылки сообщений запущен!")
    logger.info("Сервис пересылки сообщений запущен!")
    
    # Подключаемся к Telegram
    client = TelegramClient('forwarder_session', API_ID, API_HASH)
    await client.start()
    
    logger.info("Подключение к Telegram установлено")
    
    # Отправляем приветственные сообщения
    try:
        # Отправляем в основной канал для TheMobyBot
        await client.send_message(
            TARGET_CHANNEL, 
            f"🔄 Сервис пересылки сообщений запущен и отслеживает бота: @TheMobyBot"
        )
        logger.info("Приветственное сообщение отправлено в канал @{}".format(TARGET_CHANNEL))
        
        # Отправляем в канал для ray_cyan_bot
        await client.send_message(
            "cringemonke2", 
            f"🔄 Сервис пересылки сообщений запущен и отслеживает бота: @ray_cyan_bot"
        )
        logger.info("Приветственное сообщение отправлено в канал @cringemonke2")
        
        # Отправляем в канал для новостей
        news_channels_list = ", ".join([f"@{channel}" for channel in NEWS_CHANNELS])
        await client.send_message(
            NEWS_TARGET_CHANNEL, 
            f"🔄 Сервис пересылки новостей запущен и отслеживает каналы: {news_channels_list}"
        )
        logger.info("Приветственное сообщение отправлено в канал @{}".format(NEWS_TARGET_CHANNEL))
    except Exception as e:
        logger.error("Ошибка при отправке приветственного сообщения: {}".format(e))
    
    # Регистрируем обработчик для всех входящих сообщений
    @client.on(events.NewMessage())
    async def handler(event):
        if not is_running:
            return
            
        try:
            # Получаем имя отправителя
            sender = event.sender
            sender_username = sender.username if sender else "Unknown"
            
            # Пересылка от TheMobyBot в TARGET_CHANNEL
            if sender_username == "TheMobyBot":
                logger.info("Получено сообщение от @TheMobyBot")
                
                # Пересылаем текст сообщения в целевой канал
                if hasattr(event.message, 'text') and event.message.text:
                    # ИСПРАВЛЕНИЕ: Проверяем сначала, содержит ли сообщение "just sold"
                    # Если да, то полностью игнорируем его
                    if "just sold" in event.message.text:
                        logger.info("Сообщение содержит 'just sold', игнорируем")
                        return
                    
                    # Проверяем, является ли сообщение сообщением о ките
                    formatted_text = await extract_and_format_whale_alerts(event.message)
                    
                    if formatted_text:
                        logger.info("Обнаружено сообщение о ките, применяем форматирование")
                    else:
                        logger.info("Сообщение не распознано как сообщение о ките, пересылаем как есть")
                    
                    # Если не удалось отформатировать или это не сообщение о ките, используем оригинальный текст
                    text_to_send = formatted_text if formatted_text else event.message.text
                    
                    try:
                        await client.send_message(TARGET_CHANNEL, text_to_send)
                        logger.info("Сообщение от @TheMobyBot переслано в @{}".format(TARGET_CHANNEL))
                    except Exception as e:
                        logger.error("Ошибка при пересылке сообщения от TheMobyBot: {}".format(e))
                        import traceback
                        logger.error(traceback.format_exc())
            
            # Пересылка от ray_cyan_bot в cringemonke2
            elif sender_username == "ray_cyan_bot":
                logger.info("Получено сообщение от @ray_cyan_bot")
                
                # Применяем фильтр и форматирование для ray_cyan_bot
                if hasattr(event.message, 'text') and event.message.text:
                    formatted_text = await extract_and_format_ray_cyan_data(event.message)
                    
                    # Если не удалось отформатировать, используем оригинальный текст
                    text_to_send = formatted_text if formatted_text else event.message.text
                    
                    try:
                        await client.send_message("cringemonke2", text_to_send)
                        logger.info("Сообщение от @ray_cyan_bot переслано в @cringemonke2")
                    except Exception as e:
                        logger.error("Ошибка при пересылке сообщения от ray_cyan_bot: {}".format(e))
                        import traceback
                        logger.error(traceback.format_exc())
            
            # Пересылка из новостных каналов
            elif sender_username in NEWS_CHANNELS:
                logger.info("Получено сообщение от новостного канала @{}".format(sender_username))
                
                # Пересылаем текст в канал для новостей
                if hasattr(event.message, 'text') and event.message.text:
                    try:
                        await client.send_message(NEWS_TARGET_CHANNEL, event.message.text)
                        logger.info("Новость от @{} переслана в @{}".format(sender_username, NEWS_TARGET_CHANNEL))
                    except Exception as e:
                        logger.error("Ошибка при пересылке новости: {}".format(e))
                        import traceback
                        logger.error(traceback.format_exc())
        except Exception as e:
            logger.error("Ошибка при обработке сообщения: {}".format(e))
            import traceback
            logger.error(traceback.format_exc())
    
    # Держим соединение активным до получения сигнала остановки
    try:
        logger.info("Ожидание сообщений от ботов и каналов...")
        while is_running:
            await asyncio.sleep(60)
            logger.info("Сервис активен, ожидание сообщений...")
    except KeyboardInterrupt:
        logger.info("Сервис остановлен пользователем")
    except Exception as e:
        logger.error("Ошибка в основном цикле: {}".format(e))
        import traceback
        logger.error(traceback.format_exc())
    finally:
        await client.disconnect()
        logger.info("Соединение закрыто")

# Обработчик сигнала прерывания
def signal_handler(sig, frame):
    global is_running
    logger.info("Получен сигнал прерывания, выполняется выход...")
    print("Остановка сервиса пересылки сообщений...")
    is_running = False

if __name__ == "__main__":
    try:
        # Регистрируем обработчик прерывания
        signal.signal(signal.SIGINT, signal_handler)
        
        # Решение проблемы с event loop в новых версиях Python
        if sys.version_info >= (3, 10):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        # Запускаем сервис
        asyncio.run(start_forwarding())
    except Exception as e:
        print("Критическая ошибка при запуске: {}".format(e))
        import traceback
        print(traceback.format_exc())
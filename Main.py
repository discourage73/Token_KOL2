import logging
import sys
import os
import signal
import time
import asyncio
import subprocess

# Создаем директорию для логов, если она не существует
if not os.path.exists('logs'):
    os.makedirs('logs')

# Получаем текущую временную метку для имен файлов
timestamp = time.strftime("%Y%m%d-%H%M%S")

# Глобальный уровень логирования: можно изменить на INFO для более подробных логов
LOG_LEVEL = "WARNING"  # Доступные варианты: DEBUG, INFO, WARNING, ERROR, CRITICAL

# Настройка логирования
# Файловый обработчик для детальных логов
file_handler = logging.FileHandler(f'logs/main_{timestamp}.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)  # В файл пишем все информационные сообщения
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Консольный обработчик только для важных сообщений
console_handler = logging.StreamHandler()
console_handler.setLevel(getattr(logging, LOG_LEVEL))
console_formatter = logging.Formatter('%(message)s')
console_handler.setFormatter(console_formatter)

# Основной логгер
logger = logging.getLogger("main")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Запретить распространение логов в родительский логгер
logger.propagate = False

# Процессы и задачи для управления компонентами
bot_process = None
tracker_task = None
forwarder_task = None
stop_event = asyncio.Event()

def configure_root_logger():
    """Настраивает корневой логгер для управления всеми модулями."""
    # Настройка корневого логгера
    root_logger = logging.getLogger()
    
    # Удаляем существующие обработчики
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Файловый обработчик для всех логов
    all_log_file = f'logs/all_components_{timestamp}.log'
    all_handler = logging.FileHandler(all_log_file, encoding='utf-8')
    all_handler.setLevel(logging.INFO)
    all_handler.setFormatter(file_formatter)
    
    # Добавляем обработчик
    root_logger.addHandler(all_handler)
    root_logger.setLevel(logging.INFO)
    
    # Настройка популярных модулей
    for module_name in ['asyncio', 'telethon', 'httpx', 'telegram', 'config']:
        module_logger = logging.getLogger(module_name)
        module_logger.setLevel(getattr(logging, LOG_LEVEL))
        
        # Если нужен отдельный файл для этого модуля
        if module_name in ['telethon', 'config']:
            module_file = f'logs/{module_name}_{timestamp}.log'
            module_handler = logging.FileHandler(module_file, encoding='utf-8')
            module_handler.setLevel(logging.INFO)
            module_handler.setFormatter(file_formatter)
            module_logger.addHandler(module_handler)
        
        # Запретить распространение логов в корневой логгер
        module_logger.propagate = False
    
    print(f"[INFO] Настроено логирование всех компонентов (уровень: {LOG_LEVEL})")
    print(f"[INFO] Объединенный лог всех компонентов: {all_log_file}")

def run_telegram_bot():
    """Запускает Telegram бота в отдельном процессе."""
    global bot_process
    
    try:
        logger.info("Запуск Telegram бота в отдельном процессе...")
        
        # Создаем переменные окружения для бота
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"  # Обеспечиваем корректное кодирование для логов
        env["LOG_LEVEL"] = LOG_LEVEL  # Передаем уровень логирования

        # Создаем имя файла лога для бота
        bot_log_file = f'logs/bot_{timestamp}.log'
        
        # Запускаем бот в отдельном процессе с перенаправлением вывода
        with open(bot_log_file, 'a', encoding='utf-8') as bot_log:
            bot_process = subprocess.Popen(
                [sys.executable, "bot.py"],
                stdout=bot_log,
                stderr=bot_log,
                env=env
            )
        
        print(f"[INFO] Telegram бот запущен с PID: {bot_process.pid}")
        logger.info(f"Telegram бот запущен с PID: {bot_process.pid}, логи в {bot_log_file}")
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        print(f"[ОШИБКА] Не удалось запустить Telegram бота: {e}")
        return False

async def run_solana_tracker():
    """Запускает отслеживание контрактов Solana."""
    global tracker_task
    
    try:
        # Переопределяем стандартный вывод для solana_contract_tracker
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        solana_log_file = f'logs/solana_output_{timestamp}.log'
        
        with open(solana_log_file, 'a', encoding='utf-8') as solana_stdout:
            # Перенаправляем stdout и stderr
            sys.stdout = solana_stdout
            sys.stderr = solana_stdout
            
            # Модифицируем переменные окружения для контроля логирования
            os.environ["LOG_LEVEL"] = LOG_LEVEL
            
            # Импортируем функцию main из solana_contract_tracker
            from solana_contract_tracker import main
            
            logger.info("Запуск отслеживания контрактов Solana...")
            
            # Возвращаем стандартный вывод основному процессу
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            
            print("[INFO] Отслеживание контрактов Solana запущено")
            
            # Создаем задачу для отслеживания
            tracker_task = asyncio.create_task(main())
            
            # Ждем завершения задачи или сигнала остановки
            await stop_event.wait()
            
            # Если трекер все еще работает, отменяем его
            if tracker_task and not tracker_task.done():
                logger.info("Остановка трекера контрактов Solana...")
                tracker_task.cancel()
                try:
                    await tracker_task
                except asyncio.CancelledError:
                    logger.info("Трекер остановлен")
            
    except Exception as e:
        logger.error(f"Ошибка при запуске трекера контрактов: {e}")
        print(f"[ОШИБКА] Не удалось запустить отслеживание контрактов: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Возвращаем стандартный вывод, если произошла ошибка
        if 'original_stdout' in locals() and sys.stdout != original_stdout:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

async def run_message_forwarder():
    """Запускает сервис пересылки сообщений."""
    global forwarder_task
    
    try:
        # Переопределяем стандартный вывод для message_forwarder
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        forwarder_log_file = f'logs/forwarder_output_{timestamp}.log'
        
        with open(forwarder_log_file, 'a', encoding='utf-8') as forwarder_stdout:
            # Перенаправляем stdout и stderr
            sys.stdout = forwarder_stdout
            sys.stderr = forwarder_stdout
            
            # Модифицируем переменные окружения для контроля логирования
            os.environ["LOG_LEVEL"] = LOG_LEVEL
            
            # Импортируем функцию start_forwarding из message_forwarder
            from message_forwarder import start_forwarding
            
            logger.info("Запуск сервиса пересылки сообщений...")
            
            # Возвращаем стандартный вывод основному процессу
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            
            print("[INFO] Сервис пересылки сообщений запущен")
            
            # Создаем задачу для пересылки сообщений
            forwarder_task = asyncio.create_task(start_forwarding())
            
            # Ждем завершения задачи или сигнала остановки
            await stop_event.wait()
            
            # Если задача все еще работает, отменяем её
            if forwarder_task and not forwarder_task.done():
                logger.info("Остановка сервиса пересылки сообщений...")
                forwarder_task.cancel()
                try:
                    await forwarder_task
                except asyncio.CancelledError:
                    logger.info("Сервис пересылки сообщений остановлен")
            
    except Exception as e:
        logger.error(f"Ошибка при запуске сервиса пересылки сообщений: {e}")
        print(f"[ОШИБКА] Не удалось запустить сервис пересылки сообщений: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Возвращаем стандартный вывод, если произошла ошибка
        if 'original_stdout' in locals() and sys.stdout != original_stdout:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

def signal_handler(sig, frame):
    """Обработчик сигнала прерывания."""
    logger.info("Получен сигнал прерывания, выполняется выход...")
    print("\n[INFO] Завершение работы системы...")
    
    # Останавливаем процессы
    global bot_process, stop_event
    
    # Устанавливаем событие остановки для асинхронных задач
    try:
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(stop_event.set)
    except:
        pass
    
    # Останавливаем процесс бота если он запущен
    if bot_process and bot_process.poll() is None:
        logger.info("Остановка процесса бота...")
        try:
            bot_process.terminate()
            # Даем процессу время на корректное завершение
            time.sleep(1)
            if bot_process.poll() is None:
                bot_process.kill()
        except:
            pass
    
    # Немного ждем перед завершением программы
    time.sleep(1)
    logger.info("Выход из программы")
    sys.exit(0)

async def main():
    """Основная асинхронная функция программы."""
    try:
        print("[INFO] Запуск системы...")
        
        # Настраиваем глобальное логирование
        configure_root_logger()
        
        # Запускаем бот
        if not run_telegram_bot():
            logger.error("Не удалось запустить Telegram бота")
            return
        
        # Даем время для инициализации бота
        await asyncio.sleep(5)
        
        # Запускаем отслеживание контрактов и пересылку сообщений параллельно
        tracker_coroutine = run_solana_tracker()
        forwarder_coroutine = run_message_forwarder()
        
        # Запускаем оба сервиса параллельно
        print("[INFO] Запуск всех компонентов системы...")
        await asyncio.gather(tracker_coroutine, forwarder_coroutine)
        
    except KeyboardInterrupt:
        logger.info("Программа остановлена пользователем")
        print("[INFO] Программа остановлена пользователем")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка: {e}")
        print(f"[ОШИБКА] Непредвиденная ошибка: {e}")
    finally:
        # Останавливаем процессы при выходе
        signal_handler(None, None)

if __name__ == "__main__":
    # Регистрируем обработчик сигнала прерывания
    signal.signal(signal.SIGINT, signal_handler)
    
    # Настройка для Windows, если необходимо
    if sys.version_info >= (3, 8) and sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Запускаем программу
    try:
        print("[INFO] Система запущена. Нажмите Ctrl+C для выхода.")
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] Завершение работы...")
    finally:
        print("[INFO] Программа завершена.")
import logging
from typing import Final

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)

logger = logging.getLogger(__name__)

# Токен телеграм бота
TELEGRAM_TOKEN: Final = "8147051772:AAE5LijuMcdPNazVmkvQmtGPf0OOdi4xZW0"

# API URLs
DEXSCREENER_API_URL: Final = "https://api.dexscreener.com/latest/dex/search"

# Данные для Telegram API
API_ID: Final = 25308063
API_HASH: Final = "458e1315175e0103f19d925204b690a5"

# Бот для отправки сообщений (без символа @ в начале)
TARGET_BOT: Final = "RadarDexBot"

# Настройки для message_forwarder.py
# Источники сообщений (имена ботов)
SOURCE_BOTS = [
    "TheMobyBot",  # без символа @ в начале
    "ray_cyan_bot"         # без символа @ в начале
]

# Целевой канал для пересылки из ботов
TARGET_CHANNEL = "cringemonke"  # без символа @ в начале
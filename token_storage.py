import logging
import time
import os
import json
from typing import Dict, Any, Optional, List
import pandas as pd
from datetime import datetime

# Настройка логгирования
logger = logging.getLogger(__name__)

# Словарь для хранения данных о токенах
# Ключ: запрос пользователя (адрес или название токена)
# Значение: словарь с данными о токене
token_data_store: Dict[str, Dict[str, Any]] = {}

# Интервал для автоматической проверки токенов (в секундах)
AUTO_CHECK_INTERVAL = 60  # 1 минута

# Время последней автоматической проверки
last_auto_check_time = 0

# Период хранения токенов (в секундах)
TOKEN_RETENTION_PERIOD = 31536000  # 1 год

# Словарь для хранения ID сообщений со списками токенов для каждого чата
list_message_ids = {}

# Путь к файлу Excel с базой токенов
EXCEL_DB_PATH = "tokens_database.xlsx"

# Путь к JSON-файлу для постоянного хранения данных
JSON_DB_PATH = "tokens_database.json"

# Загружаем данные при инициализации модуля
def load_data_from_disk():
    """Загружает данные о токенах из JSON-файла при запуске."""
    global token_data_store
    try:
        if os.path.exists(JSON_DB_PATH):
            with open(JSON_DB_PATH, 'r', encoding='utf-8') as json_file:
                data = json.load(json_file)
                token_data_store = data
                logger.info(f"Загружено {len(data)} токенов из JSON файла")
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных из JSON файла: {e}")

# Загружаем данные при импорте модуля
load_data_from_disk()

def save_data_to_disk():
    """Сохраняет данные о токенах в JSON-файл для постоянного хранения."""
    try:
        with open(JSON_DB_PATH, 'w', encoding='utf-8') as json_file:
            json.dump(token_data_store, json_file, ensure_ascii=False, default=str)
        logger.info(f"Сохранено {len(token_data_store)} токенов в JSON файл")
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных в JSON файл: {e}")

def store_token_data(query: str, data: Dict[str, Any]) -> None:
    """Сохраняет данные о токене в хранилище."""
    # Добавляем время добавления токена, если его нет
    if 'added_time' not in data:
        data['added_time'] = time.time()
    
    # По запросу: разрешаем дубликаты токенов для тестирования ATH
    token_data_store[query] = data
    logger.info(f"Данные о токене '{query}' сохранены в хранилище")
    
    # Сохраняем данные в Excel
    save_token_to_excel(query, data)
    
    # Также сохраняем данные в JSON для постоянного хранения
    save_data_to_disk()

def save_token_to_excel(query: str, data: Dict[str, Any]) -> None:
    """Сохраняет данные о токене в Excel с двумя строками: начальные и текущие значения."""
    try:
        # Подготавливаем данные для Excel
        initial_data, current_data = prepare_excel_data(query, data)
        
        # Проверяем, существует ли файл Excel
        if os.path.exists(EXCEL_DB_PATH):
            # Загружаем существующий файл
            try:
                df = pd.read_excel(EXCEL_DB_PATH)
            except Exception as e:
                logger.error(f"Ошибка при чтении файла Excel: {e}")
                df = pd.DataFrame()
        else:
            # Создаем новый DataFrame
            df = pd.DataFrame()
        
        # Проверяем, есть ли уже этот токен в базе
        if 'query' in df.columns and query in df['query'].values:
            # Находим индексы строк с данным токеном
            token_indices = df.index[df['query'] == query].tolist()
            
            if len(token_indices) >= 2:
                # Обновляем существующие записи
                # Первая строка (начальные значения)
                for key, value in initial_data.items():
                    df.at[token_indices[0], key] = value
                
                # Вторая строка (текущие значения)
                for key, value in current_data.items():
                    df.at[token_indices[1], key] = value
                
                # Добавляем запись об обновлении
                df.at[token_indices[1], 'last_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                # Если существует только одна строка, удаляем ее и добавляем две новые
                df = df[df['query'] != query]
                
                # Добавляем новые строки
                initial_data['creation_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                initial_data['last_update'] = initial_data['creation_date']
                initial_data['data_type'] = 'initial'
                
                current_data['creation_date'] = initial_data['creation_date']
                current_data['last_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                current_data['data_type'] = 'current'
                
                df = pd.concat([df, pd.DataFrame([initial_data, current_data])], ignore_index=True)
        else:
            # Добавляем новые строки (начальные и текущие значения)
            initial_data['creation_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            initial_data['last_update'] = initial_data['creation_date']
            initial_data['data_type'] = 'initial'
            
            current_data['creation_date'] = initial_data['creation_date']
            current_data['last_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            current_data['data_type'] = 'current'
            
            df = pd.concat([df, pd.DataFrame([initial_data, current_data])], ignore_index=True)
        
        # Сохраняем DataFrame в Excel
        df.to_excel(EXCEL_DB_PATH, index=False)
        logger.info(f"Данные о токене '{query}' сохранены в Excel (начальные и текущие значения)")
    
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных в Excel: {e}")

def prepare_excel_data(query: str, data: Dict[str, Any]) -> tuple:
    """
    Подготавливает данные о токене для Excel, возвращая две структуры:
    1. Начальные значения
    2. Текущие значения
    """
    # Базовая информация для обеих строк
    initial_data = {'query': query}
    current_data = {'query': query}
    
    # Получаем все данные из API, если они есть
    raw_api_data = data.get('raw_api_data', {})
    if raw_api_data:
        # Сохраняем все данные из API в current_data
        for key, value in raw_api_data.items():
            if isinstance(value, (dict, list)):
                current_data[f'api_{key}'] = str(value)  # Преобразуем сложные структуры в строки
            else:
                current_data[f'api_{key}'] = value
    
    # Добавляем базовую информацию для обеих строк
    if 'token_info' in data:
        token_info = data['token_info']
        for key, value in token_info.items():
            current_data[key] = value
    
    # Заполняем начальные данные
    if 'initial_data' in data:
        init_data = data['initial_data']
        initial_data['time'] = init_data.get('time', 'Не указано')
        initial_data['market_cap'] = init_data.get('market_cap', 'Неизвестно')
        initial_data['raw_market_cap'] = init_data.get('raw_market_cap', 0)
        
        # Копируем основную информацию из token_info для начальных данных
        if 'token_info' in data:
            token_info = data['token_info']
            initial_data['ticker'] = token_info.get('ticker', 'Неизвестно')
            initial_data['ticker_address'] = token_info.get('ticker_address', 'Неизвестно')
            initial_data['token_age'] = token_info.get('token_age', 'Неизвестно')
            initial_data['dexscreener_link'] = token_info.get('dexscreener_link', '#')
            initial_data['axiom_link'] = token_info.get('axiom_link', '#')
    
    # Добавляем ATH информацию для начальной строки
    ath_market_cap = data.get('ath_market_cap', 0)
    initial_data['ath_market_cap'] = ath_market_cap
    
    # Если ATH не установлен или меньше начального, используем начальный как ATH
    if 'initial_data' in data:
        initial_mcap = data['initial_data'].get('raw_market_cap', 0)
        if not ath_market_cap or (initial_mcap > ath_market_cap):
            initial_data['ath_market_cap'] = initial_mcap
    
    if 'ath_time' in data:
        ath_time = data['ath_time']
        initial_data['ath_time'] = datetime.fromtimestamp(ath_time).strftime("%Y-%m-%d %H:%M:%S")
    
    # Добавляем информацию о последнем алерте множителя
    initial_data['last_alert_multiplier'] = data.get('last_alert_multiplier', 1)
    current_data['last_alert_multiplier'] = data.get('last_alert_multiplier', 1)
    
    # Добавляем ссылку на сообщение для обеих строк
    chat_id = data.get('chat_id', 0)
    message_id = data.get('message_id', 0)
    initial_data['chat_id'] = chat_id
    initial_data['message_id'] = message_id
    current_data['chat_id'] = chat_id
    current_data['message_id'] = message_id
    
    return initial_data, current_data

def get_token_data(query: str) -> Optional[Dict[str, Any]]:
    """Получает данные о токене из хранилища."""
    data = token_data_store.get(query)
    if data:
        logger.info(f"Данные о токене '{query}' получены из хранилища")
    else:
        logger.info(f"Данные о токене '{query}' не найдены в хранилище")
    return data

def update_token_field(query: str, field: str, value: Any) -> bool:
    """Обновляет значение поля в данных о токене."""
    if query in token_data_store:
        token_data_store[query][field] = value
        logger.info(f"Поле '{field}' для токена '{query}' обновлено на значение '{value}'")
        
        # Сохраняем обновленные данные в Excel
        save_token_to_excel(query, token_data_store[query])
        
        # Также сохраняем обновленные данные в JSON
        save_data_to_disk()
        
        return True
    else:
        logger.warning(f"Не удалось обновить поле '{field}' для токена '{query}': токен не найден")
        return False

def remove_token_data(query: str) -> bool:
    """Удаляет данные о токене из хранилища."""
    if query in token_data_store:
        del token_data_store[query]
        logger.info(f"Данные о токене '{query}' удалены из хранилища")
        
        # Обновляем Excel
        try:
            if os.path.exists(EXCEL_DB_PATH):
                df = pd.read_excel(EXCEL_DB_PATH)
                if 'query' in df.columns and query in df['query'].values:
                    df = df[df['query'] != query]
                    df.to_excel(EXCEL_DB_PATH, index=False)
                    logger.info(f"Данные о токене '{query}' удалены из Excel")
        except Exception as e:
            logger.error(f"Ошибка при удалении данных из Excel: {e}")
        
        # Сохраняем обновленные данные в JSON
        save_data_to_disk()
        
        return True
    else:
        logger.warning(f"Не удалось удалить данные о токене '{query}': токен не найден")
        return False

def get_all_tokens(include_hidden: bool = True) -> Dict[str, Dict[str, Any]]:
    """
    Возвращает словарь со всеми отслеживаемыми токенами.
    
    Args:
        include_hidden: Если True, включает скрытые токены, иначе исключает их
    """
    if include_hidden:
        return token_data_store
    else:
        # Фильтруем скрытые токены
        return {query: data for query, data in token_data_store.items() 
                if not data.get('hidden', False)}

def get_active_tokens(include_hidden: bool = False) -> Dict[str, Dict[str, Any]]:
    """
    Возвращает словарь с токенами, добавленными за последние 24 часа.
    
    Args:
        include_hidden: Если True, включает скрытые токены, иначе исключает их
    """
    current_time = time.time()
    active_tokens = {}
    
    for query, data in token_data_store.items():
        # Пропускаем скрытые токены, если указано их не включать
        if not include_hidden and data.get('hidden', False):
            continue
            
        added_time = data.get('added_time', 0)
        if current_time - added_time <= TOKEN_RETENTION_PERIOD:
            active_tokens[query] = data
    
    return active_tokens

def update_token_ath(query: str, current_mcap: float) -> bool:
    """Обновляет ATH (All-Time High) маркет капа токена, если текущее значение выше."""
    if query not in token_data_store:
        return False
    
    current_ath = token_data_store[query].get('ath_market_cap', 0)
    
    if current_mcap > current_ath:
        token_data_store[query]['ath_market_cap'] = current_mcap
        token_data_store[query]['ath_time'] = time.time()
        logger.info(f"Обновлен ATH для токена '{query}': {current_mcap}")
        
        # Сохраняем обновленные данные в Excel
        save_token_to_excel(query, token_data_store[query])
        
        # Сохраняем обновленные данные в JSON
        save_data_to_disk()
        
        return True
    
    return False

def check_auto_update_needed() -> bool:
    """Проверяет, нужно ли выполнить автоматическую проверку токенов."""
    global last_auto_check_time
    current_time = time.time()
    
    if current_time - last_auto_check_time >= AUTO_CHECK_INTERVAL:
        last_auto_check_time = current_time
        return True
    
    return False

def update_last_auto_check_time() -> None:
    """Обновляет время последней автоматической проверки."""
    global last_auto_check_time
    last_auto_check_time = time.time()

def hide_token(query: str) -> bool:
    """Помечает токен как скрытый, чтобы он не отображался в списке, но сохранялся в базе данных."""
    if query in token_data_store:
        token_data_store[query]['hidden'] = True
        
        # Также обновляем статус в Excel, если файл существует
        try:
            if os.path.exists(EXCEL_DB_PATH):
                df = pd.read_excel(EXCEL_DB_PATH)
                if 'query' in df.columns and query in df['query'].values:
                    # Обновляем статус для обеих строк
                    token_indices = df.index[df['query'] == query].tolist()
                    for idx in token_indices:
                        df.at[idx, 'hidden'] = True
                        df.at[idx, 'last_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    df.to_excel(EXCEL_DB_PATH, index=False)
                    logger.info(f"Токен '{query}' помечен как скрытый в Excel")
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса скрытия в Excel: {e}")
        
        # Обновляем статус в базе tracker
        try:
            TRACKER_DB_FILE = 'tokens_tracker_database.json'
            if os.path.exists(TRACKER_DB_FILE):
                with open(TRACKER_DB_FILE, 'r', encoding='utf-8') as f:
                    tracker_db = json.load(f)
                
                # Если токен существует в tracker_db, обновляем его статус
                if query in tracker_db:
                    tracker_db[query]['hidden'] = True
                    with open(TRACKER_DB_FILE, 'w', encoding='utf-8') as f:
                        json.dump(tracker_db, f, ensure_ascii=False, indent=4)
                    logger.info(f"Токен '{query}' помечен как скрытый в tracker базе")
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса в tracker базе: {e}")
        
        # Сохраняем изменения в JSON
        save_data_to_disk()
        
        return True
    return False

def unhide_token(query: str) -> bool:
    """Восстанавливает скрытый токен, чтобы он снова отображался в списке."""
    if query in token_data_store:
        token_data_store[query]['hidden'] = False
        
        # Также обновляем статус в Excel, если файл существует
        try:
            if os.path.exists(EXCEL_DB_PATH):
                df = pd.read_excel(EXCEL_DB_PATH)
                if 'query' in df.columns and query in df['query'].values:
                    # Обновляем статус для обеих строк
                    token_indices = df.index[df['query'] == query].tolist()
                    for idx in token_indices:
                        df.at[idx, 'hidden'] = False
                        df.at[idx, 'last_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    df.to_excel(EXCEL_DB_PATH, index=False)
                    logger.info(f"Токен '{query}' восстановлен из скрытых в Excel")
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса скрытия в Excel: {e}")
        
        # Обновляем статус в базе tracker
        try:
            TRACKER_DB_FILE = 'tokens_tracker_database.json'
            if os.path.exists(TRACKER_DB_FILE):
                with open(TRACKER_DB_FILE, 'r', encoding='utf-8') as f:
                    tracker_db = json.load(f)
                
                # Если токен существует в tracker_db, обновляем его статус
                if query in tracker_db:
                    if 'hidden' in tracker_db[query]:
                        tracker_db[query]['hidden'] = False
                    with open(TRACKER_DB_FILE, 'w', encoding='utf-8') as f:
                        json.dump(tracker_db, f, ensure_ascii=False, indent=4)
                    logger.info(f"Токен '{query}' восстановлен из скрытых в tracker базе")
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса в tracker базе: {e}")
        
        # Сохраняем изменения в JSON
        save_data_to_disk()
        
        return True
    return False

def get_hidden_tokens() -> Dict[str, Dict[str, Any]]:
    """Возвращает словарь со всеми скрытыми токенами."""
    return {query: data for query, data in token_data_store.items() 
            if data.get('hidden', False)}

def delete_token(query: str) -> bool:
    """Полностью удаляет токен из хранилища (вместо скрытия)."""
    if query in token_data_store:
        # Удаляем токен из словаря
        token_data = token_data_store.pop(query)
        
        # Также удаляем из Excel, если файл существует
        try:
            if os.path.exists(EXCEL_DB_PATH):
                df = pd.read_excel(EXCEL_DB_PATH)
                if 'query' in df.columns and query in df['query'].values:
                    # Удаляем строки с данным токеном
                    df = df[df['query'] != query]
                    df.to_excel(EXCEL_DB_PATH, index=False)
                    logger.info(f"Токен '{query}' полностью удален из Excel")
        except Exception as e:
            logger.error(f"Ошибка при удалении токена из Excel: {e}")
        
        # Удаляем из tracker базы
        try:
            TRACKER_DB_FILE = 'tokens_tracker_database.json'
            if os.path.exists(TRACKER_DB_FILE):
                with open(TRACKER_DB_FILE, 'r', encoding='utf-8') as f:
                    tracker_db = json.load(f)
                
                # Если токен существует в tracker_db, удаляем его
                if query in tracker_db:
                    del tracker_db[query]
                    with open(TRACKER_DB_FILE, 'w', encoding='utf-8') as f:
                        json.dump(tracker_db, f, ensure_ascii=False, indent=4)
                    logger.info(f"Токен '{query}' полностью удален из tracker базы")
        except Exception as e:
            logger.error(f"Ошибка при удалении токена из tracker базы: {e}")
        
        # Сохраняем изменения в JSON
        save_data_to_disk()
        
        logger.info(f"Токен '{query}' полностью удален из хранилища")
        return True
    return False

def delete_all_tokens() -> int:
    """Полностью удаляет все токены из хранилища (вместо скрытия).
    Возвращает количество удаленных токенов."""
    
    global token_data_store
    token_count = len(token_data_store)
    
    if token_count == 0:
        return 0
        
    # Создаем резервную копию данных перед удалением
    try:
        # Резервная копия Excel
        if os.path.exists(EXCEL_DB_PATH):
            backup_path = f"{EXCEL_DB_PATH}.backup_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            import shutil
            shutil.copy2(EXCEL_DB_PATH, backup_path)
            logger.info(f"Создана резервная копия базы токенов: {backup_path}")
            
            # Создаем пустой Excel файл
            df = pd.DataFrame()
            df.to_excel(EXCEL_DB_PATH, index=False)
        
        # Резервная копия JSON
        if os.path.exists(JSON_DB_PATH):
            backup_path = f"{JSON_DB_PATH}.backup_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            import shutil
            shutil.copy2(JSON_DB_PATH, backup_path)
            logger.info(f"Создана резервная копия JSON базы токенов: {backup_path}")
    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии данных: {e}")
    
    # Очищаем словарь токенов
    token_data_store = {}
    
    # Сохраняем пустой словарь в JSON
    save_data_to_disk()
    
    logger.info(f"Все токены ({token_count} шт.) полностью удалены из хранилища")
    return token_count

def store_list_message_id(chat_id: int, message_id: int) -> None:
    """Сохраняет ID сообщения со списком токенов для указанного чата."""
    list_message_ids[chat_id] = message_id
    logger.info(f"ID сообщения со списком токенов для чата {chat_id} сохранен: {message_id}")

def get_list_message_id(chat_id: int) -> Optional[int]:
    """Получает ID последнего сообщения со списком токенов для указанного чата."""
    message_id = list_message_ids.get(chat_id)
    return message_id

def get_excel_all_tokens() -> str:
    """Возвращает путь к Excel файлу со всеми токенами."""
    # Обновляем Excel файл перед возвратом
    try:
        if not os.path.exists(EXCEL_DB_PATH):
            # Создаем новый файл, если он не существует
            df = pd.DataFrame()
            df.to_excel(EXCEL_DB_PATH, index=False)
        else:
            # Проверяем, что файл не пустой
            df = pd.read_excel(EXCEL_DB_PATH)
            if df.empty and token_data_store:
                # Если Excel пустой, но есть данные о токенах, заполняем его
                for query, data in token_data_store.items():
                    save_token_to_excel(query, data)
    except Exception as e:
        logger.error(f"Ошибка при обновлении Excel файла: {e}")
    
    return EXCEL_DB_PATH

def clean_expired_tokens() -> List[str]:
    """Удаляет токены, которые находятся в хранилище более 24 часов.
    Возвращает список удаленных токенов."""
    current_time = time.time()
    expired_tokens = []
    
    for query, data in list(token_data_store.items()):
        added_time = data.get('added_time', 0)
        if current_time - added_time > TOKEN_RETENTION_PERIOD:
            del token_data_store[query]
            expired_tokens.append(query)
            logger.info(f"Токен '{query}' удален из-за истечения срока хранения (24 часа)")
            
            # Обновляем статус в Excel
            try:
                if os.path.exists(EXCEL_DB_PATH):
                    df = pd.read_excel(EXCEL_DB_PATH)
                    if 'query' in df.columns and query in df['query'].values:
                        # Обновляем статус для обеих строк
                        token_indices = df.index[df['query'] == query].tolist()
                        for idx in token_indices:
                            df.at[idx, 'status'] = 'expired'
                            df.at[idx, 'last_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        df.to_excel(EXCEL_DB_PATH, index=False)
            except Exception as e:
                logger.error(f"Ошибка при обновлении статуса в Excel: {e}")
    
    # Если были удалены токены, обновляем JSON
    if expired_tokens:
        save_data_to_disk()
    
    return expired_tokens
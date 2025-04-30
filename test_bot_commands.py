import logging
import asyncio
import traceback
import telegram
from typing import Dict, Any, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

# Импортируем модули проекта
import token_storage
from utils import format_tokens_list

# Настройка логирования
debug_logger = logging.getLogger('debug')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    try:
        await update.message.reply_text(
            "Привет! Я предоставляю информацию о криптотокенах.\n\n"
            "Отправь мне адрес токена или его название, и я покажу тебе информацию о нем.\n\n"
            "Доступные команды:\n"
            "/start - запустить бота\n"
            "/help - показать справку\n"
            "/list - показать список отслеживаемых токенов\n"
            "/excel - сформировать Excel-файл со всеми данными\n"
            "/clear - очистить все данные о токенах"
        )
        debug_logger.info(f"Отправлено приветственное сообщение пользователю {update.effective_user.id}")
    except Exception as e:
        debug_logger.error(f"Ошибка при отправке приветственного сообщения: {str(e)}")
        debug_logger.error(traceback.format_exc())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет справочное сообщение при команде /help."""
    try:
        await update.message.reply_text(
            "Я могу предоставить информацию о токенах.\n\n"
            "Просто отправь мне адрес контракта или название токена, и я покажу тебе его данные.\n"
            "Я также отслеживаю рост Market Cap и отправляю уведомления при значительном росте (x2, x3, x4...).\n\n"
            "Доступные команды:\n"
            "/start - запустить бота\n"
            "/help - показать справку\n"
            "/list - показать список отслеживаемых токенов\n"
            "/excel - сформировать Excel-файл со всеми данными\n"
            "/clear - удалить/управлять токенами\n\n"
            "Обозначения источников сигналов:\n"
            "🎯 - Снайпер с миграции\n"
            "💎 - Gem канал\n"
            "🍀 - KOL телеграм\n"
            "⚡ - Early mover\n"
            "💵 - SmartMoney\n"
            "🐋 - Покупка кита\n"
            "🚀 - Резкий рост объемов\n"
            "🐂 - СмартKOL"
        )
        debug_logger.info(f"Отправлено справочное сообщение пользователю {update.effective_user.id}")
    except Exception as e:
        debug_logger.error(f"Ошибка при отправке справочного сообщения: {str(e)}")
        debug_logger.error(traceback.format_exc())

async def list_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список всех отслеживаемых не скрытых токенов с пагинацией."""
    try:
        debug_logger.info("Запрошен список отслеживаемых токенов")
        
        # Получаем chat_id для идентификации чата
        chat_id = update.message.chat_id
        
        # Извлекаем номер страницы, если он передан в аргументах команды
        page = 0
        if context.args and len(context.args) > 0:
            try:
                page = int(context.args[0]) - 1  # Преобразуем в 0-based индекс
                if page < 0:
                    page = 0
            except ValueError:
                page = 0
        
        # Проверяем, есть ли предыдущее сообщение со списком токенов для этого чата
        prev_message_id = token_storage.get_list_message_id(chat_id)
        
        # Удаляем команду /list пользователя (если бот имеет права на удаление сообщений)
        try:
            await update.message.delete()
            debug_logger.info(f"Команда /list удалена из чата {chat_id}")
        except Exception as e:
            debug_logger.warning(f"Не удалось удалить команду /list: {e}")
        
        # Если есть предыдущее сообщение, удаляем его
        if prev_message_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=prev_message_id)
                debug_logger.info(f"Предыдущее сообщение со списком токенов удалено (ID: {prev_message_id})")
            except Exception as e:
                debug_logger.warning(f"Не удалось удалить предыдущее сообщение: {e}")
        
        # Отправляем новое сообщение с уведомлением об обновлении данных
        wait_message = await context.bot.send_message(
            chat_id=chat_id,
            text="Обновляю данные о токенах...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Сохраняем ID нового сообщения
        token_storage.store_list_message_id(chat_id, wait_message.message_id)
        
        # Получаем все токены, исключая скрытые
        active_tokens = token_storage.get_all_tokens(include_hidden=False)
        
        if not active_tokens:
            await wait_message.edit_text(
                "Нет активных токенов в списке отслеживаемых."
            )
            debug_logger.info("Список токенов пуст")
            return
        
        # Форматируем список токенов с пагинацией
        tokens_per_page = 10  # Отображаем по 10 токенов на странице
        message, total_pages, current_page = format_tokens_list(active_tokens, page, tokens_per_page)
        
        # Создаем кнопки навигации
        keyboard = []
        
        # Кнопки для навигации по страницам
        nav_buttons = []
        if total_pages > 1:
            if current_page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"list_page:{current_page-1}"))
            
            if current_page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("Следующая ➡️", callback_data=f"list_page:{current_page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Кнопки для действий со списком
        action_buttons = [
            InlineKeyboardButton("🔄 Обновить", callback_data=f"list_page:{current_page}"),
            InlineKeyboardButton("📊 Excel отчет", callback_data="generate_excel")
        ]
        keyboard.append(action_buttons)
        
        # Кнопка для управления токенами
        keyboard.append([InlineKeyboardButton("🔍 Управление токенами", callback_data="manage_tokens")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Обновляем сообщение с актуальными данными
        try:
            await wait_message.edit_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            debug_logger.info(f"Список токенов успешно отправлен (страница {current_page+1} из {total_pages})")
        except telegram.error.BadRequest as e:
            if "Message is too long" in str(e):
                # Если сообщение слишком длинное, уменьшаем количество токенов на странице
                tokens_per_page = 5
                message, total_pages, current_page = format_tokens_list(active_tokens, page, tokens_per_page)
                
                # Обновляем кнопки навигации
                keyboard = []
                nav_buttons = []
                
                if total_pages > 1:
                    if current_page > 0:
                        nav_buttons.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"list_page:{current_page-1}"))
                    
                    if current_page < total_pages - 1:
                        nav_buttons.append(InlineKeyboardButton("Следующая ➡️", callback_data=f"list_page:{current_page+1}"))
                
                if nav_buttons:
                    keyboard.append(nav_buttons)
                
                keyboard.append(action_buttons)
                keyboard.append([InlineKeyboardButton("🔍 Управление токенами", callback_data="manage_tokens")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await wait_message.edit_text(
                    message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
                debug_logger.info(f"Список токенов успешно отправлен (страница {current_page+1} из {total_pages}, уменьшено количество токенов на странице)")
            else:
                # Если произошла другая ошибка
                error_message = "Произошла ошибка при формировании списка токенов. Пожалуйста, попробуйте позже."
                await wait_message.edit_text(error_message)
                debug_logger.error(f"Ошибка при отправке списка токенов: {str(e)}")
        
    except Exception as e:
        debug_logger.error(f"Ошибка при выполнении команды /list: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await update.message.reply_text(
                "Произошла ошибка при формировании списка токенов. Пожалуйста, попробуйте позже."
            )
        except Exception:
            pass

async def excel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Формирует Excel-файл со всеми данными о токенах."""
    try:
        debug_logger.info("Запрошено формирование Excel-файла")
        
        # Получаем chat_id для идентификации чата
        chat_id = update.message.chat_id
        
        # Отправляем уведомление о начале формирования файла
        wait_message = await update.message.reply_text(
            "Формирую Excel-файл со всеми данными о токенах...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Получаем все токены
        active_tokens = token_storage.get_all_tokens()
        
        if not active_tokens:
            await wait_message.edit_text(
                "Нет активных токенов для формирования Excel-файла."
            )
            debug_logger.info("Список токенов пуст, Excel-файл не сформирован")
            return
        
        # Импортируем функцию generate_excel из token_service
        from token_service import generate_excel
        
        # Генерируем Excel-файл
        await generate_excel(context, chat_id)
        
        # Удаляем сообщение об ожидании
        await wait_message.delete()
        
        debug_logger.info(f"Excel-файл успешно сформирован и отправлен пользователю {update.effective_user.id}")
        
    except Exception as e:
        debug_logger.error(f"Ошибка при формировании Excel-файла: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await update.message.reply_text(
                "Произошла ошибка при формировании Excel-файла. Пожалуйста, попробуйте позже."
            )
        except Exception:
            pass

async def handle_refresh_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает обновление списка токенов."""
    query = update.callback_query
    chat_id = query.message.chat_id
    
    try:
        # Получаем текущую страницу из данных callback, по умолчанию - первая страница
        page = 0
        if ":" in query.data:
            _, page = query.data.split(":", 1)
            page = int(page)
        
        # Уведомляем пользователя о начале обновления
        await query.answer("Обновляю список токенов...")
        
        # Сохраняем ID текущего сообщения
        token_storage.store_list_message_id(chat_id, query.message.message_id)
        
        # Получаем свежие данные о всех токенах, исключая скрытые
        active_tokens = token_storage.get_all_tokens(include_hidden=False)
        
        if not active_tokens:
            await query.edit_message_text(
                "Нет активных токенов в списке отслеживаемых.",
                parse_mode=ParseMode.MARKDOWN
            )
            debug_logger.info("Список токенов пуст после обновления")
            return
        
        # Форматируем список токенов с пагинацией
        tokens_per_page = 10  # Отображаем по 10 токенов на странице
        message, total_pages, current_page = format_tokens_list(active_tokens, page, tokens_per_page)
        
        # Создаем кнопки навигации
        keyboard = []
        
        # Кнопки для навигации по страницам
        nav_buttons = []
        if total_pages > 1:
            if current_page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"list_page:{current_page-1}"))
            
            if current_page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("Следующая ➡️", callback_data=f"list_page:{current_page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Кнопки для действий со списком
        action_buttons = [
            InlineKeyboardButton("🔄 Обновить", callback_data=f"list_page:{current_page}"),
            InlineKeyboardButton("📊 Excel отчет", callback_data="generate_excel")
        ]
        keyboard.append(action_buttons)
        
        # Кнопка для управления токенами
        keyboard.append([InlineKeyboardButton("🔍 Управление токенами", callback_data="manage_tokens")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Обновляем сообщение с актуальными данными
        try:
            await query.edit_message_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            debug_logger.info(f"Список из {len(active_tokens)} токенов успешно обновлен (страница {current_page+1} из {total_pages})")
        except telegram.error.BadRequest as e:
            if "Message is too long" in str(e):
                # Если сообщение слишком длинное, уменьшаем количество токенов на странице
                tokens_per_page = 5
                message, total_pages, current_page = format_tokens_list(active_tokens, page, tokens_per_page)
                
                # Обновляем кнопки навигации
                keyboard = []
                nav_buttons = []
                
                if total_pages > 1:
                    if current_page > 0:
                        nav_buttons.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"list_page:{current_page-1}"))
                    
                    if current_page < total_pages - 1:
                        nav_buttons.append(InlineKeyboardButton("Следующая ➡️", callback_data=f"list_page:{current_page+1}"))
                
                if nav_buttons:
                    keyboard.append(nav_buttons)
                
                keyboard.append(action_buttons)
                keyboard.append([InlineKeyboardButton("🔍 Управление токенами", callback_data="manage_tokens")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
                debug_logger.info(f"Список токенов успешно обновлен (страница {current_page+1} из {total_pages}, уменьшено количество токенов на странице)")
            else:
                # Если произошла другая ошибка
                debug_logger.error(f"Ошибка при обновлении списка токенов: {str(e)}")
                await query.answer("Ошибка при обновлении списка. Пожалуйста, попробуйте позже.")
        
    except Exception as e:
        debug_logger.error(f"Ошибка при обновлении списка токенов: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка при обновлении списка. Пожалуйста, попробуйте позже.")
        except Exception:
            pass

async def handle_generate_excel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает запрос на генерацию Excel-файла через инлайн-кнопку."""
    query = update.callback_query
    chat_id = query.message.chat_id
    
    try:
        # Уведомляем пользователя о начале формирования файла
        await query.answer("Генерирую Excel-файл...")
        
        # Отправляем уведомление в чат
        wait_message = await context.bot.send_message(
            chat_id=chat_id,
            text="Формирую Excel-файл со всеми данными о токенах...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Импортируем функцию generate_excel из token_service
        from token_service import generate_excel
        
        # Генерируем Excel-файл
        await generate_excel(context, chat_id)
        
        # Удаляем сообщение об ожидании
        await wait_message.delete()
        
        debug_logger.info(f"Excel-файл успешно сформирован и отправлен по запросу через инлайн-кнопку")
        
    except Exception as e:
        debug_logger.error(f"Ошибка при формировании Excel-файла через инлайн-кнопку: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Произошла ошибка при формировании Excel-файла. Пожалуйста, попробуйте позже."
            )
        except Exception:
            pass

async def clear_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает меню управления токенами (удаление/скрытие)."""
    try:
        debug_logger.info("Запрошено управление токенами")
        
        # Получаем словарь со всеми токенами, включая скрытые
        all_tokens = token_storage.get_all_tokens(include_hidden=True)
        tokens_count = len(all_tokens)
        
        if tokens_count == 0:
            await update.message.reply_text(
                "Нет сохраненных токенов для управления."
            )
            return
        
        # Добавляем опции для удаления и скрытия токенов
        keyboard = [
            [InlineKeyboardButton("⛔ Удалить все", callback_data="delete_all_confirm")],
            [InlineKeyboardButton("🔍 Выборочное удаление", callback_data="delete_selective")],
            [InlineKeyboardButton("🙈 Скрыть все", callback_data="clear_all_confirm")],
            [InlineKeyboardButton("📋 Выборочное скрытие", callback_data="clear_selective")],
            [InlineKeyboardButton("🕵️ Управление скрытыми", callback_data="manage_hidden")],
            [InlineKeyboardButton("❌ Отмена", callback_data="clear_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Получаем число видимых и скрытых токенов
        visible_tokens_count = len(token_storage.get_all_tokens(include_hidden=False))
        hidden_tokens_count = len(token_storage.get_hidden_tokens())
        
        # Отправляем сообщение с опциями
        await update.message.reply_text(
            f"Выберите действие для токенов (активных: {visible_tokens_count}, скрытых: {hidden_tokens_count}):\n\n"
            "⛔ *Удалить все* - удалит все активные токены полностью.\n"
            "🔍 *Выборочное удаление* - позволит выбрать токены для удаления.\n"
            "🙈 *Скрыть все* - скроет все токены (они останутся в базе).\n"
            "📋 *Выборочное скрытие* - позволит выбрать токены для скрытия.\n"
            "🕵️ *Управление скрытыми* - управление скрытыми токенами.\n"
            "❌ *Отмена* - отменить операцию.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        debug_logger.info(f"Отправлен запрос на управление токенами (активных: {visible_tokens_count}, скрытых: {hidden_tokens_count})")
        
    except Exception as e:
        debug_logger.error(f"Ошибка при выполнении команды /clear: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await update.message.reply_text(
                "Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."
            )
        except Exception:
            pass

async def handle_clear_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает подтверждение скрытия всех токенов."""
    query = update.callback_query
    
    try:
        # Логируем действие
        debug_logger.info("Подтверждена очистка всех токенов")
        
        # Получаем число токенов перед очисткой (для логирования)
        tokens_count = len(token_storage.get_all_tokens(include_hidden=True))
        
        # Помечаем все токены как скрытые вместо полного удаления
        tokens = token_storage.get_all_tokens(include_hidden=True)
        for token_query in tokens:
            token_storage.hide_token(token_query)
        
        # Обновляем сообщение
        await query.edit_message_text(
            f"✅ *Все токены скрыты ({tokens_count} шт.)*\n\n"
            "Они больше не будут отображаться в списке, но сохранятся в истории.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        await query.answer("Токены успешно скрыты")
        debug_logger.info(f"Скрыты все токены ({tokens_count} шт.)")
    except Exception as e:
        debug_logger.error(f"Ошибка при подтверждении очистки токенов: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка при очистке токенов.")
        except:
            pass

async def handle_clear_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает отмену удаления всех токенов."""
    query = update.callback_query
    
    try:
        # Обновляем сообщение
        await query.edit_message_text(
            "❌ Операция удаления отменена.\n\n"
            "Все данные о токенах сохранены.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        await query.answer("Операция отменена")
        debug_logger.info("Удаление токенов отменено пользователем")
    except Exception as e:
        debug_logger.error(f"Ошибка при отмене удаления токенов: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка при отмене удаления.")
        except:
            pass

async def handle_clear_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает запрос на скрытие всех токенов."""
    query = update.callback_query
    
    try:
        # Создаем кнопки для подтверждения
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, скрыть все", callback_data="clear_confirm"),
                InlineKeyboardButton("❌ Отмена", callback_data="clear_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Получаем число токенов
        tokens_count = len(token_storage.get_all_tokens(include_hidden=True))
        
        # Обновляем сообщение с запросом подтверждения
        await query.edit_message_text(
            f"Вы уверены, что хотите скрыть *все* токены? ({tokens_count} шт.)\n\n"
            "Они больше не будут отображаться в списке, но сохранятся в базе данных.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        await query.answer()
        debug_logger.info(f"Запрос подтверждения скрытия всех токенов ({tokens_count} шт.)")
    except Exception as e:
        debug_logger.error(f"Ошибка при запросе подтверждения скрытия: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")
        except:
            pass

async def handle_clear_selective(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает запрос на выборочное скрытие токенов."""
    query = update.callback_query
    page = 0
    
    try:
        # Извлекаем номер страницы из callback_data, если он есть
        if ":" in query.data:
            _, page = query.data.split(":", 1)
            page = int(page)
        
        # Получаем видимые токены
        tokens = token_storage.get_all_tokens(include_hidden=False)
        
        if not tokens:
            await query.edit_message_text(
                "Нет активных токенов для скрытия.",
                parse_mode=ParseMode.MARKDOWN
            )
            await query.answer()
            return
        
        # Формируем список токенов
        tokens_list = list(tokens.items())
        tokens_count = len(tokens_list)
        
        # Настройки пагинации
        tokens_per_page = 5
        total_pages = (tokens_count + tokens_per_page - 1) // tokens_per_page  # округление вверх
        
        # Проверяем, что страница в допустимых пределах
        if page >= total_pages:
            page = 0
        
        # Получаем токены для текущей страницы
        start_idx = page * tokens_per_page
        end_idx = min(start_idx + tokens_per_page, tokens_count)
        page_tokens = tokens_list[start_idx:end_idx]
        
        # Создаем кнопки для выбора токенов
        keyboard = []
        
        for idx, (token_query, token_data) in enumerate(page_tokens, start=start_idx + 1):
            # Получаем тикер для отображения
            ticker = "Неизвестно"
            if 'token_info' in token_data and 'ticker' in token_data['token_info']:
                ticker = token_data['token_info']['ticker']
            
            # Добавляем кнопку для токена
            keyboard.append([
                InlineKeyboardButton(
                    f"{idx}. {ticker}",
                    callback_data=f"hide_token:{token_query}"
                )
            ])
        
        # Добавляем навигационные кнопки, если страниц больше одной
        nav_buttons = []
        
        if total_pages > 1:
            # Кнопка предыдущей страницы
            prev_page = (page - 1) % total_pages
            nav_buttons.append(InlineKeyboardButton(
                "⬅️ Назад",
                callback_data=f"clear_selective:{prev_page}"
            ))
            
            # Кнопка следующей страницы
            next_page = (page + 1) % total_pages
            nav_buttons.append(InlineKeyboardButton(
                "Вперёд ➡️",
                callback_data=f"clear_selective:{next_page}"
            ))
        
        # Добавляем навигационные кнопки в клавиатуру
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Добавляем кнопку отмены
        keyboard.append([
            InlineKeyboardButton("↩️ Вернуться", callback_data="clear_return")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Обновляем сообщение
        await query.edit_message_text(
            f"Выберите токен для скрытия (страница {page + 1}/{total_pages}):\n\n"
            "Выбранные токены будут скрыты и не будут отображаться в списке, "
            "но сохранятся в базе данных.\n",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        await query.answer()
        debug_logger.info(f"Отображен список токенов для выборочного скрытия (страница {page + 1}/{total_pages})")
    except Exception as e:
        debug_logger.error(f"Ошибка при выборочном скрытии: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")
        except:
            pass

async def handle_hide_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает запрос на скрытие конкретного токена."""
    query = update.callback_query
    
    try:
        # Извлекаем запрос токена из callback_data
        _, token_query = query.data.split(":", 1)
        
        # Скрываем токен
        success = token_storage.hide_token(token_query)
        
        if success:
            # Получаем тикер для отображения в сообщении
            token_data = token_storage.get_token_data(token_query)
            ticker = "Неизвестно"
            if token_data and 'token_info' in token_data and 'ticker' in token_data['token_info']:
                ticker = token_data['token_info']['ticker']
            
            await query.answer(f"Токен {ticker} скрыт")
            debug_logger.info(f"Токен {token_query} ({ticker}) скрыт")
            
            # Возвращаемся к списку выборочного удаления
            await handle_clear_selective(update, context)
        else:
            await query.answer("Не удалось скрыть токен")
            debug_logger.warning(f"Не удалось скрыть токен {token_query}")
    except Exception as e:
        debug_logger.error(f"Ошибка при скрытии токена: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка при скрытии токена")
        except:
            pass

async def handle_manage_hidden(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает запрос на управление скрытыми токенами."""
    query = update.callback_query
    page = 0
    
    try:
        # Извлекаем номер страницы из callback_data, если он есть
        if ":" in query.data:
            _, page = query.data.split(":", 1)
            page = int(page)
        
        # Получаем скрытые токены
        hidden_tokens = token_storage.get_hidden_tokens()
        
        if not hidden_tokens:
            await query.edit_message_text(
                "У вас нет скрытых токенов.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("↩️ Вернуться", callback_data="clear_return")
                ]])
            )
            await query.answer()
            return
        
        # Формируем список токенов
        tokens_list = list(hidden_tokens.items())
        tokens_count = len(tokens_list)
        
        # Настройки пагинации
        tokens_per_page = 5
        total_pages = (tokens_count + tokens_per_page - 1) // tokens_per_page  # округление вверх
        
        # Проверяем, что страница в допустимых пределах
        if page >= total_pages:
            page = 0
        
        # Получаем токены для текущей страницы
        start_idx = page * tokens_per_page
        end_idx = min(start_idx + tokens_per_page, tokens_count)
        page_tokens = tokens_list[start_idx:end_idx]
        
        # Создаем кнопки для выбора токенов
        keyboard = []
        
        for idx, (token_query, token_data) in enumerate(page_tokens, start=start_idx + 1):
            # Получаем тикер для отображения
            ticker = "Неизвестно"
            if 'token_info' in token_data and 'ticker' in token_data['token_info']:
                ticker = token_data['token_info']['ticker']
            
            # Добавляем кнопку для токена
            keyboard.append([
                InlineKeyboardButton(
                    f"{idx}. {ticker} (восстановить)",
                    callback_data=f"unhide_token:{token_query}"
                )
            ])
        
        # Добавляем навигационные кнопки, если страниц больше одной
        nav_buttons = []
        
        if total_pages > 1:
            # Кнопка предыдущей страницы
            prev_page = (page - 1) % total_pages
            nav_buttons.append(InlineKeyboardButton(
                "⬅️ Назад",
                callback_data=f"manage_hidden:{prev_page}"
            ))
            
            # Кнопка следующей страницы
            next_page = (page + 1) % total_pages
            nav_buttons.append(InlineKeyboardButton(
                "Вперёд ➡️",
                callback_data=f"manage_hidden:{next_page}"
            ))
        
        # Добавляем навигационные кнопки в клавиатуру
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Добавляем кнопку отмены
        keyboard.append([
            InlineKeyboardButton("↩️ Вернуться", callback_data="clear_return")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Обновляем сообщение
        await query.edit_message_text(
            f"Скрытые токены (страница {page + 1}/{total_pages}):\n\n"
            "Выберите токен для восстановления:\n",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        await query.answer()
        debug_logger.info(f"Отображен список скрытых токенов (страница {page + 1}/{total_pages})")
    except Exception as e:
        debug_logger.error(f"Ошибка при управлении скрытыми токенами: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")
        except:
            pass

async def handle_unhide_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает запрос на восстановление скрытого токена."""
    query = update.callback_query
    
    try:
        # Извлекаем запрос токена из callback_data
        _, token_query = query.data.split(":", 1)
        
        # Восстанавливаем токен
        success = token_storage.unhide_token(token_query)
        
        if success:
            # Получаем тикер для отображения в сообщении
            token_data = token_storage.get_token_data(token_query)
            ticker = "Неизвестно"
            if token_data and 'token_info' in token_data and 'ticker' in token_data['token_info']:
                ticker = token_data['token_info']['ticker']
            
            await query.answer(f"Токен {ticker} восстановлен")
            debug_logger.info(f"Токен {token_query} ({ticker}) восстановлен")
            
            # Возвращаемся к списку скрытых токенов
            await handle_manage_hidden(update, context)
        else:
            await query.answer("Не удалось восстановить токен")
            debug_logger.warning(f"Не удалось восстановить токен {token_query}")
    except Exception as e:
        debug_logger.error(f"Ошибка при восстановлении токена: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка при восстановлении токена")
        except:
            pass

async def handle_clear_return(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает запрос на возврат к основному меню управления токенами."""
    query = update.callback_query
    
    try:
        # Создаем основные кнопки меню управления
        keyboard = [
            [InlineKeyboardButton("⛔ Удалить все", callback_data="delete_all_confirm")],
            [InlineKeyboardButton("🔍 Выборочное удаление", callback_data="delete_selective")],
            [InlineKeyboardButton("🙈 Скрыть все", callback_data="clear_all_confirm")],
            [InlineKeyboardButton("📋 Выборочное скрытие", callback_data="clear_selective")],
            [InlineKeyboardButton("🕵️ Управление скрытыми", callback_data="manage_hidden")],
            [InlineKeyboardButton("❌ Отмена", callback_data="clear_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Получаем число токенов
        visible_tokens_count = len(token_storage.get_all_tokens(include_hidden=False))
        hidden_tokens_count = len(token_storage.get_hidden_tokens())
        
        # Обновляем сообщение
        await query.edit_message_text(
            f"Выберите действие для токенов (активных: {visible_tokens_count}, скрытых: {hidden_tokens_count}):\n\n"
            "⛔ *Удалить все* - удалит все активные токены полностью.\n"
            "🔍 *Выборочное удаление* - позволит выбрать токены для удаления.\n"
            "🙈 *Скрыть все* - скроет все токены (они останутся в базе).\n"
            "📋 *Выборочное скрытие* - позволит выбрать токены для скрытия.\n"
            "🕵️ *Управление скрытыми* - управление скрытыми токенами.\n"
            "❌ *Отмена* - отменить операцию.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        await query.answer()
        debug_logger.info("Возврат к основному меню управления токенами")
    except Exception as e:
        debug_logger.error(f"Ошибка при возврате к меню: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")
        except:
            pass

async def handle_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает подтверждение полного удаления всех токенов."""
    query = update.callback_query
    
    try:
        # Логируем действие
        debug_logger.info("Подтверждено полное удаление всех токенов")
        
        # Получаем число токенов перед удалением (для логирования)
        tokens_count = len(token_storage.get_all_tokens(include_hidden=True))
        
        # Полностью удаляем все токены
        deleted_count = token_storage.delete_all_tokens()
        
        # Обновляем сообщение
        await query.edit_message_text(
            f"✅ *Все токены удалены ({deleted_count} шт.)*\n\n"
            "Они полностью удалены из базы данных и не могут быть восстановлены.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        await query.answer("Токены успешно удалены")
        debug_logger.info(f"Удалены все токены ({deleted_count} шт.)")
    except Exception as e:
        debug_logger.error(f"Ошибка при подтверждении удаления токенов: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка при удалении токенов.")
        except:
            pass

async def handle_delete_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает запрос на полное удаление всех токенов."""
    query = update.callback_query
    
    try:
        # Создаем кнопки для подтверждения
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, удалить все", callback_data="delete_confirm"),
                InlineKeyboardButton("❌ Отмена", callback_data="clear_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Получаем число токенов
        tokens_count = len(token_storage.get_all_tokens(include_hidden=True))
        
        # Обновляем сообщение с запросом подтверждения
        await query.edit_message_text(
            f"Вы уверены, что хотите полностью удалить *все* токены? ({tokens_count} шт.)\n\n"
            "⚠️ Это действие нельзя отменить. Все данные будут полностью удалены из базы данных.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        await query.answer()
        debug_logger.info(f"Запрос подтверждения полного удаления всех токенов ({tokens_count} шт.)")
    except Exception as e:
        debug_logger.error(f"Ошибка при запросе подтверждения удаления: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")
        except:
            pass

async def handle_delete_selective(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает запрос на выборочное удаление токенов."""
    query = update.callback_query
    page = 0
    
    try:
        # Извлекаем номер страницы из callback_data, если он есть
        if ":" in query.data:
            _, page = query.data.split(":", 1)
            page = int(page)
        
        # Получаем все токены (включая скрытые)
        tokens = token_storage.get_all_tokens(include_hidden=True)
        
        if not tokens:
            await query.edit_message_text(
                "Нет токенов для удаления.",
                parse_mode=ParseMode.MARKDOWN
            )
            await query.answer()
            return
        
        # Формируем список токенов
        tokens_list = list(tokens.items())
        tokens_count = len(tokens_list)
        
        # Настройки пагинации
        tokens_per_page = 5
        total_pages = (tokens_count + tokens_per_page - 1) // tokens_per_page  # округление вверх
        
        # Проверяем, что страница в допустимых пределах
        if page >= total_pages:
            page = 0
        
        # Получаем токены для текущей страницы
        start_idx = page * tokens_per_page
        end_idx = min(start_idx + tokens_per_page, tokens_count)
        page_tokens = tokens_list[start_idx:end_idx]
        
        # Создаем кнопки для выбора токенов
        keyboard = []
        
        for idx, (token_query, token_data) in enumerate(page_tokens, start=start_idx + 1):
            # Получаем тикер для отображения
            ticker = "Неизвестно"
            if 'token_info' in token_data and 'ticker' in token_data['token_info']:
                ticker = token_data['token_info']['ticker']
            
            # Добавляем статус токена (скрытый или обычный)
            status = " (скрыт)" if token_data.get('hidden', False) else ""
            
            # Добавляем кнопку для токена
            keyboard.append([
                InlineKeyboardButton(
                    f"{idx}. {ticker}{status}",
                    callback_data=f"delete_token:{token_query}"
                )
            ])
        
        # Добавляем навигационные кнопки, если страниц больше одной
        nav_buttons = []
        
        if total_pages > 1:
            # Кнопка предыдущей страницы
            prev_page = (page - 1) % total_pages
            nav_buttons.append(InlineKeyboardButton(
                "⬅️ Назад",
                callback_data=f"delete_selective:{prev_page}"
            ))
            
            # Кнопка следующей страницы
            next_page = (page + 1) % total_pages
            nav_buttons.append(InlineKeyboardButton(
                "Вперёд ➡️",
                callback_data=f"delete_selective:{next_page}"
            ))
        
        # Добавляем навигационные кнопки в клавиатуру
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Добавляем кнопку отмены
        keyboard.append([
            InlineKeyboardButton("↩️ Вернуться", callback_data="clear_return")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Обновляем сообщение
        await query.edit_message_text(
            f"Выберите токен для удаления (страница {page + 1}/{total_pages}):\n\n"
            "⚠️ Выбранные токены будут полностью удалены из базы данных. "
            "Это действие нельзя отменить.\n",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        await query.answer()
        debug_logger.info(f"Отображен список токенов для выборочного удаления (страница {page + 1}/{total_pages})")
    except Exception as e:
        debug_logger.error(f"Ошибка при выборочном удалении: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")
        except:
            pass

async def handle_delete_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает запрос на удаление конкретного токена."""
    query = update.callback_query
    
    try:
        # Извлекаем запрос токена из callback_data
        _, token_query = query.data.split(":", 1)
        
        # Получаем тикер для отображения в сообщении
        token_data = token_storage.get_token_data(token_query)
        ticker = "Неизвестно"
        if token_data and 'token_info' in token_data and 'ticker' in token_data['token_info']:
            ticker = token_data['token_info']['ticker']
        
        # Удаляем токен
        success = token_storage.delete_token(token_query)
        
        if success:
            await query.answer(f"Токен {ticker} удален")
            debug_logger.info(f"Токен {token_query} ({ticker}) удален")
            
            # Проверяем, остались ли еще токены перед возвратом к списку
            remaining_tokens = token_storage.get_all_tokens(include_hidden=True)
            if not remaining_tokens:
                # Если токенов больше нет, показываем сообщение об этом
                await query.edit_message_text(
                    "Все токены были удалены. Список пуст.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
                
            # Возвращаемся к списку выборочного удаления
            await handle_delete_selective(update, context)
        else:
            await query.answer("Не удалось удалить токен")
            debug_logger.warning(f"Не удалось удалить токен {token_query}")
    except Exception as e:
        debug_logger.error(f"Ошибка при удалении токена: {str(e)}")
        debug_logger.error(traceback.format_exc())
        try:
            await query.answer("Произошла ошибка при удалении токена")
        except:
            pass

async def setup_bot_commands(application) -> None:
    """Устанавливает список команд бота с описаниями."""
    try:
        # Добавляем команду excel
        commands = [
            BotCommand("start", "запустить бота"),
            BotCommand("help", "показать справку"),
            BotCommand("list", "показать список отслеживаемых токенов"),
            BotCommand("excel", "сформировать Excel-файл со всеми данными"),
            BotCommand("clear", "удалить/управлять токенами")
        ]
        
        await application.bot.set_my_commands(commands)
        debug_logger.info("Команды бота успешно настроены")
    except Exception as e:
        debug_logger.error(f"Ошибка при настройке команд бота: {str(e)}")
        debug_logger.error(traceback.format_exc())

def setup_commands_direct(token):
    """Устанавливает команды бота напрямую через HTTP API."""
    try:
        import requests
        
        # Добавляем команду excel
        commands = [
            {"command": "start", "description": "запустить бота"},
            {"command": "help", "description": "показать справку"},
            {"command": "list", "description": "показать список отслеживаемых токенов"},
            {"command": "excel", "description": "сформировать Excel-файл со всеми данными"},
            {"command": "clear", "description": "удалить/управлять токенами"}
        ]
        
        url = f"https://api.telegram.org/bot{token}/setMyCommands"
        response = requests.post(url, json={"commands": commands})
        
        if response.status_code == 200 and response.json().get("ok"):
            debug_logger.info("Команды бота успешно настроены напрямую через API")
        else:
            debug_logger.error(f"Ошибка при настройке команд бота через API: {response.text}")
    except Exception as e:
        debug_logger.error(f"Ошибка при настройке команд бота через API: {str(e)}")
        debug_logger.error(traceback.format_exc())
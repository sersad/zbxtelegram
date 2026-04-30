#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zabbix Telegram Bot Callback Handler
Обработчик колбэков для интерактивных кнопок в уведомлениях Zabbix
"""
import asyncio
import logging
import sys
import ssl
from datetime import datetime


import warnings
warnings.filterwarnings("ignore", message=".*model_custom_emoji_id.*")

# ГЛОБАЛЬНОЕ ОТКЛЮЧЕНИЕ ПРОВЕРКИ SSL (для самоподписанных сертификатов)
ssl._create_default_https_context = ssl._create_unverified_context

# Импорт конфигурации
from zbxTelegram_config import *

# Aiogram
from aiogram import Bot, Dispatcher
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, BufferedInputFile
from aiogram.filters import Filter
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

# Aiozabbix
from aiozabbix import ZabbixAPI
from aiozabbix import ZabbixAPIException

# aiohttp для прокси
import aiohttp
from aiohttp import TCPConnector

# FSM импорты
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

# Логирование
log_format = logging.Formatter(
    '[%(asctime)s] - PID:%(process)s - %(funcName)s() - %(filename)s:%(lineno)d - %(levelname)s: %(message)s'
)
logger = logging.getLogger('zbxTelegramBot')
logger.setLevel(logging.DEBUG if config_debug_mode else logging.INFO)

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(log_format)
logger.addHandler(stdout_handler)

try:
    file_handler = logging.FileHandler(filename=config_log_file, mode='a')
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)
except PermissionError as e:
    logger.error(f"Cannot write to log file {config_log_file}: {e}")


# def remove_button_by_action(original_markup, action_prefix):
#     """
#     Удаляет кнопку из клавиатуры по префиксу действия в callback_data.
#     Например: action_prefix='a:' удалит кнопку подтверждения ✅
#     """
#     if not original_markup or not original_markup.inline_keyboard:
#         return None

#     new_rows = []
#     for row in original_markup.inline_keyboard:
#         # Фильтруем кнопки: оставляем только те, у которых callback_data НЕ начинается с указанного префикса
#         new_row = [
#             btn for btn in row
#             if not (btn.callback_data and btn.callback_data.startswith(action_prefix))
#         ]
#         if new_row:  # Сохраняем только непустые строки
#             new_rows.append(new_row)

#     # Если все кнопки удалены — возвращаем None (убираем клавиатуру полностью)
#     if not new_rows:
#         return None

#     return InlineKeyboardMarkup(inline_keyboard=new_rows)

def remove_button_by_action(original_markup, action_prefix):
    """Удаляет кнопку из клавиатуры по префиксу действия в callback_data"""
    if not original_markup or not original_markup.inline_keyboard:
        return None

    new_rows = []
    for row in original_markup.inline_keyboard:
        new_row = [
            btn for btn in row
            if not (hasattr(btn, 'callback_data') and btn.callback_data and btn.callback_data.startswith(action_prefix))
        ]
        if new_row:
            new_rows.append(new_row)

    return InlineKeyboardMarkup(inline_keyboard=new_rows) if new_rows else None



# Состояния для подтверждения с комментарием
class AcknowledgeStates(StatesGroup):
    waiting_for_comment = State()  # Ожидание ввода комментария


class CallbackFilter(Filter):
    """Фильтр для колбэков: <действие>:<eventid>"""
    def __init__(self, action: str):
        self.action = action

    async def __call__(self, callback: CallbackQuery) -> bool | dict:
        if not callback.data:  # ИСПРАВЛЕНО: .data вместо .
            return False
        parts = callback.data.split(':')
        if len(parts) >= 2 and parts[0] == self.action:
            return {'eventid': parts[1], 'extra': parts[2:] if len(parts) > 2 else []}
        return False


async def init_zabbix():
    """Инициализация Zabbix API с отключенной проверкой SSL для самоподписанных сертификатов"""
    # Создаем SSL контекст без проверки сертификатов
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # Создаем коннектор с отключенной проверкой SSL
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    # Создаем сессию с этим коннектором
    session = aiohttp.ClientSession(connector=connector)

    # # Простая сессия без прокси для Zabbix (прокси настраивается на уровне ОС/окружения)
    # session = aiohttp.ClientSession()

    zapi = ZabbixAPI(zabbix_api_url, client_session=session)

    try:
        await zapi.login(zabbix_api_login, password=zabbix_api_pass)
        logger.info(f"Successfully authenticated to Zabbix API at {zabbix_api_url}")
        return zapi, session
    except Exception as e:
        logger.error(f"Failed to authenticate to Zabbix API: {e}", exc_info=True)
        await session.close()
        await connector.close()  # ← Важно: закрываем и коннектор тоже
        return None, None


async def auto_cancel_acknowledge(state: FSMContext, chat_id: int, message_id: int, bot: Bot, eventid: str):
    """Автоматическая отмена подтверждения через 3 минуты бездействия"""
    try:
        # Ждём 3 минуты (180 секунд)
        await asyncio.sleep(180)

        # Проверяем, всё ещё ли пользователь в состоянии ожидания комментария
        current_state = await state.get_state()
        if current_state == AcknowledgeStates.waiting_for_comment.state:
            # Сбрасываем состояние
            await state.clear()

            # Отправляем уведомление об отмене
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"⏰ Подтверждение события #{eventid} отменено автоматически (таймаут 3 минуты истёк)"
                )
                logger.info(f"Auto-cancelled acknowledge for event {eventid} due to timeout (180s)")
            except Exception as e:
                logger.warning(f"Could not send auto-cancel notification: {e}")
    except asyncio.CancelledError:
        # Задача была отменена (пользователь ввёл комментарий или нажал отмену)
        pass
    except Exception as e:
        logger.error(f"Error in auto_cancel_acknowledge: {e}")


async def handle_acknowledge(callback: CallbackQuery, eventid: str, state: FSMContext, zapi, bot):
    """Запрос комментария перед подтверждением события"""
    try:
        await callback.answer()

        # Получаем событие
        events = await zapi.event.get(
            eventids=[int(eventid)],
            output=["eventid", "value", "acknowledged", "r_eventid"],
            selectHosts=["name"]
        )

        if not events:
            await callback.message.answer("❌ Событие не найдено")
            logger.warning(f"Event {eventid} not found")
            return

        event = events[0]
        host_name = event.get('hosts', [{}])[0].get('name', 'N/A') if event.get('hosts') else 'N/A'

        # Проверки статуса
        if event.get('r_eventid') and event['r_eventid'] != '0':
            await callback.message.answer(f"ℹ️ Проблема уже восстановлена\nХост: {host_name}")
            return
        if event['value'] == '0':
            await callback.message.answer(f"ℹ️ Событие уже восстановлено\nХост: {host_name}")
            return
        if event.get('acknowledged') == '1':
            await callback.message.answer(f"ℹ️ Событие уже подтверждено ранее\nХост: {host_name}")
            return

        # Сохраняем контекст для последующего подтверждения
        await state.update_data(
            eventid=eventid,
            host_name=host_name,
            original_message_text=callback.message.text or callback.message.caption,
            original_reply_markup=callback.message.reply_markup,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id
        )

        # Кнопка отмены
        cancel_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_ack:{eventid}")]
        ])

        await callback.message.answer(
            f"📝 Введите комментарий для подтверждения события #{eventid}:\n\n"
            "<i>Минимум 3 символа. У вас есть 3 минуты на ввод.</i>",
            reply_markup=cancel_markup,
            parse_mode="HTML"
        )

        # Запускаем таймаут-задачу
        timeout_task = asyncio.create_task(
            auto_cancel_acknowledge(
                state=state,
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                bot=bot,
                eventid=eventid
            )
        )

        # Сохраняем задачу в состоянии для возможности отмены
        await state.update_data(timeout_task=timeout_task)

        await state.set_state(AcknowledgeStates.waiting_for_comment)
        logger.info(f"User {callback.from_user.id} ({callback.from_user.full_name}) entered comment input mode for event {eventid}")

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)[:80]}")
        logger.error(f"Error in handle_acknowledge init: {e}", exc_info=True)
        await state.clear()


async def process_acknowledge_comment(message: Message, state: FSMContext, zapi, bot):
    """Обработка введённого комментария и подтверждение события"""
    try:
        data = await state.get_data()

        # Отменяем таймаут-задачу (если ещё активна)
        timeout_task = data.get('timeout_task')
        if timeout_task and not timeout_task.done():
            timeout_task.cancel()
            logger.debug(f"Cancelled timeout task for event {data['eventid']}")

        eventid = data['eventid']
        host_name = data['host_name']
        original_text = data['original_message_text']
        original_markup = data['original_reply_markup']
        chat_id = data['chat_id']
        message_id = data['message_id']
        user_comment = message.text.strip()

        # Валидация комментария
        if not user_comment or len(user_comment) < 3:
            await message.answer(
                "⚠️ Комментарий должен содержать минимум 3 символа.\n"
                "Повторите ввод или нажмите «Отмена»."
            )
            return

        # Формируем полный комментарий для Zabbix
        full_comment = (
            f"{user_comment}\n\n"
            f"Acknowledged via Telegram by {message.from_user.full_name} "
            f"(@{message.from_user.username or 'N/A'})"
        )

        # Подтверждаем в Zabbix
        await zapi.event.acknowledge(
            eventids=[int(eventid)],
            action=6,
            message=full_comment
        )

        # Формируем текст подтверждения
        ack_text = (
            f"\n\n✅ Подтверждено: {message.from_user.full_name}\n"
            f"💬 {user_comment}\n"
            f"Хост: {host_name}"
        )

        # Обновляем исходное сообщение (удаляем только кнопку ✅)
        new_markup = remove_button_by_action(original_markup, 'a:')

        try:
            if original_text:  # Текстовое сообщение
                new_text = (original_text + ack_text)[:4096]
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=new_text,
                    reply_markup=new_markup,
                    parse_mode="HTML"
                )
            else:  # Медиа с подписью
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=(original_text + ack_text)[:1024],
                    reply_markup=new_markup,
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.warning(f"Could not update original message {message_id}: {e}")
            await message.answer(
                f"✅ Событие #{eventid} подтверждено!\n"
                f"💬 {user_comment}\n"
                f"Хост: {host_name}"
            )

        # Подтверждение пользователю
        await message.answer("✅ Комментарий добавлен к событию")
        logger.info(f"Event {eventid} acknowledged by user {message.from_user.id} with comment: {user_comment[:50]}...")
        await state.clear()

    except Exception as e:
        await message.answer(f"❌ Ошибка подтверждения: {str(e)[:80]}")
        logger.error(f"Error processing acknowledge comment for event {eventid}: {e}", exc_info=True)
        await state.clear()


async def cancel_acknowledge(callback: CallbackQuery, state: FSMContext):
    """Отмена операции подтверждения"""
    try:
        data = await state.get_data()

        # Отменяем таймаут-задачу
        timeout_task = data.get('timeout_task')
        if timeout_task and not timeout_task.done():
            timeout_task.cancel()
            logger.debug(f"Cancelled timeout task on manual cancel")

        await state.clear()
        parts = callback.data.split(':', 1)
        eventid = parts[1] if len(parts) > 1 else 'N/A'
        await callback.message.edit_text(
            f"❌ Подтверждение события #{eventid} отменено",
            reply_markup=None
        )
        logger.info(f"User {callback.from_user.id} cancelled acknowledge for event {eventid}")
        await callback.answer("Отменено", show_alert=False)
    except Exception as e:
        logger.error(f"Error in cancel_acknowledge: {e}")
        try:
            await callback.answer("Ошибка при отмене", show_alert=True)
        except:
            pass


# async def handle_acknowledge(callback: CallbackQuery, eventid: str, zapi):
#     """Подтверждение события БЕЗ закрытия (action=6 = подтверждение + сообщение)"""
#     try:
#         await callback.answer()

#         # Получаем событие (числовой формат!)
#         events = await zapi.event.get(
#             eventids=[int(eventid)],
#             output=["eventid", "value", "acknowledged", "r_eventid"],
#             selectHosts=["name"]
#         )

#         if not events:
#             await callback.message.answer("❌ Событие не найдено")
#             logger.warning(f"Event {eventid} not found")
#             return

#         event = events[0]
#         host_name = event.get('hosts', [{}])[0].get('name', 'N/A') if event.get('hosts') else 'N/A'

#         # Проверка 1: событие уже восстановлено (есть событие восстановления)
#         if event.get('r_eventid') and event['r_eventid'] != '0':
#             await callback.message.answer(f"ℹ️ Проблема уже восстановлена\nХост: {host_name}")
#             logger.info(f"Event {eventid} already resolved (r_eventid={event['r_eventid']})")
#             return

#         # Проверка 2: событие закрыто (value=0)
#         if event['value'] == '0':
#             await callback.message.answer(f"ℹ️ Событие уже восстановлено\nХост: {host_name}")
#             logger.info(f"Event {eventid} value=0")
#             return

#         # Проверка 3: уже подтверждено
#         if event.get('acknowledged') == '1':
#             await callback.message.answer(f"ℹ️ Событие уже подтверждено ранее\nХост: {host_name}")
#             logger.info(f"Event {eventid} already acknowledged")
#             return

#         # === ПОДТВЕРЖДЕНИЕ БЕЗ ЗАКРЫТИЯ (action=6) ===
#         try:
#             # action=6 = 2 (подтверждение) + 4 (сообщение)
#             result = await zapi.event.acknowledge(
#                 eventids=[int(eventid)],
#                 action=6,
#                 message=f"Acknowledged via Telegram by {callback.from_user.full_name} (@{callback.from_user.username or 'N/A'})"
#             )

#             # === УДАЛЕНИЕ ТОЛЬКО КНОПКИ ✅ (префикс 'a:') ===
#             original_markup = callback.message.reply_markup
#             new_rows = []

#             # Формируем новую клавиатуру без кнопки подтверждения
#             if original_markup and hasattr(original_markup, 'inline_keyboard') and original_markup.inline_keyboard:
#                 for row in original_markup.inline_keyboard:
#                     # Оставляем все кнопки, кроме тех, у которых callback_data начинается с 'a:'
#                     new_row = [
#                         btn for btn in row
#                         if not (hasattr(btn, 'callback_data') and btn.callback_data and btn.callback_data.startswith('a:'))
#                     ]
#                     if new_row:  # Сохраняем только непустые строки
#                         new_rows.append(new_row)

#             # Создаём новую клавиатуру (или None если все кнопки удалены)
#             new_markup = InlineKeyboardMarkup(inline_keyboard=new_rows) if new_rows else None

#             # Формируем текст подтверждения
#             ack_text = f"\n\n✅ Подтверждено: {callback.from_user.full_name}\nХост: {host_name}"

#             # Случай 1: текстовое сообщение
#             if callback.message.text:
#                 new_text = (callback.message.text + ack_text)[:4096]
#                 await callback.message.edit_text(
#                     new_text,
#                     reply_markup=new_markup,  # ← Клавиатура БЕЗ кнопки ✅, остальные кнопки сохранены
#                     parse_mode="HTML"
#                 )

#             # Случай 2: медиа-сообщение (изображение/видео) с подписью
#             elif callback.message.caption:
#                 new_caption = (callback.message.caption + ack_text)[:1024]
#                 await callback.message.edit_caption(
#                     caption=new_caption,
#                     reply_markup=new_markup,  # ← Клавиатура БЕЗ кнопки ✅
#                     parse_mode="HTML"
#                 )

#             # Случай 3: сообщение без текста и подписи (крайне редко)
#             else:
#                 await callback.message.answer(
#                     f"✅ Событие #{eventid} подтверждено пользователем {callback.from_user.full_name}\nХост: {host_name}",
#                     reply_markup=None
#                 )

#             logger.info(f"Event {eventid} acknowledged (action=6) by user {callback.from_user.id}")

#         except ZabbixAPIException as e:
#             error_code = e.args[1] if len(e.args) > 1 else None
#             error_msg = e.args[0] if e.args else "Unknown error"

#             # Проверка после ошибки (гонка условий)
#             post_check = await zapi.event.get(
#                 eventids=[int(eventid)],
#                 output=["acknowledged", "r_eventid", "value"]
#             )

#             if post_check:
#                 post_event = post_check[0]
#                 if post_event.get('acknowledged') == '1':
#                     await callback.message.answer(f"✅ Событие уже подтверждено\nХост: {host_name}")
#                     logger.info(f"Event {eventid} already acknowledged (race condition)")
#                 elif post_event.get('r_eventid') and post_event['r_eventid'] != '0':
#                     await callback.message.answer(f"ℹ️ Проблема восстановилась до подтверждения\nХост: {host_name}")
#                     logger.info(f"Event {eventid} resolved during acknowledge")
#                 elif error_code == -32500 and 'manual closing' in str(error_msg).lower():
#                     await callback.message.answer(
#                         f"⚠️ Ошибка: попытка закрытия проблемы запрещена триггером.\n"
#                         f"Исправлено: теперь используется действие 'Подтвердить' (без закрытия).\n"
#                         f"Хост: {host_name}"
#                     )
#                     logger.error(f"Event {eventid} failed with action=1 — must use action=6")
#                 else:
#                     await callback.message.answer(f"❌ Ошибка Zabbix API ({error_code}): {str(error_msg)[:70]}")
#                     logger.error(f"Zabbix API error for event {eventid}: {e}", exc_info=True)
#             else:
#                 await callback.message.answer("❌ Событие удалено из системы")
#                 logger.warning(f"Event {eventid} disappeared")

#     except ValueError as e:
#         await callback.message.answer(f"❌ Неверный формат ID события: {eventid}")
#         logger.error(f"Invalid eventid format '{eventid}': {e}")
#     except Exception as e:
#         await callback.message.answer(f"❌ Внутренняя ошибка: {str(e)[:80]}")
#         logger.error(f"Unexpected error for event {eventid}: {e}", exc_info=True)


async def handle_messages(callback: CallbackQuery, eventid: str, zapi):
    """Показать сообщения/комментарии к событию с проверкой существования"""
    try:
        await callback.answer()

        # Проверка существования события
        events = await zapi.event.get(
            eventids=[eventid],
            output=["eventid"],
            select_acknowledges="extend"
        )

        if not events:
            await callback.message.answer("❌ Событие не найдено")
            logger.warning(f"Event {eventid} not found for messages request")
            return

        event = events[0]
        acks = event.get('acknowledges', [])

        if not acks:
            text = "📝 Нет комментариев к событию"
        else:
            comments = []
            for ack in sorted(acks, key=lambda x: int(x['clock']), reverse=True)[:5]:
                dt = datetime.fromtimestamp(int(ack['clock']))
                user = ack.get('alias', ack.get('name', 'Unknown'))
                msg = ack.get('message', '').strip() or '(без комментария)'
                comments.append(f"▫️ {dt.strftime('%Y-%m-%d %H:%M')} — {user}:\n   {msg}")

            text = "📝 Комментарии к событию:\n" + "\n\n".join(comments)

        await callback.message.answer(text, disable_notification=True)
        logger.info(f"Messages shown for event {eventid}")

    except ZabbixAPIException as e:
        error_code = e.args[1] if len(e.args) > 1 else None
        error_msg = e.args[0] if e.args else "Unknown error"
        await callback.message.answer(f"❌ Ошибка Zabbix API ({error_code}): {str(error_msg)[:80]}")
        logger.error(f"Zabbix API error for event {eventid} messages: {e}", exc_info=True)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка получения комментариев: {str(e)[:80]}")
        logger.error(f"Error getting messages for event {eventid}: {e}", exc_info=True)



async def handle_history(callback: CallbackQuery, eventid: str, zapi):
    """Показать историю события с ТЕКУЩИМ статусом проблемы"""
    try:
        await callback.answer()

        # Получаем событие с данными о восстановлении (числовой формат!)
        events = await zapi.event.get(
            eventids=[int(eventid)],  # ← ЧИСЛО
            output=["eventid", "clock", "value", "r_eventid", "objectid"],
            selectHosts=["hostid", "name"],
            selectRelatedObject=["description", "expression"]
        )

        if not events:
            await callback.message.answer("❌ Событие не найдено")
            logger.warning(f"Event {eventid} not found for history request")
            return

        event = events[0]
        host_name = event.get('hosts', [{}])[0].get('name', 'N/A') if event.get('hosts') else 'N/A'
        trigger_name = event.get('relatedObject', {}).get('description', 'N/A')
        event_time = datetime.fromtimestamp(int(event['clock'])).strftime('%Y-%m-%d %H:%M:%S')

        # Определяем ТЕКУЩИЙ статус проблемы
        current_status = "🔴 АКТИВНА"
        status_details = ""
        restore_time_str = ""

        r_eventid = event.get('r_eventid')
        if r_eventid and r_eventid != '0':
            # Проблема восстановлена — получаем время восстановления
            restore_events = await zapi.event.get(
                eventids=[int(r_eventid)],
                output=["clock", "value"]
            )
            if restore_events:
                restore_event = restore_events[0]
                restore_time = datetime.fromtimestamp(int(restore_event['clock'])).strftime('%Y-%m-%d %H:%M:%S')
                restore_time_str = restore_time
                current_status = "🟢 ВОССТАНОВЛЕНА"
                status_details = f"\nВремя восстановления: {restore_time}"
            else:
                current_status = "🟢 ВОССТАНОВЛЕНА (время неизвестно)"
        else:
            # Проверяем через problem.get для уверенности
            problems = await zapi.problem.get(
                eventids=[int(eventid)],
                output=["eventid"]
            )
            if not problems:
                current_status = "🟢 ВОССТАНОВЛЕНА (активная проблема не найдена)"

        # Формируем сообщение
        text = (
            f"📈 Событие #{eventid}\n"
            f"Текущий статус: {current_status}\n"
            f"Время события: {event_time}{status_details}\n"
            f"Хост: {host_name}\n"
            f"Триггер: {trigger_name}"
        )

        await callback.message.answer(text, disable_notification=True)
        logger.info(f"History shown for event {eventid} (current status: {current_status})")

    except ZabbixAPIException as e:
        error_code = e.args[1] if len(e.args) > 1 else None
        error_msg = e.args[0] if e.args else "Unknown error"
        await callback.message.answer(f"❌ Ошибка Zabbix API ({error_code}): {str(error_msg)[:80]}")
        logger.error(f"Zabbix API error for event {eventid} history: {e}", exc_info=True)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка получения истории: {str(e)[:80]}")
        logger.error(f"Error getting history for event {eventid}: {e}", exc_info=True)



async def handle_last_value(callback: CallbackQuery, eventid: str, zapi):
    """Показать последнее значение элемента данных с проверкой существования"""
    try:
        await callback.answer()

        # Получаем событие
        events = await zapi.event.get(
            eventids=[int(eventid)],  # ← ЧИСЛО
            output=["eventid", "clock", "value", "r_eventid", "objectid"],
            selectHosts=["hostid", "name"],
            selectRelatedObject=["description", "expression"]
        )

        if not events:
            await callback.message.answer("❌ Событие не найдено")
            logger.warning(f"Event {eventid} not found for last value request")
            return

        event = events[0]
        host_name = event.get('hosts', [{}])[0].get('name', 'N/A') if event.get('hosts') else 'N/A'
        trigger_name = event.get('relatedObject', {}).get('description', 'N/A')


        triggerid = events[0]['objectid']

        # Получаем элементы данных
        items = await zapi.item.get(
            triggerids=[triggerid],
            output=["name", "lastvalue", "lastclock", "units"],
            sortfield="name",
            limit=5
        )

        if not items:
            await callback.message.answer("ℹ️ Нет данных для отображения")
            return

        lines = [f"⏱ Последние значения для события #{eventid} {trigger_name} на {host_name}:"]
        for item in items:
            dt = datetime.fromtimestamp(int(item['lastclock'])) if item.get('lastclock') else None
            value = item.get('lastvalue', 'N/A')
            units = f" {item['units']}" if item.get('units') and item['units'] != 'unixtime' else ""
            time_str = f" ({dt.strftime('%H:%M:%S')})" if dt else ""
            lines.append(f"▫️ {item['name']}: {value}{units}{time_str}")

        await callback.message.answer("\n".join(lines), disable_notification=True)
        logger.info(f"Last values shown for event {eventid}")

    except ZabbixAPIException as e:
        error_code = e.args[1] if len(e.args) > 1 else None
        error_msg = e.args[0] if e.args else "Unknown error"
        await callback.message.answer(f"❌ Ошибка Zabbix API ({error_code}): {str(error_msg)[:80]}")
        logger.error(f"Zabbix API error for event {eventid} last value: {e}", exc_info=True)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка получения значений: {str(e)[:80]}")
        logger.error(f"Error getting last values for event {eventid}: {e}", exc_info=True)



async def handle_graphs(callback: CallbackQuery, eventid: str, extra: list, zapi):
    """Показать график (ссылка на график в Zabbix)"""
    try:
        await callback.answer()

        # Проверка существования события
        events = await zapi.event.get(
            eventids=[eventid],
            output=["eventid"]
        )

        if not events:
            await callback.message.answer("❌ Событие не найдено")
            logger.warning(f"Event {eventid} not found for graph request")
            return

        itemid = extra[0] if extra else None

        if itemid:
            # Формат URL: https://zabbix.tspd.local/history.php?action=showgraph&itemids%5B%5D=123456
            graph_url = f"{zabbix_api_url.rstrip('/')}/history.php?action=showgraph&itemids%5B%5D={itemid}"
            text = f"📊 График элемента данных:\n{graph_url}"
        else:
            # Ссылка на событие в интерфейсе Zabbix
            event_url = zabbix_event_link.format(
                zabbix_server=zabbix_api_url.rstrip('/'),
                eventid=eventid,
                triggerid='0'
            )
            text = f"📊 Открыть событие в Zabbix:\n{event_url}"

        await callback.message.answer(text, disable_web_page_preview=False)
        logger.info(f"Graph link sent for event {eventid}, itemid={itemid}")

    except ZabbixAPIException as e:
        error_code = e.args[1] if len(e.args) > 1 else None
        error_msg = e.args[0] if e.args else "Unknown error"
        await callback.message.answer(f"❌ Ошибка Zabbix API ({error_code}): {str(error_msg)[:80]}")
        logger.error(f"Zabbix API error for event {eventid} graph: {e}", exc_info=True)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка получения графика: {str(e)[:80]}")
        logger.error(f"Error getting graph for event {eventid}: {e}", exc_info=True)


async def handle_unknown(callback: CallbackQuery):
    """Обработчик неизвестных колбэков"""
    await callback.answer("❓ Неизвестная команда", show_alert=True)
    logger.warning(f"Unknown callback received: {callback.data}")


async def main():
    logger.info("Starting Zabbix Telegram Bot Callback Handler...")

    # Инициализация Zabbix
    zapi, zabbix_session = await init_zabbix()
    if not zapi:
        logger.critical("Cannot start bot without Zabbix API connection")
        return 1

    # # Настройка прокси для Telegram (простой вариант)
    # proxy_url = None
    # if tg_proxy and tg_proxy_server:
    #     if isinstance(tg_proxy_server, dict):
    #         proxy_url = next(iter(tg_proxy_server.values()))
    #     else:
    #         proxy_url = tg_proxy_server
    #     logger.info(f"Using proxy for Telegram API: {proxy_url}")

    # # Инициализация бота с хранилищем для FSM
    # bot_session = AiohttpSession(proxy=proxy_url) if proxy_url else AiohttpSession()
    # bot = Bot(token=tg_token, session=bot_session)

    # Настройка прокси для Telegram
    proxy_url = None
    if tg_proxy and tg_proxy_server:
        if isinstance(tg_proxy_server, dict):
            proxy_url = next(iter(tg_proxy_server.values()))
        else:
            proxy_url = tg_proxy_server
        logger.info(f"Using proxy for Telegram API: {proxy_url}")

    # SSL-контекст для самоподписанных сертификатов (используется и для кастомного сервера)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connector = TCPConnector(ssl=ssl_context)

    # Инициализация сессии с поддержкой кастомного API-сервера
    session_kwargs = {'connector': connector}
    if proxy_url:
        session_kwargs['proxy'] = proxy_url
    if tg_server_api:  # ← Поддержка кастомного сервера из config/env
        logger.info(f"Using custom Telegram API server: {tg_server_api}")
        local_server = TelegramAPIServer.from_base(tg_server_api)
        session_kwargs['api'] = local_server

    bot_session = AiohttpSession(**session_kwargs)
    bot = Bot(token=tg_token, session=bot_session)

    # Создаём диспетчер с MemoryStorage для FSM
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Проверка подключения
    try:
        me = await bot.get_me()
        logger.info(f"Bot @{me.username} (id={me.id}) started successfully")
    except Exception as e:
        logger.critical(f"Cannot connect to Telegram API: {e}", exc_info=True)
        await zabbix_session.close()
        await bot_session.close()
        return 1

    # Обработчик кнопки ✅ — запрос комментария (передаём bot!)
    @dp.callback_query(CallbackFilter(action="a"))
    async def cb_ack(callback: CallbackQuery, eventid: str, state: FSMContext):
        await handle_acknowledge(callback, eventid, state, zapi, bot)  # ← bot передан!

    # Обработчик текстового комментария (передаём bot!)
    @dp.message(AcknowledgeStates.waiting_for_comment)
    async def msg_comment(message: Message, state: FSMContext):
        await process_acknowledge_comment(message, state, zapi, bot)  # ← bot передан!

    # Обработчик отмены подтверждения
    @dp.callback_query(lambda c: c.data.startswith('cancel_ack:'))
    async def cb_cancel(callback: CallbackQuery, state: FSMContext):
        await cancel_acknowledge(callback, state)

    # Остальные кнопки (без изменений)
    @dp.callback_query(CallbackFilter(action="m"))
    async def cb_msg(callback: CallbackQuery, eventid: str):
        await handle_messages(callback, eventid, zapi)

    @dp.callback_query(CallbackFilter(action="h"))
    async def cb_hist(callback: CallbackQuery, eventid: str):
        await handle_history(callback, eventid, zapi)

    @dp.callback_query(CallbackFilter(action="l"))
    async def cb_last(callback: CallbackQuery, eventid: str):
        await handle_last_value(callback, eventid, zapi)

    @dp.callback_query(CallbackFilter(action="g"))
    async def cb_graph(callback: CallbackQuery, eventid: str, extra: list):
        await handle_graphs(callback, eventid, extra, zapi)

    # Обработчик неизвестных колбэков
    @dp.callback_query()
    async def cb_unknown(callback: CallbackQuery):
        await handle_unknown(callback)

    # Запуск
    logger.info("Bot is ready to receive callbacks...")
    try:
        await dp.start_polling(bot, handle_signals=True)
    finally:
        await bot_session.close()
        await zabbix_session.close()
        logger.info("Bot stopped gracefully")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)

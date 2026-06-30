from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from bot.database import async_session, User, UserRole
from sqlalchemy import select
from bot.services.logger import send_log

# Клавиатура создается здесь, чтобы она была доступна во всех функциях
main_keyboard = ReplyKeyboardMarkup([
    ["📅 Сегодня", "📆 Неделя"],
    ["➕ Встреча", "➕ Zoom встреча"],
    ["🔔 Уведомления", "📋 Добавить свой календарь"],
    ["🎥 Zoom календарь", "ℹ️ Помощь"],
    ["👥 Пользователи"]
], resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with async_session() as session:
        db_user = await session.get(User, user.id)
        if not db_user:
            role = UserRole.ADMIN if user.id == int(context.bot_data.get("admin_chat_id", 0)) else UserRole.USER
            db_user = User(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                role=role,
                is_approved=(role == UserRole.ADMIN)
            )
            session.add(db_user)
            await session.commit()

            await send_log(f"🆕 Новый пользователь: {user.first_name} (@{user.username}, ID: {user.id})")

            if role == UserRole.USER:
                await context.bot.send_message(
                    chat_id=context.bot_data["admin_chat_id"],
                    text=f"🔔 Новый пользователь:\n"
                         f"ID: {user.id}\n"
                         f"Имя: {user.first_name} {user.last_name or ''}\n"
                         f"Username: @{user.username}",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{user.id}"),
                            InlineKeyboardButton("🚫 Отклонить", callback_data=f"block_{user.id}")
                        ]
                    ])
                )
                await update.message.reply_text(
                    "👋 Здравствуйте! Ваш запрос отправлен администратору.\nОжидайте подтверждения.",
                    disable_web_page_preview=True
                )
            else:
                await update.message.reply_text(
                    "👑 Добро пожаловать, администратор!",
                    reply_markup=main_keyboard,
                    disable_web_page_preview=True
                )
        else:
            if db_user.is_blocked:
                await update.message.reply_text("⛔ Ваш аккаунт заблокирован.", disable_web_page_preview=True)
                return
            if not db_user.is_approved:
                await update.message.reply_text("⏳ Ожидайте подтверждения администратора.", disable_web_page_preview=True)
                return
            if db_user.role == UserRole.ADMIN:
                await update.message.reply_text("👑 С возвращением, администратор!", reply_markup=main_keyboard, disable_web_page_preview=True)
            else:
                await update.message.reply_text("👋 С возвращением!", reply_markup=main_keyboard, disable_web_page_preview=True)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    async with async_session() as session:
        admin = await session.get(User, user_id)
        if not admin or admin.role != UserRole.ADMIN:
            await query.edit_message_text("⛔ Недостаточно прав.")
            return

        data = query.data
        target_id = int(data.split("_")[1])
        target = await session.get(User, target_id)

        if not target:
            await query.edit_message_text("❌ Пользователь не найден.")
            return

        if data.startswith("approve_"):
            target.is_approved = True
            target.is_blocked = False
            await session.commit()
            await query.edit_message_text(f"✅ Пользователь {target_id} подтверждён.")
            await send_log(f"✅ Админ подтвердил пользователя {target_id}")
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="✅ Ваш аккаунт подтверждён!\nТеперь вы можете пользоваться ботом iCalendarPM.",
                    reply_markup=main_keyboard,
                    disable_web_page_preview=True
                )
            except:
                pass
        elif data.startswith("block_"):
            target.is_approved = False
            target.is_blocked = True
            await session.commit()
            await query.edit_message_text(f"🚫 Пользователь {target_id} заблокирован.")
            await send_log(f"🚫 Админ заблокировал пользователя {target_id}")


async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with async_session() as session:
        admin = await session.get(User, update.effective_user.id)
        if not admin or admin.role != UserRole.ADMIN:
            await update.message.reply_text("⛔ Недостаточно прав.")
            return
        if not context.args:
            await update.message.reply_text("Использование: /approve ID")
            return
        target = await session.get(User, int(context.args[0]))
        if target:
            target.is_approved = True
            target.is_blocked = False
            await session.commit()
            await update.message.reply_text(f"✅ Пользователь {context.args[0]} подтверждён.", disable_web_page_preview=True)
            await send_log(f"✅ Админ подтвердил пользователя {context.args[0]}")
            try:
                await context.bot.send_message(
                    chat_id=target.telegram_id,
                    text="✅ Ваш аккаунт подтверждён!\nТеперь вы можете пользоваться ботом iCalendarPM.",
                    reply_markup=main_keyboard,
                    disable_web_page_preview=True
                )
            except:
                pass


async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with async_session() as session:
        admin = await session.get(User, update.effective_user.id)
        if not admin or admin.role != UserRole.ADMIN:
            return
        target = await session.get(User, int(context.args[0])) if context.args else None
        if target:
            target.is_blocked = True
            await session.commit()
            await update.message.reply_text(f"🚫 {context.args[0]} заблокирован.", disable_web_page_preview=True)
            await send_log(f"🚫 Админ заблокировал пользователя {context.args[0]}")


async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with async_session() as session:
        admin = await session.get(User, update.effective_user.id)
        if not admin or admin.role != UserRole.ADMIN:
            return
        target = await session.get(User, int(context.args[0])) if context.args else None
        if target:
            target.is_blocked = False
            await session.commit()
            await update.message.reply_text(f"✅ {context.args[0]} разблокирован.", disable_web_page_preview=True)
            await send_log(f"✅ Админ разблокировал пользователя {context.args[0]}")


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with async_session() as session:
        admin = await session.get(User, update.effective_user.id)
        if not admin or admin.role != UserRole.ADMIN:
            await update.message.reply_text("⛔ Недостаточно прав.")
            return
        result = await session.execute(select(User))
        users = result.scalars().all()

        if not users:
            await update.message.reply_text("👥 Нет зарегистрированных пользователей.", disable_web_page_preview=True)
            return

        msg = "👥 Список пользователей:\n\n"
        for u in users:
            status = ""
            if u.role == UserRole.ADMIN:
                status = "👑 "
            elif u.is_approved and not u.is_blocked:
                status = "✅ "
            elif u.is_blocked:
                status = "🚫 "
            else:
                status = "⏳ "
            msg += f"{status}ID: {u.telegram_id} | @{u.username or 'нет'} | {u.first_name or ''}\n"

        await update.message.reply_text(msg, disable_web_page_preview=True)
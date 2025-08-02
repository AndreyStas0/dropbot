import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from database import (
    init_database, save_form_data, get_user_forms_count_sync,
    update_user_stats_sync, get_database_stats_sync, get_all_forms_sync,
    get_user_forms_sync, get_next_pending_form_sync, get_accepted_forms_sync,
    get_form_by_id_sync, update_form_status_sync, get_pending_forms_count_sync,
    get_username_by_user_id_sync, get_user_telegram_info_sync,
    get_all_user_ids_sync, get_user_email_count_sync, update_payment_status_sync,
    save_payment_card_sync, save_payment_receipt_sync, get_user_available_emails_limit,
    load_emails, save_emails, load_banks, save_banks)
from config import BOT_TOKEN, ADMIN_IDS, CHAT_ID

# Support multiple admins
ADMIN_ID = ADMIN_IDS[0] if ADMIN_IDS else 6995773690  # Backward compatibility

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Constants
# MAX_EMAILS_LIMIT is now dynamic based on formula: 3 + (forms_count * 3)
user_email_state = {}
user_states = {}  # For payment states
users_ids = set()

# Initialize PostgreSQL database
# Database initialization will be done async in main()


class FormStates(StatesGroup):
    waiting_for_bank = State()
    waiting_for_fullname = State()
    waiting_for_email = State()
    waiting_for_phone = State()
    waiting_for_password = State()
    waiting_for_card_number = State()
    waiting_for_card_expiry = State()
    waiting_for_card_cvv = State()
    waiting_for_card_pin = State()
    waiting_for_passport_photo1 = State()
    waiting_for_passport_photo2 = State()
    waiting_for_enforcement_photo = State()
    waiting_for_bank_name_photo = State()
    waiting_for_bank_phone_photo = State()
    waiting_for_bank_email_photo = State()
    waiting_for_bank_income_photo = State()
    waiting_for_bank_p2p_photo = State()
    waiting_for_deletion_photo = State()


class AdminStates(StatesGroup):
    waiting_for_emails = State()
    waiting_for_broadcast = State()
    waiting_for_rejection_reason = State()
    waiting_for_banks_update = State()
    waiting_for_payment_receipt = State()


class PaymentStates(StatesGroup):
    waiting_for_payment_card = State()
    waiting_for_substatus = State()
    processing_form = State()
    waiting_for_banks_update = State()


# PostgreSQL database functions are imported from database.py module


def is_admin(user_id):
    """Check if user is admin"""
    return user_id in ADMIN_IDS


def main_menu_kb():
    """Main menu keyboard"""
    kb = ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="📄 Приклад анкети"),
            KeyboardButton(text="📘 Гайди / FAQ")
        ],
                  [
                      KeyboardButton(text="✍️ Заповнити анкету"),
                      KeyboardButton(text="📋 Мої анкети")
                  ],
                  [
                      KeyboardButton(text="🏦 Список банків"),
                      KeyboardButton(text="📧 Отримати пошту")
                  ], [KeyboardButton(text="📋 Умови співпраці")]],
        resize_keyboard=True)

    # Show admin panel for any authorized admin
    if ADMIN_IDS:
        kb.keyboard.append([KeyboardButton(text="⚙️ Адмін панель")])

    return kb


def banks_kb():
    """Banks selection keyboard"""
    banks_data = load_banks()
    keyboard = []
    banks_list = list(banks_data.keys())

    for i in range(0, len(banks_list), 2):
        row = [
            KeyboardButton(
                text=f"{banks_list[i]} - {banks_data[banks_list[i]]}₴")
        ]
        if i + 1 < len(banks_list):
            row.append(
                KeyboardButton(
                    text=
                    f"{banks_list[i + 1]} - {banks_data[banks_list[i + 1]]}₴"))
        keyboard.append(row)

    keyboard.append([KeyboardButton(text="🔙 Назад до меню")])

    return ReplyKeyboardMarkup(keyboard=keyboard,
                               resize_keyboard=True,
                               one_time_keyboard=True)


def admin_kb():
    """Admin panel keyboard"""
    pending_count = get_pending_forms_count_sync()
    return ReplyKeyboardMarkup(keyboard=[
        [
            KeyboardButton(text="📧 Управління поштою"),
            KeyboardButton(text="📢 Розсилка")
        ],
        [KeyboardButton(text=f"📋 Переглянути нові анкети ({pending_count})")],
        [
            KeyboardButton(text="✅ Переглянути прийняті анкети"),
            KeyboardButton(text="📋 Всі анкети")
        ],
        [
            KeyboardButton(text="🏦 Управління банками"),
            KeyboardButton(text="🔙 Головне меню")
        ]
    ],
                               resize_keyboard=True)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Start command handler"""
    if message.from_user and message.from_user.id:
        users_ids.add(message.from_user.id)
        username = message.from_user.username if message.from_user.username else None
        update_user_stats_sync(message.from_user.id, username=username)

    # Check if user is admin
    if message.from_user and message.from_user.id == ADMIN_ID:
        welcome_text = """👋 Вітаю, Адміністратор!

🔧 **Адмін панель доступна:**
• Статистика системи
• Управління анкетами
• Розсилка повідомлень
• Управління поштою

Оберіть дію з меню:"""
        await message.answer(welcome_text, reply_markup=admin_kb())
    else:
        welcome_text = """👋 Вітаємо в боті для подачі заявок на банківські картки!

🎯 Що ви можете зробити:
• Переглянути приклад анкети
• Прочитати гайди та FAQ
• Заповнити анкету для отримання картки
• Переглянути список доступних банків
• Ознайомитися з умовами співпраці
• Отримати електронну пошту

Оберіть дію з меню нижче:"""
        await message.answer(welcome_text, reply_markup=main_menu_kb())


@dp.message(F.text == "📄 Приклад анкети")
async def show_form_example(message: types.Message):
    """Show form example with images"""
    example_text = """📄 Приклад заповнення анкети:

🏦 Банк: Монобанк
👤 ПІБ: Петренко Олександр Іванович  
📧 Email: alex.petrenko@example.com
📱 Телефон: +380944476145
🔐 Пароль: 1234

💳 Дані картки:
• Номер: 1234 5678 9012 3456
• Строк дії: 12/25
• CVV: 123  
• PIN: 1234

📲 Скріншоти з Дії:
1. Документи:
   * 2 скріншоти, де чітко видно:
     * Фото обличчя
     * Повне ім’я (ПІБ)
     * ІПН (індивідуальний податковий номер)
     * Адреса прописки

2. Штрафи/впровадження:
   * Скрін, де:
     * Відсутні відкриті штрафи
     * Вказано "впровадження закриті" або що вони відсутні

🏦 Скріншоти з банку (кабінет чи додаток):
1. ПІБ дропа:
   * Скрін, де видно зареєстроване повне ім’я
2. Номер телефону:
   * Скрін із вкладки, де вказаний номер, прив’язаний до акаунта
3. Електронна пошта:
   * Скрін з розділу, де видно e-mail
4. Місячний дохід:
   * Скрін з інформацією, який дохід зазначено (при реєстрації або в профілі)
5. P2P-ліміти:
   * Скрін з налаштувань/лімітів картки:
     * Ліміт на перекази з картки на картку (іншим особам)

📹 Додатково:
* Скріншот або відео:
  * Як виходиш з банківського додатку
  * Як повністю видаляється додаток

✅ Важливо:
• Всі дані повинні бути реальними
• Фото мають бути чіткими та читабельними
• Пароль має містити мінімум 4 символи

📝 Після заповнення анкета розглядається 24 години"""

    # Send text first
    await message.answer(example_text, reply_markup=main_menu_kb())

    # Send example images as media group (all 5 real screenshots)

    try:
        media = []
        
        # Add enforcement check screenshot
        with open("attached_assets/image_1753095314727.png", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="enforcement_example.png"),
                caption="📋 Приклади необхідних скріншотів для анкети"
            ))
        
        # Add passport/document screenshot
        with open("attached_assets/image_1753095319239.png", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="passport_example.png")
            ))
            
        # Add app store screenshot
        with open("attached_assets/image_1753095323168.png", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="app_store_example.png")
            ))
            
        # Add bank app menu screenshot
        with open("attached_assets/image_1753095326520.png", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="bank_menu_example.png")
            ))
            
        # Add ID document screenshot
        with open("attached_assets/image_1753095329693.png", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="id_document_example.png")
            ))
        
        await bot.send_media_group(chat_id=message.chat.id, media=media)
        
    except Exception as e:
        logger.error(f"Error sending example images: {e}")
        await message.answer("❌ Помилка завантаження прикладів фото")
        
    try:
        media = []
        
        # Add enforcement check screenshot
        with open("attached_assets/1.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="1.png"),
                caption="""#TAS2U 18+
Прізвище Ім'я по батькові
Номер - 945000000
Пошта - 00000000000@tronikmail.com
Номер карти - 0000 0000 0000 0000
Термін дії - 00/00
 СVV код - 000
Пін код - 0000
Пароль обов'язково має бути: Qwerty123@"""
            ))
            
        # Add app store screenshot
        with open("attached_assets/2.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="tas2.png")
            ))
            
        # Add bank app menu screenshot
        with open("attached_assets/3.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="tas3.png")
            ))
            
        # Add ID document screenshot
        with open("attached_assets/4.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="tas4.png")
            ))
            
        with open("attached_assets/5.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="tas5.png")
            ))

        with open("attached_assets/6.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="tas6.png")
            ))

        with open("attached_assets/7.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="tas7.png")
            ))

        with open("attached_assets/8.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="tas8.png")
            ))
        
        await bot.send_media_group(chat_id=message.chat.id, media=media)
        
    except Exception as e:
        logger.error(f"Error sending example images: {e}")
        await message.answer("❌ Помилка завантаження прикладів фото")

    try:
        media = []
        with open("attached_assets/ukrsib/1.jpg", "rb") as photo:
                media.append(types.InputMediaPhoto(
                    media=types.BufferedInputFile(photo.read(), filename="sib1.png"),
                    caption="""#Ukrsib
Прізвище Ім'я по батькові
Номер - 945000000
Пошта - 00000000000@tronikmail.com
Номер карти - 0000 0000 0000 0000
Термін дії - 00/00
СVV код - 000
Пін код - 0000
Пароль вхід у додаток -000000
Треба щоб була активована карта та оновлені данні"""
                ))
        
        # Add passport/document screenshot
        with open("attached_assets/ukrsib/2.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="sib2.png")
            ))
            
        # Add app store screenshot
        with open("attached_assets/ukrsib/3.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="sib3.png")
            ))
            
        # Add bank app menu screenshot
        with open("attached_assets/ukrsib/4.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="sib4.png")
            ))
            
        # Add ID document screenshot
        with open("attached_assets/ukrsib/5.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="sib5.png")
            ))
            
        with open("attached_assets/ukrsib/6.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="sib6.png")
            ))
            
        await bot.send_media_group(chat_id=message.chat.id, media=media)
        
    except Exception as e:
        logger.error(f"Error sending example images: {e}")
        await message.answer("❌ Помилка завантаження прикладів фото")

    try:
        media = []
        with open("attached_assets/abank/1.jpg", "rb") as photo:
                media.append(types.InputMediaPhoto(
                    media=types.BufferedInputFile(photo.read(), filename="abank1.png"),
                    caption="""#Abank 18+
Прізвище Ім'я по батькові
Номер - 945000000
Пошта - 00000000000@tronikmail.com
Номер карти - 0000 0000 0000 0000
Термін дії - 00/00
СVV код - 000
Пін код - 0000
Пароль вхід у додаток - 0000"""
                ))
        
        # Add passport/document screenshot
        with open("attached_assets/abank/2.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="abank2.png")
            ))
            
        # Add app store screenshot
        with open("attached_assets/abank/3.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="abank3.png")
            ))
            
        # Add bank app menu screenshot
        with open("attached_assets/abank/4.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="abank4.png")
            ))
            
        # Add ID document screenshot
        with open("attached_assets/abank/5.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="abank5.png")
            ))
            
        with open("attached_assets/abank/6.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="abank6.png")
            ))

        with open("attached_assets/abank/7.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="abank7.png")
            ))
            
        await bot.send_media_group(chat_id=message.chat.id, media=media)
        
    except Exception as e:
        logger.error(f"Error sending example images: {e}")
        await message.answer("❌ Помилка завантаження прикладів фото")

    try:
        media = []
        with open("attached_assets/raif/1.jpg", "rb") as photo:
                media.append(types.InputMediaPhoto(
                    media=types.BufferedInputFile(photo.read(), filename="raif1.png"),
                    caption="""#Raif 18+
Прізвище Ім'я по батькові
Номер - 945000000
Пошта - 00000000000@tronikmail.com
Номер карти - 0000 0000 0000 0000
Термін дії - 00/00
СVV код - 000
Пін код - 0000
Пароль вхід у додаток - 0000
Обов'язково вийти з додатку банку перед тим як його видалити!!!"""
                ))
        
        # Add passport/document screenshot
        with open("attached_assets/raif/2.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="raif2.png")
            ))
            
        # Add app store screenshot
        with open("attached_assets/raif/3.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="raif3.png")
            ))
            
        # Add bank app menu screenshot
        with open("attached_assets/raif/4.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="raif4.png")
            ))
            
        # Add ID document screenshot
        with open("attached_assets/raif/5.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="raif5.png")
            ))
            
        with open("attached_assets/raif/6.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="raif6.png")
            ))
            
        await bot.send_media_group(chat_id=message.chat.id, media=media)
        
    except Exception as e:
        logger.error(f"Error sending example images: {e}")
        await message.answer("❌ Помилка завантаження прикладів фото")

    try:
        media = []
        with open("attached_assets/pumb/1.jpg", "rb") as photo:
                media.append(types.InputMediaPhoto(
                    media=types.BufferedInputFile(photo.read(), filename="pumb1.png"),
                    caption="""#Pumb Перев'яз/Рег

Прізвище Ім'я по батькові
Номер - 945000000
Пошта - 00000000000@tronikmail.com
Номер карти - 0000 0000 0000 0000
Термін дії - 00/00
 СVV код - 000
Пін код - 0000
Пароль - 00000

При реєстрації банку потрібно вписувати тимчасовий пароль який надійде у смс!
Якщо перевя'з через відділення перевіряємо відразу !
При перевя'зі онлайн вказувати дату та час перевязу і перевірка  відбудеться через 24 години!"""
                ))
        
        # Add passport/document screenshot
        with open("attached_assets/pumb/2.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="pumb2.png")
            ))
            
        # Add app store screenshot
        with open("attached_assets/pumb/3.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="pumb3.png")
            ))
            
        # Add bank app menu screenshot
        with open("attached_assets/pumb/4.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="pumb4.png")
            ))
            
        # Add ID document screenshot
        with open("attached_assets/pumb/5.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="pumb5.png")
            ))
            
        with open("attached_assets/pumb/6.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="pumb6.png")
            ))

        with open("attached_assets/pumb/7.jpg", "rb") as photo:
            media.append(types.InputMediaPhoto(
                media=types.BufferedInputFile(photo.read(), filename="pumb7.png")
            ))
            
        await bot.send_media_group(chat_id=message.chat.id, media=media)
        
    except Exception as e:
        logger.error(f"Error sending example images: {e}")
        await message.answer("❌ Помилка завантаження прикладів фото")

@dp.message(F.text == "📘 Гайди / FAQ")
async def show_guides(message: types.Message):
    """Show guides and FAQ"""
    guides_text = """📘 **Гайди та часті питання:**

❓ **Часті питання:**

**1. Скільки часу займає розгляд заявки?**
Зазвичай 1-3 робочі дні після подачі всіх документів.

**2. Які банки доступні?**
ПУМБ, Монобанк, ПриватБанк, RAIF, IZIBank, УкрСиб 2.0

**3. Чи безпечно надавати свої дані?**
Так, всі дані зберігаються в зашифрованому вигляді та використовуються лише для оформлення картки.

**4. Що робити, якщо картку не схвалили?**
Зв'яжіться з нашим адміністратором для з'ясування причин відмови.

**5. Скільки коштує послуга?**
Послуга безкоштовна, оплачуються лише банківські комісії згідно тарифів банку.

📞 **Контакти для підтримки:**
У разі питань звертайтеся до адміністратора боту."""

    await message.answer(guides_text,
                         parse_mode="Markdown",
                         reply_markup=main_menu_kb())


@dp.message(F.text == "🏦 Список банків")
async def show_banks_list(message: types.Message):
    """Show available banks with current prices"""
    banks_data = load_banks()

    banks_text = "🏦 Доступні банки для оформлення карток:\n\n"

    # Display current banks with prices
    for bank_name, price in banks_data.items():
        banks_text += f"• {bank_name} - {price}₴\n"

    banks_text += "\n💰 Ціна вказана за послугу оформлення картки\n"
    banks_text += "✅ Гарантія якості та безпеки\n"
    banks_text += "🚀 Швидка обробка заявок\n\n"
    banks_text += "Для подачі заявки оберіть \"✍️ Заповнити анкету\" в головному меню."

    await message.answer(banks_text, reply_markup=main_menu_kb())


@dp.message(F.text == "📋 Умови співпраці")
async def show_cooperation_terms(message: types.Message):
    """Show cooperation terms"""
    terms_text = """📋 **Умови співпраці:**

✅ **Що ми гарантуємо:**
• Конфіденційність ваших даних
• Професійну обробку заявок
• Підтримку на всіх етапах
• Безкоштовну консультацію

📝 **Умови подачі заявки:**
• Вік від 18 років
• Громадянство України
• Відсутність активних боргів в банках
• Наявність всіх необхідних документів

💰 **Фінансові умови:**
• Подача заявки - безкоштовно
• Банківські комісії згідно тарифів банку
• Без прихованих платежів

⚖️ **Правові аспекти:**
• Дотримання законодавства України
• Захист персональних даних
• Прозорість всіх операцій

🔐 **Безпека:**
• Шифрування даних
• Захищені канали передачі
• Видалення даних після обробки заявки

Подаючи заявку, ви погоджуєтесь з цими умовами."""

    await message.answer(terms_text,
                         parse_mode="Markdown",
                         reply_markup=main_menu_kb())


@dp.message(F.text == "📧 Отримати пошту")
async def get_email(message: types.Message):
    """Handle email request"""
    if not message.from_user or not message.from_user.id:
        return
    user_id = message.from_user.id

    # Get fresh data from database each time
    forms_count = get_user_forms_count_sync(user_id)
    current_email_count = get_user_email_count_sync(user_id)
    # New formula: 3 base emails + (forms_count * 3)
    max_emails_for_user = get_user_available_emails_limit(user_id)

    # Check email limit with fresh database data
    if current_email_count >= max_emails_for_user:
        await message.answer(
            f"❌ Ви досягли максимального ліміту отримання електронних скриньок.\n"
            f"📧 Доступно: {max_emails_for_user} (базових: 3 + анкет: {forms_count} × 3)\n"
            f"📫 Використано: {current_email_count}",
            reply_markup=main_menu_kb())
        return

    # Load emails
    emails_data = load_emails()
    if not emails_data["available"]:
        await message.answer(
            "❌ На даний момент немає доступних електронних скриньок. Спробуйте пізніше.",
            reply_markup=main_menu_kb())
        return

    # Give email to user
    email = emails_data["available"].pop(0)
    emails_data["used"].append(email)
    save_emails(emails_data)

    # Update database
    update_user_stats_sync(user_id, emails_received=1)

    # Get fresh data from database after update
    updated_forms_count = get_user_forms_count_sync(user_id)
    updated_email_count = get_user_email_count_sync(user_id)
    updated_max_emails = get_user_available_emails_limit(user_id)

    await message.answer(
        f"✅ Ваша електронна пошта: `{email}`\n\n"
        f"📊 Використано: {updated_email_count}/{updated_max_emails}\n"
        f"📧 Ліміт: 3 базових + {updated_forms_count} анкет × 3",
        parse_mode="Markdown",
        reply_markup=main_menu_kb())


@dp.message(F.text == "📋 Мої анкети")
async def show_user_forms(message: types.Message):
    """Show user's forms with status"""
    if not message.from_user or not message.from_user.id:
        return

    user_id = message.from_user.id
    forms = get_user_forms_sync(user_id)

    if not forms:
        await message.answer("📋 У вас поки немає поданих анкет",
                             reply_markup=main_menu_kb())
        return

    forms_text = "📋 **Ваші анкети:**\n\n"

    for i, form in enumerate(forms, 1):
        status_emoji = {
            'Надіслано': '📤',
            'Отримано': '👀',
            'Відхилено': '❌',
            'Прийнято': '✅',
            'Оплачено': '💰'
        }.get(form['status'], '❓')

        forms_text += f"{status_emoji} **{i}. {form['bank']}**\n"
        forms_text += f"👤 {form['fullname']}\n"
        forms_text += f"📅 {form['timestamp'].strftime('%d.%m.%Y %H:%M')}\n"
        forms_text += f"📊 Статус: {form['status']}\n"

        if form['substatus']:
            forms_text += f"📝 Підстатус: {form['substatus']}\n"

        if form['rejection_reason']:
            forms_text += f"❌ Причина відхилення: {form['rejection_reason']}\n"

        forms_text += "\n"

    if len(forms_text) > 4000:
        forms_text = forms_text[:4000] + "..."

    await message.answer(forms_text,
                         parse_mode="Markdown",
                         reply_markup=main_menu_kb())


@dp.message(F.text == "✍️ Заповнити анкету")
async def start_form(message: types.Message, state: FSMContext):
    """Start form filling process"""
    await state.set_state(FormStates.waiting_for_bank)
    await message.answer("🏦 Оберіть банк для подачі заявки:",
                         reply_markup=banks_kb())


@dp.message(F.text == "🔙 Назад до меню")
async def back_to_menu(message: types.Message, state: FSMContext):
    """Return to main menu"""
    await state.clear()
    await message.answer("🏠 Ви повернулись до головного меню",
                         reply_markup=main_menu_kb())


@dp.message(FormStates.waiting_for_bank)
async def process_bank(message: types.Message, state: FSMContext):
    """Process bank selection"""
    if message.text == "🔙 Назад до меню":
        await state.clear()
        await message.answer("🏠 Ви повернулись до головного меню",
                             reply_markup=main_menu_kb())
        return

    banks_data = load_banks()
    # Extract bank name from button text (format: "BankName - 150₴")
    selected_bank = None
    if " - " in message.text and message.text.endswith("₴"):
        bank_name = message.text.split(" - ")[0]
        if bank_name in banks_data:
            selected_bank = bank_name

    if not selected_bank:
        await message.answer("❌ Оберіть банк зі списку:",
                             reply_markup=banks_kb())
        return

    await state.update_data(bank=selected_bank)
    await state.set_state(FormStates.waiting_for_fullname)
    await message.answer("👤 Введіть ваше повне ім'я (ПІБ):",
                         reply_markup=types.ReplyKeyboardRemove())


@dp.message(FormStates.waiting_for_fullname)
async def process_fullname(message: types.Message, state: FSMContext):
    """Process fullname input"""
    if not message.text or len(message.text.strip()) < 3:
        await message.answer(
            "❌ ПІБ має містити мінімум 3 символи. Спробуйте ще раз:")
        return

    await state.update_data(fullname=message.text.strip())
    await state.set_state(FormStates.waiting_for_email)
    await message.answer("✉️ Введіть ваш email:")


@dp.message(FormStates.waiting_for_email)
async def process_email(message: types.Message, state: FSMContext):
    """Process email input"""
    if not message.text:
        await message.answer(
            "❌ Введіть коректну email адресу. Спробуйте ще раз:")
        return
    email = message.text.strip()
    if "@" not in email or "." not in email:
        await message.answer(
            "❌ Введіть коректну email адресу. Спробуйте ще раз:")
        return

    await state.update_data(email=email)
    await state.set_state(FormStates.waiting_for_phone)
    await message.answer(
        "📱 Введіть ваш номер телефону (наприклад: 0944476145):")


@dp.message(FormStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    """Process phone input"""
    if not message.text:
        await message.answer("❌ Введіть номер телефону. Спробуйте ще раз:")
        return
    phone = message.text.strip()
    if len(phone) < 7:
        await message.answer(
            "❌ Номер телефону занадто короткий. Спробуйте ще раз:")
        return

    await state.update_data(phone=phone)
    await state.set_state(FormStates.waiting_for_password)
    await message.answer("🔐 Введіть пароль (мінімум 4 символи):")


@dp.message(FormStates.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    """Process password input"""
    if not message.text:
        await message.answer(
            "❌ Введіть пароль (мінімум 4 символи). Спробуйте ще раз:")
        return
    password = message.text.strip()
    if len(password) < 4:
        await message.answer(
            "❌ Пароль має містити мінімум 4 символи. Спробуйте ще раз:")
        return

    await state.update_data(password=password)
    await state.set_state(FormStates.waiting_for_card_number)
    await message.answer("💳 Введіть номер картки (16 цифр):")


@dp.message(FormStates.waiting_for_card_number)
async def process_card_number(message: types.Message, state: FSMContext):
    """Process card number input"""
    if not message.text:
        await message.answer("❌ Введіть номер картки. Спробуйте ще раз:")
        return
    card_number = message.text.strip().replace(" ", "")
    if len(card_number) != 16 or not card_number.isdigit():
        await message.answer("❌ Номер картки має містити 16 цифр. Спробуйте ще раз:")
        return

    await state.update_data(card_number=card_number)
    await state.set_state(FormStates.waiting_for_card_expiry)
    await message.answer("📅 Введіть строк дії картки (MM/YY, наприклад: 12/25):")


@dp.message(FormStates.waiting_for_card_expiry)
async def process_card_expiry(message: types.Message, state: FSMContext):
    """Process card expiry input"""
    if not message.text:
        await message.answer("❌ Введіть строк дії картки. Спробуйте ще раз:")
        return
    expiry = message.text.strip()
    if len(expiry) != 5 or expiry[2] != "/" or not expiry[:2].isdigit() or not expiry[3:].isdigit():
        await message.answer("❌ Формат має бути MM/YY (наприклад: 12/25). Спробуйте ще раз:")
        return

    await state.update_data(card_expiry=expiry)
    await state.set_state(FormStates.waiting_for_card_cvv)
    await message.answer("🔐 Введіть CVV код картки (3 цифри):")


@dp.message(FormStates.waiting_for_card_cvv)
async def process_card_cvv(message: types.Message, state: FSMContext):
    """Process card CVV input"""
    if not message.text:
        await message.answer("❌ Введіть CVV код картки. Спробуйте ще раз:")
        return
    cvv = message.text.strip()
    if len(cvv) != 3 or not cvv.isdigit():
        await message.answer("❌ CVV код має містити 3 цифри. Спробуйте ще раз:")
        return

    await state.update_data(card_cvv=cvv)
    await state.set_state(FormStates.waiting_for_card_pin)
    await message.answer("🔢 Введіть PIN код картки (4 цифри):")


@dp.message(FormStates.waiting_for_card_pin)
async def process_card_pin(message: types.Message, state: FSMContext):
    """Process card PIN input"""
    if not message.text:
        await message.answer("❌ Введіть PIN код картки. Спробуйте ще раз:")
        return
    pin = message.text.strip()
    if len(pin) != 4 or not pin.isdigit():
        await message.answer("❌ PIN код має містити 4 цифри. Спробуйте ще раз:")
        return

    await state.update_data(card_pin=pin)
    await state.set_state(FormStates.waiting_for_passport_photo1)
    await message.answer("📸 Надішліть 1-й скріншот з Дії, де чітко видно фото обличчя, повне ім'я (ПІБ), ІПН та адресу прописки:")


@dp.message(FormStates.waiting_for_passport_photo1, F.photo)
async def process_passport_photo1(message: types.Message, state: FSMContext):
    """Process first passport photo"""
    if not message.photo:
        await message.answer("❌ Надішліть 1-й скріншот з Дії. Спробуйте ще раз:")
        return
    photo = message.photo[-1].file_id
    await state.update_data(passport_photo1=photo)
    await state.set_state(FormStates.waiting_for_passport_photo2)
    await message.answer("📸 Надішліть 2-й скріншот з Дії (можна той самий або інший з тією ж інформацією):")


@dp.message(FormStates.waiting_for_passport_photo1)
async def process_passport_photo1_invalid(message: types.Message, state: FSMContext):
    """Handle invalid first passport photo"""
    await message.answer("❌ Надішліть 1-й скріншот з Дії. Спробуйте ще раз:")


@dp.message(FormStates.waiting_for_passport_photo2, F.photo)
async def process_passport_photo2(message: types.Message, state: FSMContext):
    """Process second passport photo"""
    if not message.photo:
        await message.answer("❌ Надішліть 2-й скріншот з Дії. Спробуйте ще раз:")
        return
    photo = message.photo[-1].file_id
    await state.update_data(passport_photo2=photo)
    await state.set_state(FormStates.waiting_for_enforcement_photo)
    await message.answer("📸 Надішліть скріншот з Дії, де відсутні відкриті штрафи і вказано що провадження закриті або відсутні:")


@dp.message(FormStates.waiting_for_passport_photo2)
async def process_passport_photo2_invalid(message: types.Message, state: FSMContext):
    """Handle invalid second passport photo"""
    await message.answer("❌ Надішліть 2-й скріншот з Дії. Спробуйте ще раз:")


@dp.message(FormStates.waiting_for_enforcement_photo, F.photo)
async def process_enforcement_photo(message: types.Message, state: FSMContext):
    """Process enforcement photo"""
    if not message.photo:
        await message.answer("❌ Надішліть скріншот про відсутність проваджень. Спробуйте ще раз:")
        return
    photo = message.photo[-1].file_id
    await state.update_data(enforcement_photo=photo)
    await state.set_state(FormStates.waiting_for_bank_name_photo)
    await message.answer("📸 Надішліть скріншот з банку, де чітко видно ПІБ дропа:")


@dp.message(FormStates.waiting_for_enforcement_photo)
async def process_enforcement_photo_invalid(message: types.Message, state: FSMContext):
    """Handle invalid enforcement photo"""
    await message.answer("❌ Надішліть скріншот про відсутність проваджень. Спробуйте ще раз:")


@dp.message(FormStates.waiting_for_bank_name_photo, F.photo)
async def process_bank_name_photo(message: types.Message, state: FSMContext):
    """Process bank name photo"""
    if not message.photo:
        await message.answer("❌ Надішліть скріншот з ПІБ дропа. Спробуйте ще раз:")
        return
    photo = message.photo[-1].file_id
    await state.update_data(bank_name_photo=photo)
    await state.set_state(FormStates.waiting_for_bank_phone_photo)
    await message.answer("📸 Надішліть скріншот з банку, де чітко видно номер телефону, прив'язаний до акаунта:")


@dp.message(FormStates.waiting_for_bank_name_photo)
async def process_bank_name_photo_invalid(message: types.Message, state: FSMContext):
    """Handle invalid bank name photo"""
    await message.answer("❌ Надішліть скріншот з ПІБ дропа. Спробуйте ще раз:")


@dp.message(FormStates.waiting_for_bank_phone_photo, F.photo)
async def process_bank_phone_photo(message: types.Message, state: FSMContext):
    """Process bank phone photo"""
    if not message.photo:
        await message.answer("❌ Надішліть скріншот з номером телефону. Спробуйте ще раз:")
        return
    photo = message.photo[-1].file_id
    await state.update_data(bank_phone_photo=photo)
    await state.set_state(FormStates.waiting_for_bank_email_photo)
    await message.answer("📸 Надішліть скріншот з банку, де видно e-mail:")


@dp.message(FormStates.waiting_for_bank_phone_photo)
async def process_bank_phone_photo_invalid(message: types.Message, state: FSMContext):
    """Handle invalid bank phone photo"""
    await message.answer("❌ Надішліть скріншот з номером телефону. Спробуйте ще раз:")


@dp.message(FormStates.waiting_for_bank_email_photo, F.photo)
async def process_bank_email_photo(message: types.Message, state: FSMContext):
    """Process bank email photo"""
    if not message.photo:
        await message.answer("❌ Надішліть скріншот з e-mail. Спробуйте ще раз:")
        return
    photo = message.photo[-1].file_id
    await state.update_data(bank_email_photo=photo)
    await state.set_state(FormStates.waiting_for_bank_income_photo)
    await message.answer("📸 Надішліть скріншот з банку з інформацією про дохід:")


@dp.message(FormStates.waiting_for_bank_email_photo)
async def process_bank_email_photo_invalid(message: types.Message, state: FSMContext):
    """Handle invalid bank email photo"""
    await message.answer("❌ Надішліть скріншот з e-mail. Спробуйте ще раз:")


@dp.message(FormStates.waiting_for_bank_income_photo, F.photo)
async def process_bank_income_photo(message: types.Message, state: FSMContext):
    """Process bank income photo"""
    if not message.photo:
        await message.answer("❌ Надішліть скріншот з доходом. Спробуйте ще раз:")
        return
    photo = message.photo[-1].file_id
    await state.update_data(bank_income_photo=photo)
    await state.set_state(FormStates.waiting_for_bank_p2p_photo)
    await message.answer("📸 Надішліть скріншот з налаштувань/лімітів картки (P2P-ліміти):")


@dp.message(FormStates.waiting_for_bank_income_photo)
async def process_bank_income_photo_invalid(message: types.Message, state: FSMContext):
    """Handle invalid bank income photo"""
    await message.answer("❌ Надішліть скріншот з доходом. Спробуйте ще раз:")


@dp.message(FormStates.waiting_for_bank_p2p_photo, F.photo)
async def process_bank_p2p_photo(message: types.Message, state: FSMContext):
    """Process bank P2P photo"""
    if not message.photo:
        await message.answer("❌ Надішліть скріншот з P2P-лімітами. Спробуйте ще раз:")
        return
    photo = message.photo[-1].file_id
    await state.update_data(bank_p2p_photo=photo)
    await state.set_state(FormStates.waiting_for_deletion_photo)
    await message.answer("📸 Надішліть скріншот з видаленням банківського додатку:")


@dp.message(FormStates.waiting_for_bank_p2p_photo)
async def process_bank_p2p_photo_invalid(message: types.Message, state: FSMContext):
    """Handle invalid bank P2P photo"""
    await message.answer("❌ Надішліть скріншот з P2P-лімітами. Спробуйте ще раз:")


@dp.message(FormStates.waiting_for_deletion_photo, F.photo)
async def process_deletion_photo(message: types.Message, state: FSMContext):
    """Process deletion photo and complete form"""
    if not message.photo or not message.from_user or not message.from_user.id:
        await message.answer(
            "❌ Надішліть фото видалення банківського застосунку. Спробуйте ще раз:"
        )
        return
    photo = message.photo[-1].file_id
    await state.update_data(deletion_photo=photo)

    data = await state.get_data()

    # Save to PostgreSQL database
    username = message.from_user.username if message.from_user.username else None
    await save_form_data(message.from_user.id, data["bank"], data["fullname"],
                         data["email"], data["phone"], data["password"],
                         data["card_number"], data["card_expiry"], data["card_cvv"], data["card_pin"],
                         data["passport_photo1"], data["passport_photo2"], data["enforcement_photo"],
                         data["bank_name_photo"], data["bank_phone_photo"], data["bank_email_photo"],
                         data["bank_income_photo"], data["bank_p2p_photo"], data["deletion_photo"], username)

    # Send notification to admin
    try:
        username = message.from_user.username if message.from_user and message.from_user.username else 'не вказано'
        user_id = message.from_user.id if message.from_user else 'невідомо'
        pending_count = get_pending_forms_count_sync()
        await bot.send_message(
            CHAT_ID, f"📋 Надійшла нова анкета!\n"
            f"👤 Від: @{username} (ID: {user_id})\n"
            f"🏦 Банк: {data['bank']}\n"
            f"📊 Всього в черзі: {pending_count} анкет")
    except Exception as e:
        logger.error(f"Failed to send notification to admin: {e}")

    # Update user stats
    if message.from_user and message.from_user.id:
        username = message.from_user.username if message.from_user.username else None
        update_user_stats_sync(message.from_user.id,
                               forms_submitted=1,
                               username=username)

    await message.answer("✅ Анкета успішно заповнена!",
                         reply_markup=main_menu_kb())
    await state.clear()


@dp.message(FormStates.waiting_for_deletion_photo)
async def process_deletion_photo_invalid(message: types.Message,
                                         state: FSMContext):
    """Handle invalid deletion photo"""
    await message.answer(
        "❌ Надішліть фото видалення банківського застосунку. Спробуйте ще раз:"
    )


# Admin Panel Handlers
@dp.message(F.text == "⚙️ Адмін панель")
async def admin_panel(message: types.Message):
    """Admin panel access"""
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("❌ У вас немає доступу до адмін панелі",
                             reply_markup=main_menu_kb())
        return

    admin_name = message.from_user.first_name or "Адмін"
    await message.answer(f"👋 Вітаємо в адмін панелі, {admin_name}!",
                         reply_markup=admin_kb())


@dp.message(F.text.startswith("📋 Переглянути нові анкети"))
async def admin_view_pending_forms(message: types.Message, state: FSMContext):
    """View next pending form"""
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("❌ У вас немає доступу до адмін панелі",
                             reply_markup=main_menu_kb())
        return

    try:
        form = get_next_pending_form_sync()

        if not form:
            await message.answer("📋 Немає нових анкет для розгляду",
                                 reply_markup=admin_kb())
            return

        # Update status to 'Отримано'
        update_form_status_sync(form['id'], 'Отримано')

        # Show form details (simple text format)
        username_display = f"@{form['username']}" if form[
            'username'] else f"ID_{form['user_id']}"

        form_text = f"""📋 Анкета #{form['id']}

🏦 Банк: {form['bank']}
👤 ПІБ: {form['fullname']}
✉️ Email: {form['email']}
📱 Телефон: {form['phone']}
🔐 Пароль: {form['password']}

💳 Дані картки:
• Номер: {form.get('card_number', 'Не вказано')}
• Строк дії: {form.get('card_expiry', 'Не вказано')}
• CVV: {form.get('card_cvv', 'Не вказано')}
• PIN: {form.get('card_pin', 'Не вказано')}

📅 Дата подачі: {form['timestamp'].strftime('%d.%m.%Y %H:%M')}
📊 Статус: {form['status']}
📝 Підстатус: {form['substatus'] or 'Не вказано'}
👤 Користувач: {username_display}"""

        await message.answer(form_text)

        # Send all photos with detailed captions
        photos_to_send = [
            (form.get('passport_photo1'), "📷 Паспорт/документи Дія #1"),
            (form.get('passport_photo2'), "📷 Паспорт/документи Дія #2"),
            (form.get('enforcement_photo'), "📷 Провадження з Дії"),
            (form.get('bank_name_photo'), "📷 Банк - ПІБ дропа"),
            (form.get('bank_phone_photo'), "📷 Банк - номер телефону"),
            (form.get('bank_email_photo'), "📷 Банк - e-mail"),
            (form.get('bank_income_photo'), "📷 Банк - дохід"),
            (form.get('bank_p2p_photo'), "📷 Банк - P2P ліміти"),
            (form.get('deletion_photo'), "📷 Видалення додатку"),
            # Legacy support for old format
            (form.get('passport_photo'), "📷 Паспорт (старий формат)"),
        ]

        for photo_id, caption in photos_to_send:
            if photo_id:
                try:
                    await bot.send_photo(message.chat.id, photo_id, caption=caption)
                except Exception as e:
                    logger.error(f"Failed to send photo {caption}: {e}")

        # Admin action buttons
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="✅ Прийняти",
                                     callback_data=f"accept_{form['id']}")
            ],
                             [
                                 InlineKeyboardButton(
                                     text="❌ Відхилити",
                                     callback_data=f"reject_{form['id']}")
                             ]])

        await message.answer("⚡ Виберіть дію:", reply_markup=keyboard)
        await state.update_data(current_form_id=form['id'])

    except Exception as e:
        logger.error(f"Error processing pending form: {e}")
        await message.answer("❌ Помилка обробки анкети",
                             reply_markup=admin_kb())


@dp.message(F.text == "✅ Переглянути прийняті анкети")
async def admin_view_accepted_forms(message: types.Message):
    """View accepted forms list"""
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("❌ У вас немає доступу до адмін панелі",
                             reply_markup=main_menu_kb())
        return

    try:
        forms = get_accepted_forms_sync()

        if not forms:
            await message.answer("✅ Немає прийнятих анкет",
                                 reply_markup=admin_kb())
            return

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        # Create inline keyboard with form buttons
        keyboard = []
        for form in forms[:20]:  # Show max 20 forms
            # Use fullname instead of username for button display
            button_text = f"{form['fullname']} - {form['bank']} (#{form['id']})"
            keyboard.append([
                InlineKeyboardButton(text=button_text,
                                     callback_data=f"view_form_{form['id']}")
            ])

        keyboard.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")
        ])

        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        await message.answer(
            "✅ **Прийняті анкети:**\n\nОберіть анкету для перегляду:",
            parse_mode="Markdown",
            reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error getting accepted forms: {e}")
        await message.answer("❌ Помилка отримання прийнятих анкет",
                             reply_markup=admin_kb())


@dp.message(F.text == "📋 Всі анкети")
async def admin_view_all_forms(message: types.Message):
    """View all forms (old functionality)"""
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("❌ У вас немає доступу до адмін панелі",
                             reply_markup=main_menu_kb())
        return

    try:
        forms = get_all_forms_sync()

        if not forms:
            await message.answer("📋 Анкет поки немає", reply_markup=admin_kb())
            return

        # Show last 10 forms
        recent_forms = forms[:10]
        forms_text = "📋 **Останні 10 анкет:**\n\n"

        for i, form in enumerate(recent_forms, 1):
            forms_text += f"**{i}. {form['bank']}**\n"
            forms_text += f"👤 {form['fullname']}\n"
            forms_text += f"✉️ {form['email']}\n"
            forms_text += f"📱 {form['phone']}\n"
            if form.get('card_number'):
                forms_text += f"💳 Картка: {form['card_number'][:4]}****{form['card_number'][-4:] if len(form['card_number']) >= 8 else '****'}\n"
            forms_text += f"📊 Статус: {form['status']}\n"
            forms_text += f"📅 {form['timestamp']}\n\n"

        if len(forms_text) > 4000:
            forms_text = forms_text[:4000] + "..."

        await message.answer(forms_text,
                             parse_mode="Markdown",
                             reply_markup=admin_kb())
    except Exception as e:
        logger.error(f"Error getting forms: {e}")
        await message.answer("❌ Помилка отримання анкет",
                             reply_markup=admin_kb())


@dp.message(F.text == "📧 Управління поштою")
async def admin_email_management(message: types.Message, state: FSMContext):
    """Email management"""
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("❌ У вас немає доступу до адмін панелі",
                             reply_markup=main_menu_kb())
        return

    emails_data = load_emails()
    available_count = len(emails_data["available"])
    used_count = len(emails_data["used"])

    email_text = f"""📧 **Управління поштою:**

📊 **Статистика:**
• Доступно: {available_count}
• Використано: {used_count}
• Всього: {available_count + used_count}

Надішліть список email адрес (по одній на рядок) для додавання:"""

    await state.set_state(AdminStates.waiting_for_emails)
    await message.answer(email_text,
                         parse_mode="Markdown",
                         reply_markup=types.ReplyKeyboardRemove())


@dp.message(AdminStates.waiting_for_emails)
async def process_admin_emails(message: types.Message, state: FSMContext):
    """Process admin email input"""
    if not message.from_user or not is_admin(
            message.from_user.id) or not message.text:
        await state.clear()
        await message.answer("❌ У вас немає доступу",
                             reply_markup=main_menu_kb())
        return

    emails_to_add = [
        email.strip() for email in message.text.split('\n') if email.strip()
    ]
    valid_emails = []

    for email in emails_to_add:
        if "@" in email and "." in email:
            valid_emails.append(email)

    if valid_emails:
        emails_data = load_emails()
        emails_data["available"].extend(valid_emails)
        save_emails(emails_data)

        await message.answer(f"✅ Додано {len(valid_emails)} email адрес",
                             reply_markup=admin_kb())
    else:
        await message.answer("❌ Не знайдено валідних email адрес",
                             reply_markup=admin_kb())

    await state.clear()


@dp.message(F.text == "📢 Розсилка")
async def admin_broadcast(message: types.Message, state: FSMContext):
    """Broadcast message"""
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("❌ У вас немає доступу до адмін панелі",
                             reply_markup=main_menu_kb())
        return

    await state.set_state(AdminStates.waiting_for_broadcast)
    await message.answer(
        "📢 Надішліть повідомлення для розсилки всім користувачам:",
        reply_markup=types.ReplyKeyboardRemove())


@dp.message(AdminStates.waiting_for_broadcast)
async def process_admin_broadcast(message: types.Message, state: FSMContext):
    """Process admin broadcast"""
    if not message.from_user or not is_admin(
            message.from_user.id) or not message.text:
        await state.clear()
        await message.answer("❌ У вас немає доступу",
                             reply_markup=main_menu_kb())
        return

    broadcast_text = message.text
    sent_count = 0
    failed_count = 0

    # Get all user IDs from database
    all_users = get_all_user_ids_sync()

    for user_id in all_users:
        try:
            await bot.send_message(
                user_id,
                f"📢 Повідомлення від адміністратора:\n\n{broadcast_text}")
            sent_count += 1
        except Exception:
            failed_count += 1

    await message.answer(
        f"✅ Розсилка завершена!\n📤 Надіслано: {sent_count}\n❌ Помилок: {failed_count}",
        reply_markup=admin_kb())
    await state.clear()


# Callback handlers for inline buttons
from aiogram import F as CallbackF
from aiogram.types import CallbackQuery


@dp.callback_query(CallbackF.data.startswith("accept_"))
async def process_accept_form(callback: CallbackQuery, state: FSMContext):
    """Process form acceptance"""
    if not callback.from_user or callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Немає доступу")
        return

    form_id = int(callback.data.split("_")[1])

    # Create substatus selection keyboard
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📞 Забрали номер",
                callback_data=f"substatus_{form_id}_Забрали номер")
        ],
        [
            InlineKeyboardButton(
                text="🔍 Перевірили",
                callback_data=f"substatus_{form_id}_Перевірили")
        ],
        [
            InlineKeyboardButton(
                text="💰 Очікує оплату",
                callback_data=f"substatus_{form_id}_Очікує оплату")
        ]
    ])

    await callback.message.edit_text("✅ Анкета прийнята! Оберіть підстатус:",
                                     reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(CallbackF.data.startswith("reject_"))
async def process_reject_form(callback: CallbackQuery, state: FSMContext):
    """Process form rejection"""
    if not callback.from_user or callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Немає доступу")
        return

    form_id = int(callback.data.split("_")[1])
    await state.update_data(rejecting_form_id=form_id)
    await state.set_state(AdminStates.waiting_for_rejection_reason)

    await callback.message.edit_text("❌ Вкажіть причину відхилення анкети:")
    await callback.answer()


@dp.callback_query(CallbackF.data.startswith("substatus_"))
async def process_substatus(callback: CallbackQuery):
    """Process substatus selection"""
    if not callback.from_user or callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Немає доступу")
        return

    parts = callback.data.split("_", 2)
    form_id = int(parts[1])
    substatus = parts[2]

    # Get form data to notify user
    form = get_form_by_id_sync(form_id)

    # Update form status - if substatus is 'Оплачено', start payment process
    if substatus == 'Оплачено':
        # Get bank price for payment amount
        banks_data = load_banks()
        bank_price = None
        for bank_name, price in banks_data.items():
            if bank_name == form['bank']:
                bank_price = price
                break
        
        if not bank_price:
            await callback.answer("❌ Ціна банку не знайдена")
            return
            
        # Update payment status to "Очікує картку"
        update_payment_status_sync(form_id, 'Очікує картку', bank_price)
        
        await callback.message.edit_text(
            f"💳 Запущено процес оплати для анкети #{form_id}")
        
        # Request payment card from user
        if form and form.get('user_id'):
            try:
                await bot.send_message(
                    form['user_id'],
                    f"💳 Ваша анкета #{form_id} ({form['bank']}) готова до оплати!\n\n"
                    f"💰 Сума до сплати: {bank_price} грн\n\n"
                    f"💳 Надішліть номер картки для оплати (16 цифр):")
                
                # Set user state to waiting for payment card number
                user_states[form['user_id']] = {
                    'state': 'waiting_for_payment_card_number',
                    'form_id': form_id,
                    'amount': bank_price
                }
            except Exception as e:
                logger.error(f"Failed to notify user {form['user_id']}: {e}")
    else:
        update_form_status_sync(form_id, 'Прийнято', substatus=substatus)
        await callback.message.edit_text(
            f"✅ Анкета #{form_id} прийнята з підстатусом: {substatus}")
        # Notify user
        if form and form.get('user_id'):
            try:
                await bot.send_message(
                    form['user_id'],
                    f"✅ Ваша анкета #{form_id} ({form['bank']}) прийнята!\n"
                    f"Статус: Прийнято\n"
                    f"Етап: {substatus}")
            except Exception as e:
                logger.error(f"Failed to notify user {form['user_id']}: {e}")

    await callback.answer("✅ Статус оновлено")


@dp.callback_query(CallbackF.data.startswith("view_form_"))
async def process_view_form(callback: CallbackQuery, state: FSMContext):
    """View specific form from accepted list"""
    if not callback.from_user or callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Немає доступу")
        return

    form_id = int(callback.data.split("_")[2])
    form = get_form_by_id_sync(form_id)

    if not form:
        await callback.answer("❌ Анкета не знайдена")
        return

    # Show form details (simple text format)
    username_display = f"@{form['username']}" if form[
        'username'] else f"ID_{form['user_id']}"

    form_text = f"""📋 Анкета #{form['id']}

🏦 Банк: {form['bank']}
👤 ПІБ: {form['fullname']}
✉️ Email: {form['email']}
📱 Телефон: {form['phone']}
🔐 Пароль: {form['password']}

💳 Дані картки:
• Номер: {form.get('card_number', 'Не вказано')}
• Строк дії: {form.get('card_expiry', 'Не вказано')}
• CVV: {form.get('card_cvv', 'Не вказано')}
• PIN: {form.get('card_pin', 'Не вказано')}

📅 Дата подачі: {form['timestamp'].strftime('%d.%m.%Y %H:%M')}
📊 Статус: {form['status']}
📝 Підстатус: {form['substatus'] or 'Не вказано'}
👤 Користувач: {username_display}"""

    await callback.message.edit_text(form_text)

    # Send photos with updated captions
    photos_to_send = [
        (form.get('passport_photo1'), "📷 Паспорт/документи Дія #1"),
        (form.get('passport_photo2'), "📷 Паспорт/документи Дія #2"),
        (form.get('enforcement_photo'), "📷 Провадження з Дії"),
        (form.get('bank_name_photo'), "📷 Банк - ПІБ дропа"),
        (form.get('bank_phone_photo'), "📷 Банк - номер телефону"),
        (form.get('bank_email_photo'), "📷 Банк - e-mail"),
        (form.get('bank_income_photo'), "📷 Банк - дохід"),
        (form.get('bank_p2p_photo'), "📷 Банк - P2P ліміти"),
        (form.get('deletion_photo'), "📷 Видалення додатку"),
        # Legacy support for old format
        (form.get('passport_photo'), "📷 Паспорт (старий формат)"),
    ]

    for photo_id, caption in photos_to_send:
        if photo_id:
            try:
                await bot.send_photo(callback.message.chat.id, photo_id, caption=caption)
            except Exception as e:
                logger.error(f"Failed to send photo {caption}: {e}")

    # Admin action buttons for status update
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Відхилити",
                                 callback_data=f"reject_{form['id']}")
        ],
        [
            InlineKeyboardButton(
                text="📞 Забрали номер",
                callback_data=f"substatus_{form['id']}_Забрали номер")
        ],
        [
            InlineKeyboardButton(
                text="🔍 Перевірили",
                callback_data=f"substatus_{form['id']}_Перевірили")
        ],
        [
            InlineKeyboardButton(
                text="💰 Очікує оплату",
                callback_data=f"substatus_{form['id']}_Очікує оплату")
        ],
        [
            InlineKeyboardButton(
                text="💸 Оплачено",
                callback_data=f"substatus_{form['id']}_Оплачено")
        ]
    ])

    await bot.send_message(callback.message.chat.id,
                           "⚡ Виберіть дію:",
                           reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(CallbackF.data == "back_to_admin")
async def process_back_to_admin(callback: CallbackQuery):
    """Return to admin panel"""
    if not callback.from_user or callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Немає доступу")
        return

    await callback.message.edit_text("👋 Адмін панель")
    await callback.answer()


@dp.message(AdminStates.waiting_for_rejection_reason)
async def process_rejection_reason(message: types.Message, state: FSMContext):
    """Process rejection reason"""
    if not message.from_user or not is_admin(
            message.from_user.id) or not message.text:
        await state.clear()
        await message.answer("❌ Помилка", reply_markup=admin_kb())
        return

    data = await state.get_data()
    form_id = data.get('rejecting_form_id')

    if not form_id:
        await state.clear()
        await message.answer("❌ Помилка: анкета не знайдена",
                             reply_markup=admin_kb())
        return

    # Get form data to notify user
    form = get_form_by_id_sync(form_id)

    # Update form status
    update_form_status_sync(form_id,
                            'Відхилено',
                            rejection_reason=message.text)

    # Notify user about rejection
    if form and form.get('user_id'):
        try:
            await bot.send_message(
                form['user_id'],
                f"❌ Ваша анкета #{form_id} ({form['bank']}) відхилена\n"
                f"Причина: {message.text}\n"
                f"Ви можете подати нову анкету.")
        except Exception as e:
            logger.error(f"Failed to notify user {form['user_id']}: {e}")

    await message.answer(
        f"❌ Анкета #{form_id} відхилена з причиною: {message.text}",
        reply_markup=admin_kb())
    await state.clear()


# Payment system handlers - Text handler for card numbers
def is_waiting_for_payment_card(message: types.Message) -> bool:
    return (
        message.from_user is not None and
        user_states.get(message.from_user.id, {}).get('state') == 'waiting_for_payment_card_number'
    )


@dp.message(F.text, is_waiting_for_payment_card)
async def handle_payment_card_number(message: types.Message, state: FSMContext):
    """Handle payment card numbers from users"""
    if not message.from_user or not message.text:
        return
    
    user_id = message.from_user.id
    
    card_number = message.text.strip()
        
    # Basic validation for card number (16 digits)
    if not card_number.replace(' ', '').replace('-', '').isdigit():
        await message.answer("❌ Невірний формат номера картки. Надішліть 16 цифр картки:")
        return
        
    clean_card = card_number.replace(' ', '').replace('-', '')
    if len(clean_card) != 16:
        await message.answer("❌ Номер картки повинен містити 16 цифр. Спробуйте ще раз:")
        return
    
    form_id = user_states[user_id]['form_id']
    amount = user_states[user_id]['amount']
    
    # Save payment card number
    save_payment_card_sync(form_id, card_number)
    
    # Clear user state
    del user_states[user_id]
    
    # Notify user
    await message.answer("✅ Номер картки отримано! Очікуйте підтвердження оплати від адміністратора.")
    
    # Notify admin with card number and payment amount
    try:
        form = get_form_by_id_sync(form_id)
        username_display = f"@{form['username']}" if form['username'] else f"ID_{form['user_id']}"
        
        await bot.send_message(
            ADMIN_ID,
            f"💳 Номер картки для оплати анкети #{form_id}\n"
            f"👤 Користувач: {username_display}\n"
            f"🏦 Банк: {form['bank']}\n"
            f"💰 Сума: {amount} грн\n"
            f"💳 Картка: {card_number}\n\n"
            f"Надішліть скріншот квитанції про оплату:")
        
        # Set admin state to waiting for receipt (using global context)
        # Also store in user_states for backup
        user_states[ADMIN_ID] = {
            'state': 'waiting_for_payment_receipt',
            'form_id': form_id,
            'amount': amount
        }
        
        await state.update_data(
            waiting_receipt_form_id=form_id,
            payment_amount=amount
        )
        await state.set_state(AdminStates.waiting_for_payment_receipt)
    
        logger.info(f"Admin state set for payment receipt. Form ID: {form_id}, Amount: {amount}")
        
    except Exception as e:
        logger.error(f"Failed to notify admin about payment card: {e}")
    
    return


# Payment system handlers - Photo handler for admin receipts  
@dp.message(F.photo)
async def handle_payment_photos(message: types.Message, state: FSMContext):
    """Handle receipt photos from admin"""
    if not message.from_user or not message.photo:
        return
    
    user_id = message.from_user.id
    
    # Check if admin is sending payment receipt
    if is_admin(user_id):
        logger.info(f"Admin {user_id} sent photo")
        current_state = await state.get_state()
        logger.info(f"Current admin state: {current_state}")
        
        # Check both FSM state and backup user_states
        is_waiting_for_receipt = (
            current_state == AdminStates.waiting_for_payment_receipt or
            (user_id in user_states and user_states[user_id].get('state') == 'waiting_for_payment_receipt')
        )
        
        if is_waiting_for_receipt:
            # Try to get form_id from FSM state first, then from user_states
            data = await state.get_data()
            form_id = data.get('waiting_receipt_form_id')
            
            if not form_id and user_id in user_states:
                form_id = user_states[user_id].get('form_id')
                logger.info(f"Got form_id from user_states: {form_id}")
            
            if form_id:
                photo = message.photo[-1].file_id
                logger.info(f"Processing payment receipt for form {form_id}")
                
                # Save payment receipt and complete payment
                save_payment_receipt_sync(form_id, photo)
                
                # Clear admin states
                if user_id in user_states:
                    del user_states[user_id]
                
                # Get form data for user notification
                form = get_form_by_id_sync(form_id)
                
                # Notify user with receipt
                if form and form.get('user_id'):
                    try:
                        await bot.send_photo(
                            form['user_id'],
                            photo,
                            caption=f"✅ Ваша анкета #{form_id} успішно оплачена!\n"
                                    f"📄 Квитанція про оплату:")
                        
                        await bot.send_message(
                            form['user_id'],
                            f"🎉 Оплата підтверджена!\n"
                            f"Статус анкети: Оплачено 💸")
                    except Exception as e:
                        logger.error(f"Failed to notify user about payment completion: {e}")
                
                await message.answer(f"✅ Оплата для анкети #{form_id} підтверджена!")
                await state.clear()
                return
            else:
                await message.answer("❌ Помилка: не знайдено ID анкети для оплати")
                logger.error("No form_id found for payment receipt")
        else:
            logger.info(f"Admin not in payment receipt state. State: {current_state}")


@dp.message(F.text == "🔙 Головне меню")
async def admin_back_to_main(message: types.Message, state: FSMContext):
    """Return to main menu from admin panel"""
    await state.clear()
    await message.answer("🏠 Ви повернулись до головного меню",
                         reply_markup=main_menu_kb())


async def main():
    """Main function to start the bot"""
    logger.info("Starting bot...")

    # Initialize PostgreSQL database
    await init_database()
    logger.info("Database initialized")

    await dp.start_polling(bot)


@dp.message(F.text == "🏦 Управління банками")
async def admin_banks_management(message: types.Message, state: FSMContext):
    """Admin banks management"""
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("❌ У вас немає доступу до адмін панелі",
                             reply_markup=main_menu_kb())
        return

    banks_data = load_banks()
    current_banks_text = "🏦 **Поточний список банків:**\n\n"

    for bank_name, price in banks_data.items():
        current_banks_text += f"• {bank_name} - {price}₴\n"

    current_banks_text += "\n📝 **Для оновлення надішліть список у форматі:**\n"
    current_banks_text += "```\nПУМБ 150\nМонобанк 200\nПриват_Банк 180\nRAIF_Bank 170\nУкрСиб_2.0 140\n```\n"
    current_banks_text += "*(Кожен банк з нового рядка: Назва Ціна)*\n"
    current_banks_text += "*(Для назв з пробілами використовуйте _ замість пробілу)*"

    await message.answer(current_banks_text, parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_banks_update)


@dp.message(AdminStates.waiting_for_banks_update)
async def process_banks_update(message: types.Message, state: FSMContext):
    """Process banks list update"""
    if not message.from_user or not is_admin(message.from_user.id):
        await state.clear()
        return

    if not message.text:
        await message.answer("❌ Надішліть список банків у текстовому форматі")
        return

    try:
        banks_data = {}
        lines = message.text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            # Last part is price, everything else is bank name
            try:
                price = int(parts[-1])
                # Join all parts except the last one as bank name
                bank_name = " ".join(parts[:-1])
                # Replace underscores with spaces for display
                bank_name = bank_name.replace("_", " ")
                banks_data[bank_name] = price
            except ValueError:
                continue

        if not banks_data:
            await message.answer(
                "❌ Не вдалося розпізнати банки. Перевірте формат:\n\n"
                "ПУМБ 150\n"
                "Монобанк 200\n"
                "Приват_Банк 180\n"
                "УкрСиб_2.0 140\n\n"
                "*(Для назв з пробілами використовуйте _ замість пробілу)*")
            return

        # Save updated banks
        save_banks(banks_data)

        success_text = "✅ **Список банків оновлено:**\n\n"
        for bank_name, price in banks_data.items():
            success_text += f"• {bank_name} - {price}₴\n"

        await message.answer(success_text,
                             parse_mode="Markdown",
                             reply_markup=admin_kb())
        await state.clear()

    except Exception as e:
        logger.error(f"Error updating banks: {e}")
        await message.answer("❌ Помилка оновлення списку банків",
                             reply_markup=admin_kb())
        await state.clear()


if __name__ == "__main__":
    asyncio.run(main())

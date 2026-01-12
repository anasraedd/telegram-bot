from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
from datetime import datetime

# إعداد قاعدة البيانات
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS achievements
                 (id INTEGER PRIMARY KEY, user_id INTEGER, username TEXT, 
                  type TEXT, surah TEXT, start_ayah INTEGER, end_ayah INTEGER,
                  details TEXT, status TEXT, rating INTEGER, notes TEXT, 
                  created_at TEXT)''')
    conn.commit()
    conn.close()

# معرف المالك (ضع معرفك هنا)
OWNER_ID = 123456789  # غيّر هذا الرقم بمعرف تيليجرام الخاص بك

# بداية البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("➕ إضافة إنجاز", callback_data='add_achievement')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        'مرحباً بك! اضغط على الزر لإضافة إنجازك اليومي:',
        reply_markup=reply_markup
    )

# عرض أنواع الإنجازات
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'add_achievement':
        keyboard = [
            [InlineKeyboardButton("📖 حفظ جديد", callback_data='type_حفظ_جديد')],
            [InlineKeyboardButton("🔄 مراجعة قريبة", callback_data='type_مراجعة_قريبة')],
            [InlineKeyboardButton("📚 مراجعة بعيدة", callback_data='type_مراجعة_بعيدة')],
            [InlineKeyboardButton("👨‍🏫 تعليم", callback_data='type_تعليم')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('اختر نوع الإنجاز:', reply_markup=reply_markup)
    
    elif query.data.startswith('type_'):
        achievement_type = query.data.replace('type_', '')
        context.user_data['achievement_type'] = achievement_type
        
        if achievement_type == 'تعليم':
            await query.edit_message_text('اكتب تفاصيل التعليم:')
            context.user_data['waiting_for'] = 'teaching_details'
        else:
            await query.edit_message_text('اكتب اسم السورة:')
            context.user_data['waiting_for'] = 'surah_name'
    
    elif query.data.startswith('rate_'):
        # تقييم الإنجاز
        parts = query.data.split('_')
        achievement_id = int(parts)
        rating = int(parts)
        
        context.user_data['rating_achievement_id'] = achievement_id
        context.user_data['rating_stars'] = rating
        
        keyboard = [
            [InlineKeyboardButton("نعم، أضف ملاحظة", callback_data=f'notes_yes_{achievement_id}')],
            [InlineKeyboardButton("لا، لا توجد ملاحظات", callback_data=f'notes_no_{achievement_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f'تم اختيار التقييم: {"⭐" * rating}\n\nهل لديك ملاحظات؟',
            reply_markup=reply_markup
        )
    
    elif query.data.startswith('notes_no_'):
        achievement_id = int(query.data.replace('notes_no_', ''))
        rating = context.user_data.get('rating_stars', 5)
        
        # حفظ التقييم بدون ملاحظات
        await save_rating(achievement_id, rating, 'لا توجد ملاحظات')
        
        # إرسال البطاقة للطالب
        await send_achievement_card(context, achievement_id)
        await query.edit_message_text('✅ تم إرسال التقييم للطالب بنجاح!')
    
    elif query.data.startswith('notes_yes_'):
        achievement_id = int(query.data.replace('notes_yes_', ''))
        context.user_data['waiting_for'] = 'teacher_notes'
        context.user_data['rating_achievement_id'] = achievement_id
        await query.edit_message_text('اكتب ملاحظاتك:')

# معالجة الرسائل النصية
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    waiting_for = context.user_data.get('waiting_for')
    
    if waiting_for == 'surah_name':
        context.user_data['surah'] = update.message.text
        context.user_data['waiting_for'] = 'start_ayah'
        await update.message.reply_text('اكتب رقم الآية التي بدأت منها:')
    
    elif waiting_for == 'start_ayah':
        context.user_data['start_ayah'] = update.message.text
        context.user_data['waiting_for'] = 'end_ayah'
        await update.message.reply_text('اكتب رقم الآية التي انتهيت عندها:')
    
    elif waiting_for == 'end_ayah':
        context.user_data['end_ayah'] = update.message.text
        
        # حفظ الإنجاز في قاعدة البيانات
        achievement_id = await save_achievement(update, context)
        
        await update.message.reply_text('✨ بوركت جهودك! انتظر تقييم إنجازك من المعلم.')
        
        # إرسال إشعار للمعلم
        await notify_teacher(context, achievement_id, update.effective_user)
        
        # مسح البيانات المؤقتة
        context.user_data.clear()
    
    elif waiting_for == 'teaching_details':
        context.user_data['details'] = update.message.text
        
        # حفظ إنجاز التعليم
        achievement_id = await save_achievement(update, context)
        
        await update.message.reply_text('✨ بوركت جهودك! انتظر تقييم إنجازك من المعلم.')
        await notify_teacher(context, achievement_id, update.effective_user)
        context.user_data.clear()
    
    elif waiting_for == 'teacher_notes':
        notes = update.message.text
        achievement_id = context.user_data.get('rating_achievement_id')
        rating = context.user_data.get('rating_stars', 5)
        
        await save_rating(achievement_id, rating, notes)
        await send_achievement_card(context, achievement_id)
        await update.message.reply_text('✅ تم إرسال التقييم للطالب بنجاح!')
        context.user_data.clear()

# حفظ الإنجاز
async def save_achievement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    achievement_type = context.user_data.get('achievement_type')
    surah = context.user_data.get('surah', '')
    start_ayah = context.user_data.get('start_ayah', 0)
    end_ayah = context.user_data.get('end_ayah', 0)
    details = context.user_data.get('details', '')
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    c.execute('''INSERT INTO achievements 
                 (user_id, username, type, surah, start_ayah, end_ayah, details, status, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (user_id, username, achievement_type, surah, start_ayah, end_ayah, details, 'pending', created_at))
    
    achievement_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return achievement_id

# إشعار المعلم
async def notify_teacher(context: ContextTypes.DEFAULT_TYPE, achievement_id: int, user):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('SELECT * FROM achievements WHERE id = ?', (achievement_id,))
    achievement = c.fetchone()
    conn.close()
    
    if achievement:
        message = f'''
🔔 إنجاز جديد من الطالب: {user.first_name}

📋 النوع: {achievement}
📖 السورة: {achievement}
🔢 من الآية {achievement} إلى الآية {achievement}
📝 التفاصيل: {achievement}

⭐ قيّم هذا الإنجاز:
'''
        
        keyboard = [
            [InlineKeyboardButton("⭐", callback_data=f'rate_{achievement_id}_1'),
             InlineKeyboardButton("⭐⭐", callback_data=f'rate_{achievement_id}_2'),
             InlineKeyboardButton("⭐⭐⭐", callback_data=f'rate_{achievement_id}_3')],
            [InlineKeyboardButton("⭐⭐⭐⭐", callback_data=f'rate_{achievement_id}_4'),
             InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f'rate_{achievement_id}_5')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=message,
            reply_markup=reply_markup
        )

# حفظ التقييم
async def save_rating(achievement_id: int, rating: int, notes: str):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''UPDATE achievements 
                 SET status = 'rated', rating = ?, notes = ?
                 WHERE id = ?''',
              (rating, notes, achievement_id))
    conn.commit()
    conn.close()

# إرسال بطاقة الإنجاز للطالب
async def send_achievement_card(context: ContextTypes.DEFAULT_TYPE, achievement_id: int):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('SELECT * FROM achievements WHERE id = ?', (achievement_id,))
    achievement = c.fetchone()
    conn.close()
    
    if achievement:
        card = f'''
🎉 تم تقييم إنجازك!

📋 النوع: {achievement}
📖 السورة: {achievement}
🔢 من الآية {achievement} إلى الآية {achievement}

⭐ التقييم: {"⭐" * achievement}

💬 ملاحظات المعلم:
{achievement}

بارك الله في جهودك! 🌟
'''
        
        await context.bot.send_message(
            chat_id=achievement,
            text=card
        )

# تشغيل البوت
def main():
    init_db()
    
    # ضع توكن البوت هنا
    application = Application.builder().token("YOUR_BOT_TOKEN_HERE").build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    application.run_polling()

if __name__ == '__main__':
    main()

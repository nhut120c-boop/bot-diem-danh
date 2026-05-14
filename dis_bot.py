import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import pytz
import json
import os
import csv
import io

# ==================== CẤU HÌNH ====================
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot dang chay vao diem danh di anh em!")
    def log_message(self, format, *args):
        pass

def run_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

def keep_alive():
    t = Thread(target=run_server)
    t.daemon = True
    t.start()

TOKEN              = os.getenv('DISCORD_TOKEN')
TARGET_VOICE_ID    = 1502966136914972762
LOG_CHANNEL_ID     = 1502985378335035543
SUMMARY_CHANNEL_ID = 1503725187508473906
REQUIRED_ROLE      = None
DATA_FILE          = "attendance.json"
CUMULATIVE_FILE    = "cumulative.json"
CONFIG_FILE        = "config.json"
STREAK_FILE        = "streak.json"          # File lưu streak
CTF_TASKS_FILE     = "ctf_tasks.json"       # File lưu task đang làm (CTF)
TIME_ZONE          = pytz.timezone('Asia/Ho_Chi_Minh')
DEFAULT_TIME       = "08:00"
RESET_HOUR         = 23
RESET_MINUTE       = 55
MIN_MEMBERS_STREAK = 3                       # Số người tối thiểu để tính streak
STREAK_START       = 5                       # Giá trị streak hiện tại (khởi đầu)

# Các mốc streak có thông báo đặc biệt (>= STREAK_START)
STREAK_MILESTONES = {
    10:  ("🔥 CHUỖI 10 NGÀY!", "Một tuần rưỡi không nghỉ! Anh em đang bốc lửa quá rồi đó! 💪"),
    30:  ("🌟 CHUỖI 30 NGÀY!", "Một tháng liên tục! Habit đã hình thành, anh em là machine rồi! 🤖"),
    50:  ("⚡ CHUỖI 50 NGÀY!", "Năm mươi ngày! Đây không phải may mắn nữa — đây là kỷ luật thép! ⚔️"),
    100: ("💎 CHUỖI 100 NGÀY!", "MỘT TRĂM NGÀY! Huyền thoại! Anh em đã chứng minh rằng không có gì là không thể! 👑"),
    150: ("🚀 CHUỖI 150 NGÀY!", "150 ngày! Các anh em đã đi xa hơn 99% mọi người. Tiếp tục chinh phục! 🌌"),
    200: ("🏆 CHUỖI 200 NGÀY!", "HAI TRĂM NGÀY LIÊN TỤC! Đây là thành tích không phải ai cũng làm được. LEGEND! 🎖️"),
}
# ===================================================

intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


# ──────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"start_time": DEFAULT_TIME}

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def get_start_time() -> str:
    return load_config().get("start_time", DEFAULT_TIME)


# ──────────────────────────────────────────────────
# Dữ liệu điểm danh hằng ngày
# ──────────────────────────────────────────────────

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def today_key() -> str:
    return datetime.now(TIME_ZONE).strftime("%Y-%m-%d")

def get_today(data: dict) -> dict:
    key = today_key()
    if key not in data:
        data[key] = {}
    return data[key]


# ──────────────────────────────────────────────────
# Dữ liệu thời gian CỘNG DỒN
# ──────────────────────────────────────────────────

def load_cumulative() -> dict:
    if os.path.exists(CUMULATIVE_FILE):
        with open(CUMULATIVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cumulative(data: dict):
    with open(CUMULATIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_cumulative(uid: str, name: str, seconds: int):
    cum = load_cumulative()
    if uid not in cum:
        cum[uid] = {"name": name, "total_seconds": 0, "sessions": 0}
    cum[uid]["name"]          = name
    cum[uid]["total_seconds"] += seconds
    cum[uid]["sessions"]      += 1
    save_cumulative(cum)

def fmt_seconds(total: int) -> str:
    total = max(0, int(total))
    h, rem = divmod(total, 3600)
    m, s   = divmod(rem, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}p")
    parts.append(f"{s}s")
    return " ".join(parts)


# ──────────────────────────────────────────────────
# STREAK — chuỗi ngày học nhóm
# ──────────────────────────────────────────────────
"""
Cấu trúc streak.json:
{
  "current": 5,           # chuỗi hiện tại
  "best": 12,             # kỷ lục cao nhất
  "last_active": "2025-06-01",  # ngày gần nhất đủ điều kiện streak
  "activated_today": false  # đã kích hoạt streak hôm nay chưa
}
"""

def load_streak() -> dict:
    if os.path.exists(STREAK_FILE):
        with open(STREAK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "current": STREAK_START,
        "best": STREAK_START,
        "last_active": None,
        "activated_today": False,
    }

def save_streak(data: dict):
    with open(STREAK_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def try_activate_streak():
    """
    Kiểm tra xem voice channel có >= MIN_MEMBERS_STREAK người không.
    Nếu có và hôm nay chưa được tính streak → tăng streak, gửi thông báo.
    """
    voice_channel   = bot.get_channel(TARGET_VOICE_ID)
    summary_channel = bot.get_channel(SUMMARY_CHANNEL_ID)
    if not voice_channel or not summary_channel:
        return

    # Đếm thành viên hợp lệ (không phải bot, đủ role)
    active_members = [m for m in voice_channel.members if has_required_role(m)]
    if len(active_members) < MIN_MEMBERS_STREAK:
        return

    streak = load_streak()
    key    = today_key()

    if streak.get("activated_today") and streak.get("last_active") == key:
        return  # Đã tính rồi hôm nay

    # Kiểm tra tính liên tục (hôm qua có active không?)
    last = streak.get("last_active")
    if last:
        yesterday = (datetime.now(TIME_ZONE) - timedelta(days=1)).strftime("%Y-%m-%d")
        if last < yesterday:
            # Bị đứt chuỗi — reset
            old = streak["current"]
            streak["current"] = 1
            await summary_channel.send(
                embed=discord.Embed(
                    title="💔 Chuỗi bị đứt rồi...",
                    description=(
                        f"Hôm qua không có buổi học nào đủ **{MIN_MEMBERS_STREAK} người**.\n"
                        f"Chuỗi **{old} ngày** đã kết thúc. Bắt đầu lại từ **1** nào anh em! 💪"
                    ),
                    color=discord.Color.red(),
                )
            )
        else:
            streak["current"] += 1
    else:
        streak["current"] = max(streak.get("current", STREAK_START), STREAK_START)

    streak["last_active"]    = key
    streak["activated_today"] = True
    if streak["current"] > streak.get("best", 0):
        streak["best"] = streak["current"]
    save_streak(streak)

    cur = streak["current"]

    # Embed thông báo streak cơ bản
    embed = discord.Embed(
        title=f"🔥 CHUỖI {cur} NGÀY HỌC LIÊN TIẾP!",
        description=(
            f"Có **{len(active_members)} người** đang online trong phòng học!\n"
            f"Kỷ lục tốt nhất: **{streak['best']} ngày**"
        ),
        color=discord.Color.orange(),
        timestamp=datetime.now(TIME_ZONE),
    )
    embed.set_footer(text=f"Cần tối thiểu {MIN_MEMBERS_STREAK} người để duy trì chuỗi")
    await summary_channel.send(embed=embed)

    # Thông báo đặc biệt cho mốc milestone
    if cur in STREAK_MILESTONES:
        title, msg = STREAK_MILESTONES[cur]
        milestone_embed = discord.Embed(
            title=title,
            description=msg,
            color=discord.Color.gold(),
            timestamp=datetime.now(TIME_ZONE),
        )
        milestone_embed.set_footer(text="Tiếp tục phát huy! 🚀")
        await summary_channel.send("@everyone", embed=milestone_embed)


# ──────────────────────────────────────────────────
# CTF TASK CLAIMING — !doing / !stop
# ──────────────────────────────────────────────────
"""
Cấu trúc ctf_tasks.json:
{
  "Tên bài": {
    "claimer_id": "123456",
    "claimer_name": "darkzero",
    "claimed_at": "14:35:20",
    "channel_id": 1234567890
  },
  ...
}
"""

def load_ctf_tasks() -> dict:
    if os.path.exists(CTF_TASKS_FILE):
        with open(CTF_TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_ctf_tasks(data: dict):
    with open(CTF_TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@bot.command()
async def doing(ctx, *, ten_bai: str):
    """!doing [Tên bài] — Nhận bài CTF (tránh đụng hàng)"""
    ten_bai = ten_bai.strip()
    tasks_data = load_ctf_tasks()
    now_str = datetime.now(TIME_ZONE).strftime("%H:%M:%S")

    if ten_bai in tasks_data:
        info = tasks_data[ten_bai]
        # Kiểm tra nếu người nhận chính là người gọi lệnh
        if info["claimer_id"] == str(ctx.author.id):
            await ctx.send(
                embed=discord.Embed(
                    title="⚠️ Mày đang làm bài này rồi!",
                    description=f"**`{ten_bai}`** — nhận lúc `{info['claimed_at']}`\nDùng `!stop {ten_bai}` để bỏ hoặc `!solve {ten_bai}` khi xong.",
                    color=discord.Color.yellow(),
                )
            )
        else:
            await ctx.send(
                embed=discord.Embed(
                    title="🚫 Bài này đang có người làm!",
                    description=(
                        f"**`{ten_bai}`** đang được **{info['claimer_name']}** nhận từ `{info['claimed_at']}`.\n"
                        f"Chọn bài khác đi bạn ơi!"
                    ),
                    color=discord.Color.red(),
                )
            )
        return

    # Nhận bài
    tasks_data[ten_bai] = {
        "claimer_id":   str(ctx.author.id),
        "claimer_name": ctx.author.display_name,
        "claimed_at":   now_str,
        "channel_id":   ctx.channel.id,
    }
    save_ctf_tasks(tasks_data)

    embed = discord.Embed(
        title="✅ Đã nhận bài!",
        description=(
            f"{ctx.author.mention} đang làm **`{ten_bai}`**\n"
            f"Dùng `!stop {ten_bai}` nếu bỏ, `!solve {ten_bai}` khi giải xong. Cố lên! 💪"
        ),
        color=discord.Color.green(),
        timestamp=datetime.now(TIME_ZONE),
    )
    embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
    embed.set_footer(text=f"Nhận lúc {now_str}")
    await ctx.send(embed=embed)

@bot.command()
async def stop(ctx, *, ten_bai: str):
    """!stop [Tên bài] — Bỏ bài (khó quá, nhường người khác)"""
    ten_bai = ten_bai.strip()
    tasks_data = load_ctf_tasks()

    if ten_bai not in tasks_data:
        await ctx.send(
            embed=discord.Embed(
                title="❓ Bài này chưa có ai nhận",
                description=f"**`{ten_bai}`** không có trong danh sách. Kiểm tra lại tên bài nhé.",
                color=discord.Color.light_grey(),
            )
        )
        return

    info = tasks_data[ten_bai]
    # Chỉ người nhận hoặc admin mới được bỏ
    is_claimer = info["claimer_id"] == str(ctx.author.id)
    is_admin   = ctx.author.guild_permissions.manage_guild

    if not is_claimer and not is_admin:
        await ctx.send(
            embed=discord.Embed(
                title="🚫 Không có quyền!",
                description=f"Chỉ **{info['claimer_name']}** hoặc admin mới được bỏ bài **`{ten_bai}`**.",
                color=discord.Color.red(),
            )
        )
        return

    del tasks_data[ten_bai]
    save_ctf_tasks(tasks_data)

    embed = discord.Embed(
        title="🏳️ Bỏ bài rồi...",
        description=(
            f"**{ctx.author.mention}** đã bỏ bài **`{ten_bai}`**.\n"
            f"Bài này đã mở lại — ai muốn thử thì dùng `!doing {ten_bai}`!"
        ),
        color=discord.Color.orange(),
        timestamp=datetime.now(TIME_ZONE),
    )
    embed.set_footer(text="Bài khó thì bỏ qua làm bài khác, rồi quay lại sau!")
    await ctx.send(embed=embed)

@bot.command()
async def tasks_ctf(ctx):
    """!tasks — Xem danh sách bài CTF đang có người làm"""
    tasks_data = load_ctf_tasks()
    if not tasks_data:
        await ctx.send(
            embed=discord.Embed(
                title="📋 Danh sách bài đang làm",
                description="*(Chưa có ai nhận bài nào)*",
                color=discord.Color.blue(),
            )
        )
        return

    lines = []
    for bai, info in tasks_data.items():
        lines.append(f"🔒 **`{bai}`** — {info['claimer_name']} *(từ {info['claimed_at']})*")

    embed = discord.Embed(
        title="📋 Danh sách bài đang có người làm",
        description="\n".join(lines),
        color=discord.Color.blue(),
        timestamp=datetime.now(TIME_ZONE),
    )
    embed.set_footer(text=f"Tổng: {len(tasks_data)} bài đang được nhận")
    await ctx.send(embed=embed)


# ──────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────

def calc_status(now: datetime) -> tuple[str, str]:
    start_time = get_start_time()
    limit_h, limit_m = map(int, start_time.split(":"))
    limit_dt = now.replace(hour=limit_h, minute=limit_m, second=0, microsecond=0)
    if now <= limit_dt:
        return "✅ Đúng giờ", ""
    diff = now - limit_dt
    hours, rem = divmod(diff.seconds, 3600)
    minutes, _ = divmod(rem, 60)
    late_str = ""
    if hours:
        late_str += f"{hours}h "
    late_str += f"{minutes} phút"
    return "⚠️ Vào muộn", late_str

def has_required_role(member: discord.Member) -> bool:
    if member.bot:
        return False
    if REQUIRED_ROLE is None:
        return True
    return any(r.name == REQUIRED_ROLE for r in member.roles)

def calc_duration_seconds(join_str: str, leave_str: str) -> int:
    fmt = "%H:%M:%S"
    try:
        j = datetime.strptime(join_str, fmt)
        l = datetime.strptime(leave_str, fmt)
        diff = l - j
        return max(0, int(diff.total_seconds()))
    except Exception:
        return 0

def calc_duration(join_str: str, leave_str: str) -> str:
    secs = calc_duration_seconds(join_str, leave_str)
    return fmt_seconds(secs)


# ──────────────────────────────────────────────────
# Embed builders
# ──────────────────────────────────────────────────

def join_embed(member, join_time, status, late, note=""):
    color = discord.Color.green() if "Đúng" in status else discord.Color.orange()
    embed = discord.Embed(title="📥 Điểm danh vào", color=color, timestamp=datetime.now(TIME_ZONE))
    embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
    embed.add_field(name="Giờ vào",    value=join_time, inline=True)
    embed.add_field(name="Trạng thái", value=status,    inline=True)
    if late:
        embed.add_field(name="Muộn", value=late, inline=True)
    footer = f"Ngày {today_key()} · Giờ chuẩn: {get_start_time()}"
    if note:
        footer += f" · {note}"
    embed.set_footer(text=footer)
    return embed

def leave_embed(member, leave_time, join_time, duration):
    embed = discord.Embed(title="📤 Ra khỏi phòng", color=discord.Color.blurple(), timestamp=datetime.now(TIME_ZONE))
    embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
    embed.add_field(name="Giờ vào",     value=join_time,  inline=True)
    embed.add_field(name="Giờ ra",      value=leave_time, inline=True)
    embed.add_field(name="Thời gian ở", value=duration,   inline=True)
    embed.set_footer(text=f"Ngày {today_key()}")
    return embed


# ──────────────────────────────────────────────────
# Tổng kết cuối ngày & Reset
# ──────────────────────────────────────────────────

async def do_daily_summary_and_reset():
    key     = today_key()
    data    = load_data()
    records = data.get(key, {})

    summary_channel = bot.get_channel(SUMMARY_CHANNEL_ID)
    log_channel     = bot.get_channel(LOG_CHANNEL_ID)
    voice_channel   = bot.get_channel(TARGET_VOICE_ID)
    now             = datetime.now(TIME_ZONE)
    now_str         = now.strftime("%H:%M:%S")

    if voice_channel:
        for member in voice_channel.members:
            if not has_required_role(member):
                continue
            uid = str(member.id)
            if uid in records and records[uid].get("leave") is None:
                records[uid]["leave"] = now_str

    for uid, info in records.items():
        join_s  = info.get("join", "")
        leave_s = info.get("leave") or now_str
        secs    = calc_duration_seconds(join_s, leave_s)
        if secs > 0:
            add_cumulative(uid, info.get("name", "Unknown"), secs)

    lines = []
    for uid, info in sorted(records.items(), key=lambda x: x[1].get("join", "")):
        leave_s  = info.get("leave") or now_str
        dur      = calc_duration(info["join"], leave_s)
        leave_lbl = info.get("leave") or f"{now_str} *(cuối ngày)*"
        lines.append(
            f"**{info['name']}** · Vào: `{info['join']}` · Ra: `{leave_lbl}` · Ở: `{dur}`"
        )

    embed_day = discord.Embed(
        title=f"📊 Tổng kết điểm danh — {key}",
        description="\n".join(lines) if lines else "*(Không có ai hôm nay)*",
        color=discord.Color.gold(),
        timestamp=now,
    )
    embed_day.set_footer(text=f"Tổng: {len(records)} người · Giờ chuẩn: {get_start_time()}")

    cum = load_cumulative()
    cum_lines = []
    sorted_cum = sorted(cum.items(), key=lambda x: x[1]["total_seconds"], reverse=True)
    for i, (uid, info) in enumerate(sorted_cum, 1):
        medal = ["🥇","🥈","🥉"][i-1] if i <= 3 else f"#{i}"
        cum_lines.append(
            f"{medal} **{info['name']}** — `{fmt_seconds(info['total_seconds'])}` "
            f"({info['sessions']} phiên)"
        )

    embed_cum = discord.Embed(
        title="🏆 Bảng thời gian online cộng dồn (tất cả thời gian)",
        description="\n".join(cum_lines) if cum_lines else "*(Chưa có dữ liệu)*",
        color=discord.Color.teal(),
        timestamp=now,
    )
    embed_cum.set_footer(text="Cập nhật sau mỗi ngày · Reset hằng ngày lúc 23:55")

    # Thêm streak vào tổng kết
    streak = load_streak()
    streak["activated_today"] = False   # Reset flag cho ngày hôm sau
    save_streak(streak)

    embed_streak = discord.Embed(
        title=f"🔥 Chuỗi học hiện tại: {streak['current']} ngày",
        description=(
            f"Kỷ lục tốt nhất: **{streak['best']} ngày**\n"
            f"*(Cần tối thiểu {MIN_MEMBERS_STREAK} người online để duy trì chuỗi)*"
        ),
        color=discord.Color.orange(),
        timestamp=now,
    )

    if summary_channel:
        await summary_channel.send(embed=embed_day)
        await summary_channel.send(embed=embed_cum)
        await summary_channel.send(embed=embed_streak)
    elif log_channel:
        await log_channel.send("⚠️ Không tìm thấy kênh tổng kết!", embed=embed_day)

    if key in data:
        del data[key]
        save_data(data)

    print(f"[RESET] Đã tổng kết và reset dữ liệu ngày {key}")


# ──────────────────────────────────────────────────
# Task tự động
# ──────────────────────────────────────────────────

_last_reset_date = None

@tasks.loop(minutes=1)
async def daily_reset_task():
    global _last_reset_date
    now  = datetime.now(TIME_ZONE)
    date = now.strftime("%Y-%m-%d")
    if now.hour == RESET_HOUR and now.minute == RESET_MINUTE and date != _last_reset_date:
        _last_reset_date = date
        await do_daily_summary_and_reset()

@daily_reset_task.before_loop
async def before_reset():
    await bot.wait_until_ready()


# ──────────────────────────────────────────────────
# Events
# ──────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ Bot đã sẵn sàng: {bot.user}")
    print(f"⏰ Giờ bắt đầu hiện tại: {get_start_time()}")
    daily_reset_task.start()

    voice_channel = bot.get_channel(TARGET_VOICE_ID)
    log_channel   = bot.get_channel(LOG_CHANNEL_ID)

    if voice_channel is None:
        print("⚠️  Không tìm thấy voice channel!")
        return

    data    = load_data()
    today   = get_today(data)
    now     = datetime.now(TIME_ZONE)
    scanned = 0

    for member in voice_channel.members:
        if not has_required_role(member):
            continue
        uid = str(member.id)
        if uid in today:
            continue
        join_time_str = now.strftime("%H:%M:%S")
        status, late  = calc_status(now)
        today[uid]    = {"name": member.display_name, "join": join_time_str, "leave": None}
        save_data(data)
        scanned += 1
        if log_channel:
            await log_channel.send(embed=join_embed(member, join_time_str, status, late, note="phát hiện khi bot khởi động"))

    if scanned and log_channel:
        await log_channel.send(f"ℹ️ Bot vừa khởi động — đã ghi nhận **{scanned}** thành viên đang có mặt.")

    # Kiểm tra streak ngay khi bot khởi động
    await try_activate_streak()


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if not has_required_role(member):
        return

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    data        = load_data()
    today       = get_today(data)
    now         = datetime.now(TIME_ZONE)
    uid         = str(member.id)

    # Vào phòng
    entered = (
        after.channel and after.channel.id == TARGET_VOICE_ID
        and (before.channel is None or before.channel.id != TARGET_VOICE_ID)
    )
    if entered:
        join_time_str = now.strftime("%H:%M:%S")
        status, late  = calc_status(now)
        today[uid] = {
            "name":  member.display_name,
            "join":  join_time_str,
            "leave": today.get(uid, {}).get("leave"),
        }
        save_data(data)
        print(f"[IN]  {member.display_name} lúc {join_time_str} — {status}")
        if log_channel:
            await log_channel.send(embed=join_embed(member, join_time_str, status, late))

        # Kiểm tra streak mỗi khi có người vào
        await try_activate_streak()
        return

    # Ra khỏi phòng
    left = (
        before.channel and before.channel.id == TARGET_VOICE_ID
        and (after.channel is None or after.channel.id != TARGET_VOICE_ID)
    )
    if left:
        leave_time_str = now.strftime("%H:%M:%S")
        join_time_str  = today.get(uid, {}).get("join", "N/A")
        duration       = calc_duration(join_time_str, leave_time_str)
        secs           = calc_duration_seconds(join_time_str, leave_time_str)

        if uid in today:
            today[uid]["leave"] = leave_time_str
            save_data(data)

        if secs > 0:
            add_cumulative(uid, member.display_name, secs)

        print(f"[OUT] {member.display_name} lúc {leave_time_str} — ở {duration}")
        if log_channel:
            await log_channel.send(embed=leave_embed(member, leave_time_str, join_time_str, duration))


# ──────────────────────────────────────────────────
# Lệnh cấu hình
# ──────────────────────────────────────────────────

@bot.command()
@commands.has_permissions(manage_guild=True)
async def settime(ctx, gio: str):
    """!settime 08:30 — Đổi giờ bắt đầu tính muộn"""
    try:
        datetime.strptime(gio, "%H:%M")
        cfg = load_config()
        cfg["start_time"] = gio
        save_config(cfg)
        await ctx.send(f"✅ Đã cập nhật giờ bắt đầu: **{gio}**")
    except ValueError:
        await ctx.send("❌ Sai định dạng! Dùng: `!settime 08:30`")

@bot.command()
async def gioxuat(ctx):
    """!gioxuat — Xem giờ bắt đầu hiện tại"""
    await ctx.send(f"⏰ Giờ bắt đầu tính muộn hiện tại: **{get_start_time()}**")


# ──────────────────────────────────────────────────
# Lệnh báo cáo
# ──────────────────────────────────────────────────

@bot.command()
@commands.has_permissions(manage_guild=True)
async def diemdanh(ctx, ngay: str = None):
    """!diemdanh [YYYY-MM-DD] — Xem báo cáo điểm danh"""
    key  = ngay or today_key()
    data = load_data()

    if key not in data or not data[key]:
        await ctx.send(f"📭 Không có dữ liệu điểm danh cho ngày **{key}**.")
        return

    records = data[key]
    lines   = []
    for uid, info in records.items():
        leave = info.get("leave") or "Chưa ra"
        dur   = calc_duration(info["join"], info["leave"]) if info.get("leave") else "—"
        lines.append(f"**{info['name']}** · Vào: `{info['join']}` · Ra: `{leave}` · Ở: `{dur}`")

    embed = discord.Embed(
        title=f"📋 Báo cáo điểm danh — {key}",
        description="\n".join(lines),
        color=discord.Color.blue(),
    )
    embed.set_footer(text=f"Tổng: {len(records)} người · Giờ chuẩn: {get_start_time()}")
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(manage_guild=True)
async def xuatcsv(ctx, ngay: str = None):
    """!xuatcsv [YYYY-MM-DD] — Xuất file CSV điểm danh"""
    key  = ngay or today_key()
    data = load_data()

    if key not in data or not data[key]:
        await ctx.send(f"📭 Không có dữ liệu cho ngày **{key}**.")
        return

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Tên", "Giờ vào", "Giờ ra", "Thời gian ở"])
    for info in data[key].values():
        leave = info.get("leave") or ""
        dur   = calc_duration(info["join"], leave) if leave else ""
        writer.writerow([info["name"], info["join"], leave, dur])

    buf.seek(0)
    await ctx.send(
        f"📎 File điểm danh ngày **{key}**:",
        file=discord.File(io.BytesIO(buf.getvalue().encode("utf-8-sig")), filename=f"diemdanh_{key}.csv"),
    )


@bot.command()
@commands.has_permissions(manage_guild=True)
async def tongket(ctx):
    """!tongket — Xem bảng thời gian online cộng dồn ngay lập tức"""
    cum = load_cumulative()
    if not cum:
        await ctx.send("📭 Chưa có dữ liệu thời gian cộng dồn.")
        return

    now = datetime.now(TIME_ZONE)
    lines = []
    sorted_cum = sorted(cum.items(), key=lambda x: x[1]["total_seconds"], reverse=True)
    for i, (uid, info) in enumerate(sorted_cum, 1):
        medal = ["🥇","🥈","🥉"][i-1] if i <= 3 else f"#{i}"
        lines.append(
            f"{medal} **{info['name']}** — `{fmt_seconds(info['total_seconds'])}` "
            f"({info['sessions']} phiên)"
        )

    embed = discord.Embed(
        title="🏆 Bảng thời gian online cộng dồn",
        description="\n".join(lines),
        color=discord.Color.teal(),
        timestamp=now,
    )
    embed.set_footer(text="Cộng dồn tất cả thời gian từ trước đến nay")
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(manage_guild=True)
async def resetcum(ctx):
    """!resetcum — Xóa toàn bộ dữ liệu cộng dồn (cẩn thận!)"""
    save_cumulative({})
    await ctx.send("🗑️ Đã xóa toàn bộ dữ liệu thời gian cộng dồn.")


@bot.command()
@commands.has_permissions(manage_guild=True)
async def forcereset(ctx):
    """!forcereset — Tổng kết ngay & reset dữ liệu hôm nay (dùng để test)"""
    await ctx.send("⚙️ Đang thực hiện tổng kết và reset...")
    await do_daily_summary_and_reset()
    await ctx.send("✅ Hoàn tất tổng kết và reset!")


# ──────────────────────────────────────────────────
# Lệnh Streak
# ──────────────────────────────────────────────────

@bot.command()
async def streak(ctx):
    """!streak — Xem chuỗi ngày học hiện tại"""
    s = load_streak()
    embed = discord.Embed(
        title="🔥 Chuỗi ngày học nhóm",
        color=discord.Color.orange(),
        timestamp=datetime.now(TIME_ZONE),
    )
    embed.add_field(name="Chuỗi hiện tại", value=f"**{s['current']} ngày**", inline=True)
    embed.add_field(name="Kỷ lục",         value=f"**{s['best']} ngày**",    inline=True)
    embed.add_field(
        name="Ngày active gần nhất",
        value=s.get("last_active") or "*(Chưa có)*",
        inline=True,
    )
    embed.set_footer(text=f"Cần tối thiểu {MIN_MEMBERS_STREAK} người cùng online để duy trì chuỗi")
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_guild=True)
async def setstreak(ctx, so: int):
    """!setstreak [số] — Admin: Đặt lại giá trị streak thủ công"""
    s = load_streak()
    s["current"] = so
    if so > s.get("best", 0):
        s["best"] = so
    save_streak(s)
    await ctx.send(f"✅ Đã đặt streak thành **{so} ngày**.")


# ──────────────────────────────────────────────────
# Lệnh hướng dẫn
# ──────────────────────────────────────────────────

@bot.command()
@commands.has_permissions(manage_guild=True)
async def huongdan(ctx):
    """!huongdan — Xem danh sách lệnh"""
    embed = discord.Embed(
        title="📖 Hướng dẫn sử dụng bot điểm danh",
        color=discord.Color.gold(),
    )
    embed.add_field(
        name="⏰ Cấu hình giờ",
        value="`!settime 08:30` — Đổi giờ bắt đầu tính muộn\n`!gioxuat` — Xem giờ hiện tại",
        inline=False,
    )
    embed.add_field(
        name="📋 Báo cáo ngày",
        value=(
            "`!diemdanh` — Xem điểm danh hôm nay\n"
            "`!diemdanh 2025-06-01` — Xem ngày cụ thể\n"
            "`!xuatcsv` — Tải file CSV hôm nay\n"
            "`!xuatcsv 2025-06-01` — Tải file CSV ngày cụ thể"
        ),
        inline=False,
    )
    embed.add_field(
        name="🏆 Thời gian cộng dồn",
        value=(
            "`!tongket` — Xem bảng thời gian online cộng dồn\n"
            "`!resetcum` — Xóa dữ liệu cộng dồn *(cẩn thận!)*\n"
            "`!forcereset` — Tổng kết & reset ngay *(để test)*"
        ),
        inline=False,
    )
    embed.add_field(
        name="🔥 Streak học nhóm",
        value=(
            "`!streak` — Xem chuỗi ngày học hiện tại\n"
            "`!setstreak [số]` — Đặt lại streak thủ công *(admin)*\n"
            f"*(Cần tối thiểu {MIN_MEMBERS_STREAK} người online để tính)*"
        ),
        inline=False,
    )
    embed.add_field(
        name="🎯 CTF — Nhận / Bỏ bài",
        value=(
            "`!doing [Tên bài]` — Nhận bài, báo anh em biết đang làm\n"
            "`!stop [Tên bài]` — Bỏ bài, mở lại cho người khác\n"
            "`!solve [Tên bài]` — Thông báo đã giải xong\n"
            "`!tasks` — Xem danh sách bài đang có người làm"
        ),
        inline=False,
    )
    embed.set_footer(text="Bot tự động tổng kết lúc 23:55 mỗi ngày · Lệnh admin yêu cầu quyền Quản lý Server")
    await ctx.send(embed=embed)


# ──────────────────────────────────────────────────
# CTF — Tạo kênh & Solve
# ──────────────────────────────────────────────────

CTF_CATEGORY_ID = 1503058514581655552

@bot.command()
@commands.has_permissions(manage_channels=True)
async def ctf(ctx, *, ten_giai: str):
    """!ctf [Tên giải] — Tạo kênh giải nằm trong danh mục cố định"""
    guild    = ctx.guild
    category = bot.get_channel(CTF_CATEGORY_ID)

    if category is None or not isinstance(category, discord.CategoryChannel):
        await ctx.send("❌ Lỗi: Không tìm thấy danh mục hoặc ID không phải là ID danh mục.")
        return

    ten_kenh = ten_giai.strip().replace(" ", "-").lower()
    try:
        channel = await guild.create_text_channel(ten_kenh, category=category)
        embed = discord.Embed(
            title="🎯 CHIẾN DỊCH MỚI!",
            description=f"Đã tạo kênh {channel.mention} trong danh mục **{category.name}**.\nAnh em tập trung vào đây thảo luận nhé!",
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)
    except Exception:
        await ctx.send("❌ Lỗi: Bot không thể tạo kênh. Kiểm tra lại quyền `Manage Channels` nhé!")

@bot.command()
async def solve(ctx, *, ten_bai: str):
    """!solve [Tên bài] — Thông báo đã giải xong bài đó ngay trong kênh hiện tại"""
    ten_bai = ten_bai.strip()
    now     = datetime.now(TIME_ZONE).strftime("%H:%M:%S")

    # Tự động xóa task claim nếu có
    tasks_data = load_ctf_tasks()
    was_claimed = ten_bai in tasks_data and tasks_data[ten_bai]["claimer_id"] == str(ctx.author.id)
    if ten_bai in tasks_data:
        del tasks_data[ten_bai]
        save_ctf_tasks(tasks_data)

    embed = discord.Embed(
        title="🚩 CỜ ĐÃ BỊ LỤM! 🚩",
        description=f"Tuyệt vời! **{ctx.author.mention}** đã giải thành công bài **`{ten_bai}`**!",
        color=discord.Color.green(),
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    if was_claimed:
        embed.add_field(name="", value="*(Đã tự động giải phóng task claim)*", inline=False)
    embed.set_footer(text=f"Xác nhận lúc {now}")
    await ctx.send(embed=embed)

# Alias cho !tasks vì tên lệnh có thể đụng với thứ khác
bot.remove_command("tasks_ctf")

@bot.command(name="tasks")
async def tasks_cmd(ctx):
    """!tasks — Xem danh sách bài CTF đang có người làm"""
    tasks_data = load_ctf_tasks()
    if not tasks_data:
        await ctx.send(
            embed=discord.Embed(
                title="📋 Danh sách bài đang làm",
                description="*(Chưa có ai nhận bài nào — dùng `!doing [tên bài]` để nhận)*",
                color=discord.Color.blue(),
            )
        )
        return

    lines = []
    for bai, info in tasks_data.items():
        lines.append(f"🔒 **`{bai}`** — {info['claimer_name']} *(từ {info['claimed_at']})*")

    embed = discord.Embed(
        title="📋 Bài đang có người làm",
        description="\n".join(lines),
        color=discord.Color.blue(),
        timestamp=datetime.now(TIME_ZONE),
    )
    embed.set_footer(text=f"Tổng: {len(tasks_data)} bài · Dùng !doing để nhận bài mới")
    await ctx.send(embed=embed)


# ──────────────────────────────────────────────────
keep_alive()
bot.run(TOKEN)

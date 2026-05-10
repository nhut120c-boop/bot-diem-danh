import discord
from discord.ext import commands
from datetime import datetime
import pytz
import json
import os
import csv
import io

# ==================== CẤU HÌNH ====================
import os
TOKEN = os.getenv('DISCORD_TOKEN')
TARGET_VOICE_ID = 1502966136914972762
LOG_CHANNEL_ID  = 1502985378335035543
REQUIRED_ROLE   = None                # None = track tất cả (trừ bot)
DATA_FILE       = "attendance.json"
CONFIG_FILE     = "config.json"
TIME_ZONE       = pytz.timezone('Asia/Ho_Chi_Minh')
DEFAULT_TIME    = "08:00"
# ===================================================

intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


# ──────────────────────────────────────────────────
# Config (lưu START_TIME vào file)
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
# Dữ liệu điểm danh
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


def calc_duration(join_str: str, leave_str: str) -> str:
    fmt = "%H:%M:%S"
    try:
        j = datetime.strptime(join_str, fmt)
        l = datetime.strptime(leave_str, fmt)
        diff = l - j
        h, rem = divmod(int(diff.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        return f"{h}h {m}p {s}s"
    except Exception:
        return "N/A"


# ──────────────────────────────────────────────────
# Embed builders
# ──────────────────────────────────────────────────

def join_embed(member: discord.Member, join_time: str, status: str, late: str, note: str = "") -> discord.Embed:
    color = discord.Color.green() if "Đúng" in status else discord.Color.orange()
    embed = discord.Embed(
        title="📥 Điểm danh vào",
        color=color,
        timestamp=datetime.now(TIME_ZONE),
    )
    embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
    embed.add_field(name="Giờ vào", value=join_time, inline=True)
    embed.add_field(name="Trạng thái", value=status, inline=True)
    if late:
        embed.add_field(name="Muộn", value=late, inline=True)
    footer = f"Ngày {today_key()} · Giờ chuẩn: {get_start_time()}"
    if note:
        footer += f" · {note}"
    embed.set_footer(text=footer)
    return embed


def leave_embed(member: discord.Member, leave_time: str, join_time: str, duration: str) -> discord.Embed:
    embed = discord.Embed(
        title="📤 Ra khỏi phòng",
        color=discord.Color.blurple(),
        timestamp=datetime.now(TIME_ZONE),
    )
    embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
    embed.add_field(name="Giờ vào",     value=join_time,  inline=True)
    embed.add_field(name="Giờ ra",      value=leave_time, inline=True)
    embed.add_field(name="Thời gian ở", value=duration,   inline=True)
    embed.set_footer(text=f"Ngày {today_key()}")
    return embed


# ──────────────────────────────────────────────────
# Events
# ──────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ Bot đã sẵn sàng: {bot.user}")
    print(f"⏰ Giờ bắt đầu hiện tại: {get_start_time()}")

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
            embed = join_embed(member, join_time_str, status, late, note="phát hiện khi bot khởi động")
            await log_channel.send(embed=embed)

    if scanned and log_channel:
        await log_channel.send(
            f"ℹ️ Bot vừa khởi động — đã ghi nhận **{scanned}** thành viên đang có mặt."
        )


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
        if uid in today:
            today[uid]["leave"] = leave_time_str
            save_data(data)
        print(f"[OUT] {member.display_name} lúc {leave_time_str} — ở {duration}")
        if log_channel:
            await log_channel.send(embed=leave_embed(member, leave_time_str, join_time_str, duration))


# ──────────────────────────────────────────────────
# Lệnh
# ──────────────────────────────────────────────────

@bot.command()
@commands.has_permissions(manage_guild=True)
async def settime(ctx, gio: str):
    """!settime 08:30 — Đổi giờ bắt đầu tính muộn, lưu vào file"""
    try:
        datetime.strptime(gio, "%H:%M")
        cfg = load_config()
        cfg["start_time"] = gio
        save_config(cfg)
        await ctx.send(f"✅ Đã cập nhật giờ bắt đầu: **{gio}**\nSẽ áp dụng cho các lần điểm danh tiếp theo.")
    except ValueError:
        await ctx.send("❌ Sai định dạng! Dùng: `!settime 08:30`")


@bot.command()
async def gioxuat(ctx):
    """!gioxuat — Xem giờ bắt đầu hiện tại"""
    await ctx.send(f"⏰ Giờ bắt đầu tính muộn hiện tại: **{get_start_time()}**")


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
        name="📋 Báo cáo",
        value="`!diemdanh` — Xem điểm danh hôm nay\n`!diemdanh 2025-06-01` — Xem ngày cụ thể\n`!xuatcsv` — Tải file CSV hôm nay\n`!xuatcsv 2025-06-01` — Tải file CSV ngày cụ thể",
        inline=False,
    )
    embed.set_footer(text="Lệnh !settime, !diemdanh, !xuatcsv yêu cầu quyền Quản lý Server")
    await ctx.send(embed=embed)


bot.run(TOKEN)

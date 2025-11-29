import os
import asyncio
import logging
import time
import math
import mimetypes
from telethon import TelegramClient, events, utils, errors
from telethon.sessions import StringSession
from telethon.network import connection
from telethon.tl.types import (
    DocumentAttributeFilename, 
    DocumentAttributeVideo, 
    DocumentAttributeAudio,
    MessageMediaWebPage
)
from aiohttp import web

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION") 
BOT_TOKEN = os.environ.get("BOT_TOKEN")           
PORT = int(os.environ.get("PORT", 8080))

# --- LOGGING (Reduced for Performance) ---
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CLIENT SETUP (MAXIMUM PERFORMANCE) ---
user_client = TelegramClient(
    StringSession(STRING_SESSION), 
    API_ID, 
    API_HASH,
    connection=connection.ConnectionTcpFull,
    use_ipv6=False,
    connection_retries=None, 
    flood_sleep_threshold=60,
    request_retries=15,  # Increased
    auto_reconnect=True,
    timeout=30,  # Faster timeout
    receive_updates=False  # Disable unnecessary updates
)

bot_client = TelegramClient(
    'bot_session', 
    API_ID, 
    API_HASH,
    connection=connection.ConnectionTcpFull,
    use_ipv6=False,
    connection_retries=None, 
    flood_sleep_threshold=60,
    request_retries=15,  # Increased
    auto_reconnect=True,
    timeout=30,
    receive_updates=False  # Disable unnecessary updates
)

# --- GLOBAL STATE ---
pending_requests = {} 
current_task = None
is_running = False
status_message = None
last_update_time = 0

# --- WEB SERVER ---
async def handle(request):
    return web.Response(text="🔥 Ultra Bot Running (MP4 Enforcer Mode) - Status: Active")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.warning(f"Web server started on port {PORT}")

# --- HELPER FUNCTIONS ---
def human_readable_size(size):
    if not size: return "0B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0: return f"{size:.2f}{unit}"
        size /= 1024.0
    return f"{size:.2f}TB"

def time_formatter(seconds):
    if seconds is None or seconds < 0: return "..."
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0: return f"{hours}h {minutes}m {seconds}s"
    return f"{minutes}m {seconds}s"

# --- PROGRESS CALLBACK (Optimized) ---
async def progress_callback(current, total, start_time, file_name):
    global last_update_time, status_message
    now = time.time()
    
    if now - last_update_time < 8: return  # Reduced update frequency (5s -> 8s)
    last_update_time = now
    
    percentage = current * 100 / total if total > 0 else 0
    time_diff = now - start_time
    speed = current / time_diff if time_diff > 0 else 0
    eta = (total - current) / speed if speed > 0 else 0
    
    filled = math.floor(percentage / 10)
    bar = "█" * filled + "░" * (10 - filled)
    
    try:
        await status_message.edit(
            f"⚡️ **Format Enforcer (MP4/JPG)**\n"
            f"📂 `{file_name}`\n"
            f"**{bar} {round(percentage, 1)}%**\n"
            f"🚀 `{human_readable_size(speed)}/s` | ⏳ `{time_formatter(eta)}`\n"
            f"💾 `{human_readable_size(current)} / {human_readable_size(total)}`"
        )
    except Exception: pass

# --- ULTRA BUFFERED STREAM (Enhanced) ---
class UltraBufferedStream:
    def __init__(self, client, location, file_size, file_name, start_time):
        self.client = client
        self.location = location
        self.file_size = file_size
        self.name = file_name
        self.start_time = start_time
        self.current_bytes = 0
        self.chunk_size = 16 * 1024 * 1024  # 16MB Chunk (was 8MB)
        self.queue = asyncio.Queue(maxsize=8)  # Increased buffer (was 5)
        self.downloader_task = asyncio.create_task(self._worker())
        self.buffer = b""

    async def _worker(self):
        try:
            async for chunk in self.client.iter_download(self.location, chunk_size=self.chunk_size):
                await self.queue.put(chunk)
            await self.queue.put(None) 
        except Exception as e:
            logger.error(f"Stream Worker Error: {e}")
            await self.queue.put(None)

    def __len__(self):
        return self.file_size

    async def read(self, size=-1):
        if size == -1: size = self.chunk_size
        while len(self.buffer) < size:
            chunk = await self.queue.get()
            if chunk is None: 
                if self.current_bytes < self.file_size:
                    raise errors.RpcCallFailError("Incomplete Stream")
                break
            self.buffer += chunk
            self.current_bytes += len(chunk)
            asyncio.create_task(progress_callback(self.current_bytes, self.file_size, self.start_time, self.name))
        data = self.buffer[:size]
        self.buffer = self.buffer[size:]
        return data

# --- SMART FORMAT ENFORCER ---
def get_target_info(message):
    """Format enforcement with caching optimization"""
    original_name = "Unknown_File"
    target_mime = "application/octet-stream"
    force_video = False
    
    if isinstance(message.media, MessageMediaWebPage):
        return None, None, False

    if message.file:
        original_mime = message.file.mime_type
        if message.file.name:
            original_name = message.file.name
        else:
            ext = mimetypes.guess_extension(original_mime) or ""
            original_name = f"File_{message.id}{ext}"
    else:
        original_mime = "image/jpeg"
        original_name = f"Image_{message.id}.jpg"

    base_name = os.path.splitext(original_name)[0]
    
    if "video" in original_mime or original_name.lower().endswith(('.mkv', '.avi', '.webm', '.mov', '.flv')):
        final_name = base_name + ".mp4"
        target_mime = "video/mp4"
        force_video = True
        
    elif "image" in original_mime:
        final_name = base_name + ".jpg"
        target_mime = "image/jpeg"
        force_video = False
        
    elif "pdf" in original_mime or original_name.lower().endswith('.pdf'):
        final_name = base_name + ".pdf"
        target_mime = "application/pdf"
        force_video = False
        
    else:
        final_name = original_name
        target_mime = original_mime
        force_video = False
        
    return final_name, target_mime, force_video

# --- PARALLEL TRANSFER PROCESS (NEW!) ---
async def process_single_message(message, source_id, dest_id, sem):
    """Process single message with semaphore control"""
    async with sem:
        retries = 3
        success = False
        
        while retries > 0 and not success:
            try:
                fresh_msg = await user_client.get_messages(source_id, ids=message.id)
                if not fresh_msg: break 

                file_name, mime_type, is_video_mode = get_target_info(fresh_msg)
                
                if not file_name:
                    if fresh_msg.text:
                        await bot_client.send_message(dest_id, fresh_msg.text)
                        success = True
                    else:
                        success = True
                    continue

                start_time = time.time()
                
                attributes = []
                attributes.append(DocumentAttributeFilename(file_name=file_name))
                
                if hasattr(fresh_msg, 'document') and fresh_msg.document:
                    for attr in fresh_msg.document.attributes:
                        if isinstance(attr, DocumentAttributeVideo):
                            attributes.append(DocumentAttributeVideo(
                                duration=attr.duration,
                                w=attr.w,
                                h=attr.h,
                                supports_streaming=True
                            ))

                # Thumbnail download optimized (smaller size)
                thumb = await user_client.download_media(fresh_msg, thumb=-1) if is_video_mode else None
                
                media_obj = fresh_msg.media.document if hasattr(fresh_msg.media, 'document') else fresh_msg.media.photo
                
                stream_file = UltraBufferedStream(
                    user_client, 
                    media_obj,
                    fresh_msg.file.size,
                    file_name,
                    start_time
                )
                
                await bot_client.send_file(
                    dest_id,
                    file=stream_file,
                    caption=fresh_msg.text or "",
                    attributes=attributes,
                    thumb=thumb,
                    supports_streaming=True,
                    file_size=fresh_msg.file.size,
                    force_document=not is_video_mode,
                    part_size_kb=16384  # Increased (was 8192)
                )
                
                if thumb and os.path.exists(thumb): os.remove(thumb)
                success = True

            except (errors.FileReferenceExpiredError, errors.MediaEmptyError):
                logger.warning(f"Ref Expired on {message.id}, refreshing...")
                retries -= 1
                await asyncio.sleep(1)  # Reduced from 2s
                continue 
                
            except errors.FloodWaitError as e:
                logger.warning(f"FloodWait {e.seconds}s")
                await asyncio.sleep(e.seconds)
            
            except Exception as e:
                logger.error(f"Failed {message.id}: {e}")
                retries -= 1
                await asyncio.sleep(1)

        return success, message.id

# --- TRANSFER PROCESS (Parallel Processing) ---
async def transfer_process(event, source_id, dest_id, start_msg, end_msg):
    global is_running, status_message
    
    status_message = await event.respond(f"🔥 **Format Enforcer Engine Started!**\nSource: `{source_id}`")
    total_processed = 0
    failed_messages = []
    
    # Semaphore for parallel control (3 concurrent transfers)
    sem = asyncio.Semaphore(3)
    
    try:
        # Fetch all messages first (batch operation)
        messages = []
        async for message in user_client.iter_messages(source_id, min_id=start_msg-1, max_id=end_msg+1, reverse=True):
            if not is_running: break
            if not getattr(message, 'action', None):
                messages.append(message)
        
        # Process in parallel batches
        tasks = []
        for message in messages:
            if not is_running: break
            task = asyncio.create_task(process_single_message(message, source_id, dest_id, sem))
            tasks.append(task)
            
            # Process in batches of 10
            if len(tasks) >= 10:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, tuple) and result[0]:
                        total_processed += 1
                    elif isinstance(result, tuple):
                        failed_messages.append(result[1])
                tasks = []
                
                # Update status
                try:
                    await status_message.edit(
                        f"⚡️ **Processing...**\n"
                        f"✅ Done: `{total_processed}`\n"
                        f"❌ Failed: `{len(failed_messages)}`"
                    )
                except: pass
        
        # Process remaining tasks
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, tuple) and result[0]:
                    total_processed += 1
                elif isinstance(result, tuple):
                    failed_messages.append(result[1])

        if is_running:
            status_text = f"✅ **Job Done!**\nTotal Processed: `{total_processed}`"
            if failed_messages:
                status_text += f"\n❌ Failed: `{len(failed_messages)}` messages"
            await status_message.edit(status_text)

    except Exception as e:
        await status_message.edit(f"❌ **Critical Error:** {e}")
    finally:
        is_running = False

# --- COMMANDS ---
@bot_client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    await event.respond("🟢 **Ultra Bot (MP4 Enforcer) Ready!**\n`/clone Source Dest`")

@bot_client.on(events.NewMessage(pattern='/clone'))
async def clone_init(event):
    global is_running
    if is_running: return await event.respond("⚠️ Busy in another task...")
    try:
        args = event.text.split()
        pending_requests[event.chat_id] = {'source': int(args[1]), 'dest': int(args[2])}
        await event.respond("✅ **Set!** Send Range Link (e.g., `https://t.me/c/xxx/10 - https://t.me/c/xxx/20`)")
    except: await event.respond("❌ Usage: `/clone -100xxx -100yyy`")

@bot_client.on(events.NewMessage())
async def range_listener(event):
    global current_task, is_running
    if event.chat_id not in pending_requests or "t.me" not in event.text: return
    try:
        links = event.text.strip().split("-")
        msg1, msg2 = int(links[0].split("/")[-1]), int(links[1].split("/")[-1])
        if msg1 > msg2: msg1, msg2 = msg2, msg1
        
        data = pending_requests.pop(event.chat_id)
        is_running = True
        current_task = asyncio.create_task(transfer_process(event, data['source'], data['dest'], msg1, msg2))
    except Exception as e: await event.respond(f"❌ Error: {e}")

@bot_client.on(events.NewMessage(pattern='/stop'))
async def stop_handler(event):
    global is_running
    is_running = False
    if current_task: current_task.cancel()
    await event.respond("🛑 **Stopped!**")

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    user_client.start()
    loop.create_task(start_web_server())
    bot_client.start(bot_token=BOT_TOKEN)
    logger.warning("Bot is Running...")
    bot_client.run_until_disconnected()

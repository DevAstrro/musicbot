# Discord Music Bot (Slash Command Edition)

A high-performance Discord music bot developed by **@Downloads\AsTRRoMC.zip**. This bot features native Slash Commands, YouTube search Autocomplete, and a natural, human-readable interface.

## 🚀 Key Features
- **Native Slash Commands**: Intuitive `/` command menu integration.
- **Search Autocomplete**: Real-time YouTube search results as you type.
- **Natural Interface**: Human-readable responses and descriptions (no robotic brackets or underscores).
- **High-Quality Audio**: Advanced DSP signal processing and high-bitrate streaming.
- **Control Panel**: Real-time playback control via interactive buttons.
- **Session Persistence**: 24/7 mode to keep the bot in your voice channel.
- **Locking Mechanisms**: Restrict the bot to specific servers or text channels.

## 🛠️ Setup

1. **Install FFmpeg**:
   Ensure `ffmpeg` is installed and added to your system's PATH.

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment**:
   Create a `.env` file and add your bot token:
   ```env
   DISCORD_TOKEN=your_token_here
   ```

4. **Run the Bot**:
   ```bash
   python bot.py
   ```

## 🎮 Commands

### Music Controls
- `/play <search>`: Play a song from YouTube or a direct URL.
- `/pause`: Pause the current music.
- `/resume`: Resume playback.
- `/skip`: Skip to the next song in the queue.
- `/stop`: Stop the music and disconnect.
- `/queue`: View the upcoming tracks.
- `/history`: View recently played songs.
- `/volume <0-100>`: Adjust the audio output level.

### System & Management
- `/help`: Show the list of available commands.
- `/ping`: Check the bot's connection latency.
- `/247`: Toggle persistent connection mode.
- `/filter`: Apply audio effects (Bassboost, Nightcore, etc.).
- `/lockserver`: (Owner only) Lock the bot to the current server.
- `/lockchannel`: (Owner only) Lock the bot to the current text channel.
- `/reload`: (Admin only) Restart the bot system.

## 🔄 Synchronization
If slash commands do not appear immediately, use the `!sync` text command (Owner only) to force a global update.

## 📜 License
This project is licensed under the MIT License.

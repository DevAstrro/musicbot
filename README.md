# Discord Music Bot (Slash Command Edition)

A high-performance Discord music bot developed by **@astrromc (discord)**. This bot features native Slash Commands, YouTube search Autocomplete, and a natural, human-readable interface.

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

## 🚀 Deployment

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://www.heroku.com/deploy/?template=https://github.com/DevAstrro/musicbot)
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/DevAstrro/musicbot)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/DevAstrro/musicbot)

### 1. Heroku
- Add the **Python** buildpack.
- Add the **FFmpeg** buildpack: `https://github.com/jonathanong/heroku-buildpack-ffmpeg-latest.git`
- Set your `DISCORD_TOKEN` in the Config Vars.

### 2. Railway
- Connect your GitHub repo.
- Railway will automatically detect the `Dockerfile` and deploy it with all dependencies (including FFmpeg).
- Set your `DISCORD_TOKEN` in the Variables tab.

### 3. Render
- Create a new **Web Service** or **Background Worker**.
- Connect your GitHub repo.
- Render will use the `Dockerfile` automatically.
- Set your `DISCORD_TOKEN` in the Environment Variables.

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

## 🛠️ Troubleshooting (YouTube "Sign in" Error)

If you see an error like "Sign in to prove you're not a bot", follow these steps to secure your bot:

1. **Install Browser Extension**: Install [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/ccmclabjmapocbbgdhnkonpjjhakyclj) (Chrome/Edge).
2. **Export Cookies**: Go to YouTube, log in, click the extension, and click **Export**.
3. **Copy Content**: Open the downloaded `cookies.txt` and copy **all the text** inside.
4. **Add to Hosting**: 
   - Go to your hosting platform (Render/Railway/Heroku).
   - Create a new **Environment Variable** named **`YT_COOKIES`**.
   - Paste the copied text as the value and save.
5. **Re-deploy**: Clear build cache and deploy. The bot will now use these cookies securely without exposing them on GitHub.

## 📜 License
This project is licensed under the MIT License.

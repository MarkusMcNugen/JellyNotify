# Jellynouncer

<div align="center">
  <img src="images/Jellynouncer_Full.png" alt="Jellynouncer Logo" width="50%">
</div>

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://hub.docker.com/r/markusmcnugen/jellynouncer)
[![GitHub Issues](https://img.shields.io/github/issues/MarkusMcNugen/Jellynouncer)](https://github.com/MarkusMcNugen/Jellynouncer/issues)
[![GitHub Stars](https://img.shields.io/github/stars/MarkusMcNugen/Jellynouncer?style=social)](https://github.com/MarkusMcNugen/Jellynouncer/stargazers)
[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/MarkusMcNugen/Jellynouncer/releases)

</div>

## 📖 Overview

**Jellynouncer** is an advanced intermediary webhook service that bridges Jellyfin media server with Discord, providing intelligent notifications for media library changes. It goes beyond simple "new item" alerts by detecting quality upgrades, managing multi-channel routing, and offering extensive customization through Jinja2 templates.

The service acts as a smart filter between Jellyfin's webhook events and Discord notifications, analyzing changes to determine what's truly noteworthy - distinguishing between new content additions and quality improvements like resolution upgrades (1080p → 4K) or HDR additions.

> ⚠️ **BETA SOFTWARE NOTICE**
> 
> This software is currently in beta development. While core functionality is stable, you may encounter bugs or edge cases. Please report any issues you find to help improve the service.

## ✨ Key Features

### 🧠 Smart Change Detection
- **Intelligent Analysis**: Distinguishes between new content and quality upgrades
- **Technical Detection**: Identifies resolution improvements, codec upgrades (H.264 → H.265), audio enhancements (Stereo → 7.1), and HDR additions
- **Content Hashing**: Uses fingerprinting to prevent duplicate notifications while catching meaningful changes
- **Customizable Triggers**: Configure which changes warrant notifications

### 🚀 Multi-Channel Discord Routing
- **Content-Type Routing**: Automatically routes movies, TV shows, and music to different Discord channels
- **Flexible Webhooks**: Support for unlimited custom webhooks with granular control
- **Smart Fallback**: Ensures no notifications are lost with configurable fallback webhooks
- **Grouping Options**: Batch notifications by event type or content type

### 🎨 Advanced Template System
- **Jinja2 Templates**: Fully customizable Discord embed messages
- **Rich Media Information**: Display posters, technical specs, ratings, cast, and plot summaries
- **Multiple Templates**: Different templates for new items, upgrades, and grouped notifications
- **Dynamic Content**: Templates can access all media metadata and technical information

### 📊 External Metadata Integration
- **Rating Services**: Integrates with OMDb, TMDb, and TVDB for ratings and additional metadata
- **Poster Management**: Automatic thumbnail generation and caching for Discord embeds
- **Fallback Handling**: Gracefully handles API failures without breaking notifications

### ⚡ Production-Ready Features
- **Database Persistence**: SQLite with WAL mode for concurrent access and change tracking
- **Rate Limiting**: Respects Discord API limits with configurable rate limiting
- **Retry Logic**: Exponential backoff for network resilience
- **Background Sync**: Periodic library synchronization to catch missed webhooks
- **Health Monitoring**: Built-in health checks and diagnostic endpoints
- **Structured Logging**: Comprehensive logging with rotation and multiple output levels

### 🔧 DevOps Friendly
- **Docker-First Design**: Optimized container with multi-stage builds
- **Environment Overrides**: All settings configurable via environment variables
- **Configuration Validation**: Automatic validation with detailed error reporting
- **Graceful Shutdown**: Proper cleanup and queue processing on shutdown

## 🚀 Quick Start

### Prerequisites

- **Jellyfin Server** 10.8+ with [Webhook Plugin](https://github.com/jellyfin/jellyfin-plugin-webhook) installed
- **Discord Server** with webhook creation permissions
- **Docker** (recommended) or Python 3.11+ for manual installation

### Docker Compose (Recommended)

1. **Create directory structure:**
```bash
mkdir jellynouncer && cd jellynouncer
mkdir config data logs templates
```

2. **Create `docker-compose.yml`:**
```yaml
version: '3.8'

services:
  jellynouncer:
    image: markusmcnugen/jellynouncer:latest
    container_name: jellynouncer
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      # Required
      - JELLYFIN_SERVER_URL=http://your-jellyfin-server:8096
      - JELLYFIN_API_KEY=your_api_key_here
      - JELLYFIN_USER_ID=your_user_id_here
      - DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your/webhook
      
      # Optional: Content-specific webhooks
      - DISCORD_WEBHOOK_URL_MOVIES=https://discord.com/api/webhooks/movies
      - DISCORD_WEBHOOK_URL_TV=https://discord.com/api/webhooks/tv
      - DISCORD_WEBHOOK_URL_MUSIC=https://discord.com/api/webhooks/music
      
      # Optional: External APIs for enhanced metadata
      - OMDB_API_KEY=your_omdb_key
      - TMDB_API_KEY=your_tmdb_key
      - TVDB_API_KEY=your_tvdb_key
      
      # System
      - PUID=1000
      - PGID=1000
      - TZ=America/New_York
      - LOG_LEVEL=INFO
    volumes:
      - ./config:/app/config
      - ./data:/app/data
      - ./logs:/app/logs
      - ./templates:/app/templates
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 300s
      timeout: 10s
      retries: 3
      start_period: 10s
```

3. **Start the service:**
```bash
docker-compose up -d
```

4. **Configure Jellyfin Webhook Plugin:**
   - Go to Jellyfin Dashboard → Plugins → Webhook
   - Add new webhook with URL: `http://your-server:8080/webhook`
   - Enable "Item Added" event
   - Check "Send All Properties"
   - Save configuration

### Docker Run

1. **Run the container:**
```bash
docker run -d \
  --name jellynouncer \
  --restart unless-stopped \
  -p 8080:8080 \
  -e JELLYFIN_SERVER_URL=http://jellyfin:8096 \
  -e JELLYFIN_API_KEY=your_api_key \
  -e JELLYFIN_USER_ID=your_user_id \
  -e DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/... \
  -v ./config:/app/config \
  -v ./data:/app/data \
  -v ./logs:/app/logs \
  -v ./templates:/app/templates \
  markusmcnugen/jellynouncer:latest
```

2. **Configure Jellyfin Webhook Plugin:**
   - Go to Jellyfin Dashboard → Plugins → Webhook
   - Add new webhook with URL: `http://your-server:8080/webhook`
   - Enable "Item Added" event
   - Check "Send All Properties"
   - Save configuration

## ⚙️ Configuration

### Getting API Keys

#### Jellyfin Credentials
1. **API Key**: Dashboard → API Keys → Add Key
2. **User ID**: Dashboard → Users → Select User → Copy ID from URL

#### Discord Webhook
1. Server Settings → Integrations → Webhooks
2. Create webhook for desired channel
3. Copy webhook URL

#### Optional External APIs
- **OMDb**: Free key at [omdbapi.com](http://www.omdbapi.com/apikey.aspx) (1,000 requests/day)
- **TMDb**: Free at [themoviedb.org](https://www.themoviedb.org/settings/api)
- **TVDB**: Register at [thetvdb.com](https://thetvdb.com/api-information)

### Advanced Configuration

Create `config/config.json` for advanced settings:

```json
{
  "jellyfin": {
    "server_url": "http://jellyfin:8096",
    "api_key": "your_key",
    "user_id": "your_id"
  },
  "discord": {
    "webhooks": {
      "movies": {
        "url": "https://discord.com/api/webhooks/...",
        "enabled": true,
        "grouping": {
          "mode": "both",
          "delay_minutes": 5,
          "max_items": 20
        }
      }
    },
    "routing": {
      "enabled": true,
      "fallback_webhook": "default"
    }
  },
  "notifications": {
    "watch_changes": {
      "resolution": true,
      "codec": true,
      "audio_codec": true,
      "hdr_status": true
    }
  }
}
```

**📚 [Complete Configuration Guide →](config/Readme.md)**

## 🔄 How It Works

### Architecture Overview

```mermaid
graph TD
    A[Jellyfin Server] -->|Webhook Event| B[FastAPI Endpoint]
    B --> C[WebhookService]
    
    C --> D[Media Processing]
    D --> E[Database Check]
    E --> F{New or Update?}
    
    F -->|New Item| G[Fetch Metadata]
    F -->|Update| H[Change Detection]
    
    G --> I[Template Rendering]
    H --> I
    
    I --> J[Discord Routing]
    J --> K[Rate Limiting]
    K --> L[Discord Channels]
    
    C --> M[Background Tasks]
    M --> N[Library Sync]
    M --> O[Queue Processing]
    
    %% External Services (Blue)
    style A fill:#1976d2,stroke:#0d47a1,stroke-width:2px,color:#fff
    style L fill:#5865f2,stroke:#4752c4,stroke-width:2px,color:#fff
    
    %% Core Service (Purple)
    style B fill:#9c27b0,stroke:#6a1b9a,stroke-width:2px,color:#fff
    style C fill:#7b1fa2,stroke:#4a148c,stroke-width:2px,color:#fff
    
    %% Processing Components (Green)
    style D fill:#4caf50,stroke:#2e7d32,stroke-width:2px,color:#fff
    style E fill:#66bb6a,stroke:#388e3c,stroke-width:2px,color:#fff
    style F fill:#43a047,stroke:#2e7d32,stroke-width:2px,color:#fff
    
    %% Metadata & Enhancement (Orange)
    style G fill:#ff9800,stroke:#f57c00,stroke-width:2px,color:#fff
    style H fill:#ffa726,stroke:#fb8c00,stroke-width:2px,color:#fff
    
    %% Output Processing (Teal)
    style I fill:#26a69a,stroke:#00897b,stroke-width:2px,color:#fff
    style J fill:#00acc1,stroke:#00838f,stroke-width:2px,color:#fff
    style K fill:#00bcd4,stroke:#0097a7,stroke-width:2px,color:#fff
    
    %% Background Tasks (Pink)
    style M fill:#ec407a,stroke:#c2185b,stroke-width:2px,color:#fff
    style N fill:#f06292,stroke:#e91e63,stroke-width:2px,color:#fff
    style O fill:#f48fb1,stroke:#f06292,stroke-width:2px,color:#fff
```

### Detailed Component Flow

#### 1. **Webhook Reception & Validation**
```
Jellyfin Event → Webhook Plugin → POST /webhook → FastAPI Validation → WebhookPayload Model
```
- Jellyfin detects library changes and triggers webhook
- FastAPI validates incoming payload structure
- Pydantic models ensure type safety and data integrity

#### 2. **Media Processing Pipeline**
```
WebhookService → Extract Media Info → Database Lookup → Change Detection → Classification
```
- Extract comprehensive media information from webhook payload
- Query SQLite database for existing item history
- Analyze differences using content hashing algorithm
- Classify as new item or quality upgrade

#### 3. **Metadata Enhancement**
```
JellyfinAPI → External Services (OMDb/TMDb/TVDB) → Metadata Aggregation → Cache Storage
```
- Fetch additional details from Jellyfin API
- Query external services for ratings and additional metadata
- Aggregate all metadata into unified MediaItem object
- Cache results to reduce API calls

#### 4. **Notification Generation**
```
Template Selection → Jinja2 Rendering → Discord Embed Creation → Webhook Routing
```
- Select appropriate template based on item type and change type
- Render template with media metadata and technical information
- Generate Discord-compatible JSON embed structure
- Route to appropriate webhook based on content type

#### 5. **Delivery & Reliability**
```
Rate Limiter → Discord API → Retry Logic → Success/Failure Handling → Queue Management
```
- Apply rate limiting to respect Discord API limits
- Send notification to Discord webhook endpoint
- Implement exponential backoff for failed attempts
- Queue notifications during rate limit periods

### Background Services

1. **Library Synchronization**: Periodically syncs with Jellyfin to ensure database consistency
2. **Queue Processing**: Manages notification batching and grouped notifications
3. **Health Monitoring**: Tracks service health and external API availability
4. **Database Maintenance**: Performs WAL checkpoints and optimization

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook` | POST | Main webhook receiver from Jellyfin |
| `/webhook/debug` | POST | Debug endpoint with detailed analysis |
| `/health` | GET | Service health and status |
| `/stats` | GET | Database and processing statistics |
| `/sync` | POST | Trigger manual library synchronization |
| `/webhooks` | GET | List configured Discord webhooks |
| `/queues` | GET | Show notification queue status |
| `/flush-queues` | POST | Process all pending notifications |
| `/test-webhook` | POST | Send test notification |
| `/validate-templates` | GET | Validate all templates with sample data |

### Example API Usage

```bash
# Check service health
curl http://localhost:8080/health

# View statistics
curl http://localhost:8080/stats

# Trigger sync
curl -X POST http://localhost:8080/sync

# Test specific webhook
curl -X POST "http://localhost:8080/test-webhook?webhook_name=movies"

# Validate templates
curl http://localhost:8080/validate-templates
```

## 🎨 Templates

Jellynouncer uses Jinja2 templates for complete control over Discord embed formatting.

### Template Types

- **Individual**: `new_item.j2`, `upgraded_item.j2`
- **Grouped by Event**: `new_items_by_event.j2`, `upgraded_items_by_event.j2`
- **Grouped by Type**: `new_items_by_type.j2`, `upgraded_items_by_type.j2`
- **Fully Grouped**: `new_items_grouped.j2`, `upgraded_items_grouped.j2`

### Available Variables

```jinja2
{{ item.name }}              # Media title
{{ item.year }}              # Release year
{{ item.overview }}          # Plot summary
{{ item.video_height }}      # Resolution (1080, 2160)
{{ item.video_codec }}       # Codec (h264, hevc)
{{ item.audio_codec }}       # Audio codec
{{ item.audio_channels }}    # Channel layout (2.0, 5.1, 7.1)
{{ item.video_range }}       # HDR type (SDR, HDR, HDR10+, DV)
{{ item.imdb_rating }}       # IMDb rating
{{ item.genres }}            # Genre list
{{ item.cast }}              # Cast members
```

**📚 [Complete Template Guide →](templates/Readme.md)**

## 🔧 Manual Installation

### Requirements
- Python 3.11+
- SQLite 3
- Git

### Installation Steps

1. **Clone repository:**
```bash
git clone https://github.com/MarkusMcNugen/Jellynouncer.git
cd Jellynouncer
```

2. **Create virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure:**
```bash
cp config/config.json.example config/config.json
# Edit config.json with your settings
```

5. **Run:**
```bash
python main.py
```

6. **Configure Jellyfin Webhook Plugin:**
   - Go to Jellyfin Dashboard → Plugins → Webhook
   - Add new webhook with URL: `http://your-server:8080/webhook`
   - Enable "Item Added" event
   - Check "Send All Properties"
   - Save configuration

### Systemd Service (Linux)

Create `/etc/systemd/system/jellynouncer.service`:

```ini
[Unit]
Description=Jellynouncer Discord Webhook Service
After=network.target

[Service]
Type=simple
User=jellynouncer
WorkingDirectory=/opt/jellynouncer
Environment="PATH=/opt/jellynouncer/venv/bin"
ExecStart=/opt/jellynouncer/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable jellynouncer
sudo systemctl start jellynouncer
```

## 🛠️ Troubleshooting

### Common Issues

**No notifications received:**
- Verify Jellyfin webhook plugin is configured correctly
- Check webhook URL points to `http://your-server:8080/webhook`
- Confirm Discord webhook URLs are valid
- Review logs for connection errors

**Database errors:**
```bash
# Check permissions
ls -la data/

# Reset database (loses history)
rm data/jellynouncer.db
docker restart jellynouncer
```

**Rate limiting issues:**
- Reduce `max_items` in grouping configuration
- Increase `delay_minutes` for batching
- Check Discord rate limits in logs

### Debug Mode

Enable detailed logging:

```yaml
# Docker Compose
environment:
  - LOG_LEVEL=DEBUG
```

```bash
# Manual
export LOG_LEVEL=DEBUG
python main.py
```

### Log Locations

- **Application**: `logs/jellynouncer.log`
- **Debug**: `logs/jellynouncer-debug.log` (when DEBUG enabled)
- **Container**: `docker logs jellynouncer`

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Configuration Guide](config/Readme.md) | Complete configuration reference |
| [Template Guide](templates/Readme.md) | Template customization and examples |

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Code Style

- Python 3.11+ with type hints
- PEP 8 compliance (Black formatter, 88 char limit)
- Google-style docstrings
- Comprehensive error handling

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Jellyfin](https://jellyfin.org/) for the amazing media server
- [Discord](https://discord.com/) for the webhook API
- All contributors and users of this project

## 💬 Support

- **Issues**: [GitHub Issues](https://github.com/MarkusMcNugen/Jellynouncer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/MarkusMcNugen/Jellynouncer/discussions)

---

**Made with ☕ by Mark Newton**

*If you find this project useful, please consider giving it a ⭐ on GitHub!*

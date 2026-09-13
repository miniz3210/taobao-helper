# 📦 Taobao & Freight Forwarding Helper

A comprehensive web application for tracking Taobao purchase orders, managing freight forwarding consolidations, and querying purchase history using AI-powered natural language search.

## 🌟 Features

### Core Capabilities
- **📊 Order Management**: Track all your Taobao purchases with automatic state synchronization
- **🔄 Automatic Syncing**: Fetch orders from Taobao using session cookies
- **📸 Local Snapshot Archiving**: Permanent storage of product images (survives CDN expiration)
- **🗄️ SQLite Database**: Long-term archival with full purchase history
- **📅 Timeline Tracking**: Order Date → Pay Date → Ship Date → Receive Date
- **🔍 State Differential Engine**: Automatic detection and logging of order status changes

### Freight Forwarding
- **📦 Consolidation Management**: Group multiple orders under one forwarder tracking number
- **📋 Customs Declaration Export**: One-click generation of customs forms (.xlsx/.csv)
- **🚚 Multi-Stage Tracking**: Pending → Consolidating → In Transit → Delivered

### AI-Powered Search
- **🤖 Natural Language Queries**: Ask questions like "What toothbrush did I buy in 2025?"
- **🖼️ Visual Results**: AI responses include product images and detailed information
- **🔗 Database Integration**: Direct SQL queries combined with LLM intelligence
- **🌐 Multi-Provider Support**: Works with OpenAI GPT, Google Gemini, or local LLMs

### Backup & Export
- **💾 Full System Backup**: One-click backup of database + all snapshots (.zip)
- **📤 Restore Functionality**: Complete disaster recovery capability
- **📊 Excel/CSV Export**: Export complete purchase history with all metadata
- **📝 Notes Generator**: Auto-generated text summaries with copy-to-clipboard

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- (Optional) OpenAI API key or Google Gemini API key for AI features

### Installation

1. **Clone or download the project**
```bash
cd /opt/taobao-helper
```

2. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env and add your API keys if using AI features
```

3. **Build and run with Docker**
```bash
docker-compose up -d
```

4. **Access the application**
- Open browser: http://localhost:8000
- API documentation: http://localhost:8000/docs

The application will automatically:
- Initialize the SQLite database
- Create necessary directories for data storage
- Mount persistent volumes for data/snapshots

## 📁 Project Structure

```
taobao-helper/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── database.py             # Database configuration
│   ├── models/                 # SQLAlchemy models
│   │   ├── order.py
│   │   ├── forwarder.py
│   │   └── system_log.py
│   ├── modules/                # Core business logic
│   │   ├── backup_export_engine.py
│   │   ├── image_archiver.py
│   │   ├── taobao_scraper.py
│   │   ├── notes_generator.py
│   │   ├── consolidation_manager.py
│   │   └── ai_assistant.py
│   ├── templates/              # HTML templates
│   │   └── index.html
│   └── static/                 # Static assets
├── data/                       # Persistent data (mounted volume)
│   ├── taobao_helper.db       # SQLite database
│   ├── snapshots/             # Product images
│   ├── backups/               # System backups
│   └── exports/               # Excel/CSV exports
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## 🎯 Usage Guide

### 1. Syncing Orders from Taobao

**Important**: This application requires Taobao session cookies to fetch orders.

1. Log into Taobao in your browser
2. Open Developer Tools (F12) → Application/Storage → Cookies
3. Copy all cookies as a string (e.g., `cookie1=value1; cookie2=value2`)
4. In the app, click "🔄 Sync Taobao" and paste your cookies
5. Click "Sync Now"

**Note**: The scraping module in this release is a placeholder. You may need to implement actual Taobao HTML/API parsing based on Taobao's current structure, which changes frequently.

### 2. Manual Order Entry

For testing or manual record-keeping:
1. Click "➕ Add Order"
2. Fill in order details
3. Optionally provide a snapshot image URL
4. Submit

### 3. AI Query Assistant

Ask natural language questions about your purchase history:
- "What toothbrush brands did I buy last year?"
- "Show me all items over 100 RMB"
- "When did I order that blue shirt?"

The AI will:
1. Parse your query
2. Search the database
3. Return results with product images
4. Provide conversational explanations

### 4. Freight Forwarding Consolidation

When items arrive at your freight forwarder:
1. Go to "Consolidation" tab
2. Click "➕ Create Consolidation"
3. Enter the forwarder's master tracking number
4. Select which orders to consolidate
5. Export customs declaration form

### 5. Backup & Export

**Create Backup**:
- Click "📥 Download System Backup" in Settings
- Saves a .zip with database + all images

**Restore Backup**:
- Click "📤 Restore from Backup"
- Upload your .zip or .db file
- System will restore all data

**Export History**:
- "📊 Export to Excel" - Full history spreadsheet
- "📄 Export to CSV" - CSV format for data processing

## 🔧 Configuration

### Database
The SQLite database is located at `/app/data/taobao_helper.db` inside the container, mounted to `./data/taobao_helper.db` on the host.

### Environment Variables

Edit `.env`:

```env
# AI Provider API Keys (choose one or more)
OPENAI_API_KEY=sk-your-key-here
GEMINI_API_KEY=your-key-here

# Database (default is fine)
DATABASE_URL=sqlite:///./data/taobao_helper.db

# Timezone
TZ=Asia/Hong_Kong
```

### Timezone
Default is `Asia/Hong_Kong`. Change in `docker-compose.yml` and `.env` if needed.

## 📊 Database Schema

### Orders Table
- `order_id` (PK): Taobao order identifier
- `item_title`: Full product title
- `ai_clean_title`: AI-generated short title
- `price`, `quantity`: Pricing information
- `seller_name`, `seller_express_no`, `carrier`: Seller info
- `order_date`, `pay_date`, `ship_date`, `receive_date`: Timeline
- `current_status`: pending_shipment, in_transit, received, cancelled
- `forwarder_tracking_no`: Link to consolidation
- `snapshot_local_path`: Local image file path
- `created_at`, `updated_at`: Timestamps

### Forwarder Trackings Table
- `tracking_no` (PK): Forwarder master tracking
- `status`: pending_consolidation, consolidating, in_transit, delivered
- `consolidation_date`, `ship_date`, `delivery_date`: Timeline
- `notes`: Additional information

### System Logs Table
- Event logging for state changes, scrapes, exports, backups

## 🔌 API Endpoints

### Orders
- `GET /api/orders` - List all orders
- `GET /api/orders/{order_id}` - Get specific order
- `POST /api/orders` - Create order manually
- `DELETE /api/orders/{order_id}` - Delete order

### Scraping
- `POST /api/scrape` - Sync from Taobao with cookies

### AI
- `POST /api/ai-query` - Natural language query

### Consolidation
- `GET /api/forwarders` - List all forwarder trackings
- `GET /api/forwarders/{tracking_no}` - Get orders for forwarder
- `POST /api/consolidation/bind` - Bind orders to forwarder
- `POST /api/consolidation/unbind/{order_id}` - Remove binding
- `PUT /api/forwarders/status` - Update forwarder status
- `GET /api/consolidation/export/{tracking_no}` - Export customs form

### Backup & Export
- `GET /api/backup/create` - Download system backup
- `POST /api/backup/restore` - Upload and restore backup
- `GET /api/export/excel` - Export to Excel
- `GET /api/export/csv` - Export to CSV

### Utilities
- `GET /api/notes` - Get generated notes
- `GET /api/stats` - Get statistics
- `GET /api/logs` - Get system logs
- `GET /api/health` - Health check

Full API documentation: http://localhost:8000/docs

## 🛠️ Development

### Local Development (without Docker)

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=sqlite:///./data/taobao_helper.db
export OPENAI_API_KEY=your-key

# Create data directory
mkdir -p data/snapshots

# Run the application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Customizing Taobao Scraper

The `app/modules/taobao_scraper.py` contains placeholder scraping logic. To implement actual scraping:

1. Study Taobao's current HTML structure
2. Implement parsing in `fetch_orders_from_taobao()`
3. Handle pagination and rate limiting
4. Test with actual cookies

Example structure to parse:
```python
async def fetch_orders_from_taobao(self, cookies: str) -> List[Dict]:
    cookie_dict = self._parse_cookies(cookies)
    
    # Make request to Taobao
    response = await self.client.get(
        "https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm",
        cookies=cookie_dict
    )
    
    # Parse HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extract order data
    orders = []
    for order_element in soup.find_all('div', class_='order-item'):
        order = {
            'order_id': extract_order_id(order_element),
            'item_title': extract_title(order_element),
            'price': extract_price(order_element),
            # ... more fields
        }
        orders.append(order)
    
    return orders
```

## 🔒 Security Notes

- **Cookie Storage**: Session cookies are only used in memory and not persisted
- **Database**: SQLite database contains purchase history; secure the `data/` directory
- **API Keys**: Store in `.env` file, never commit to version control
- **Backups**: Backup files contain sensitive data; store securely

## 🐛 Troubleshooting

### Database Locked Error
SQLite only supports one writer at a time. If you get "database is locked" errors:
- Ensure only one instance is running
- Check for zombie processes
- Restart the container

### Images Not Loading
- Check `/app/data/snapshots` directory permissions
- Verify snapshot URLs are valid
- Check Docker volume mount: `docker-compose logs`

### AI Not Working
- Verify API keys in `.env`
- Check API key validity
- Ensure `litellm` package is installed
- Review logs: `docker-compose logs -f`

### Scraping Not Working
- Verify cookies are valid and fresh
- Check if logged into Taobao
- Taobao's structure may have changed (requires code update)
- Check rate limiting

## 📝 License

This project is provided as-is for personal use.

## 🤝 Contributing

This is a personal project, but improvements are welcome:
1. Implement actual Taobao scraping logic
2. Add more AI providers
3. Improve UI/UX
4. Add automated tests
5. Support for other e-commerce platforms

## ⚠️ Disclaimer

This tool is for personal purchase tracking only. Users are responsible for:
- Complying with Taobao's Terms of Service
- Securing their own data
- Proper customs declaration

## 📞 Support

For issues or questions:
1. Check the troubleshooting section
2. Review logs: `docker-compose logs -f`
3. Inspect API docs: http://localhost:8000/docs

---

**Version**: 1.0.0  
**Last Updated**: 2026-09-13  
**Timezone**: Asia/Hong_Kong (HKT/UTC+8)

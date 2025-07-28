# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Setup and Environment
```bash
# Install Python dependencies
cd backend
pip install -r requirements.txt
playwright install

# Install frontend dependencies (optional - has simple.html fallback)
cd frontend
npm install

# Start the full system (both backend and frontend)
./start.sh

# Start backend only (with simple HTML frontend)
cd backend
python app.py

# Start frontend development server
cd frontend
npm run serve

# Testing
cd backend
python ../test_system.py
```

### Prerequisites
- Python 3.8+
- Node.js 14+ (optional - for advanced frontend)
- Playwright browser automation
- Redis (optional - for enhanced task queuing)

## Architecture

This is a full-stack Apple Store automation system that evolved from a single-script bot into a scalable web application.

### Core Components

**Backend (`backend/`)**
- **app.py** - Flask main application with REST API endpoints and WebSocket support
- **task_manager.py** - Orchestrates concurrent task execution (default max 3 tasks)
- **automation_service.py** - Core Playwright automation logic based on original apple_automator.py
- **websocket_handler.py** - Real-time communication for task status updates
- **models/task.py** - Task data models with status tracking and configuration
- **models/database.py** - SQLite database for accounts and gift cards management
- **services/ip_service.py** - Proxy rotation service for avoiding rate limits
- **config/config.py** - Environment-based configuration management

**Frontend (`frontend/`)**
- **simple.html** - Lightweight single-file interface (served at root)
- **src/App.vue** - Full Vue.js application (optional)
- **src/components/** - Vue components for task management and monitoring
- **src/services/websocket.js** - Real-time WebSocket client
- **src/store/index.js** - Vuex state management

**Data Files**
- **iphone_products_clean.json** - Product configuration data from scraping
- **iphone_urls.json** - URL mappings for different iPhone models

### Task Flow Architecture

1. **Task Creation** - REST API accepts product configurations and creates tasks
2. **Concurrent Execution** - TaskManager spawns separate automation processes
3. **Browser Isolation** - Each task runs in isolated Playwright browser context
4. **Real-time Updates** - WebSocket broadcasts task progress to connected clients
5. **Database Persistence** - Accounts and gift cards stored in SQLite
6. **Proxy Management** - Optional IP rotation for enhanced anonymity

### Key Automation Steps

The automation service follows this precise workflow:

1. **Initialize Browser** - Playwright chromium with specific locale settings
2. **Navigate to Product** - Load iPhone product URL 
3. **Configure Product** - Skip size/color/memory, only configure:
   - Apple Trade In: "No trade-in"
   - Payment: "Buy" 
   - AppleCare: "No AppleCare+ Coverage"
4. **Add to Bag** - Multiple fallback strategies for add-to-cart buttons
5. **Review Bag & Checkout** - Navigate through shopping bag to checkout
6. **Apple ID Login** - Handle both iframe and direct login forms
7. **Address & Phone** - Fill shipping information and phone number
8. **Gift Card Application** - Apply gift card if configured
9. **Purchase Preparation** - Reach final purchase screen but stop for manual confirmation

### Database Schema

**Accounts Table**
- id, email, password, phone_number, created_at, updated_at, is_active

**Gift Cards Table** 
- id, gift_card_number, status (has_balance/zero_balance/error), notes, created_at, updated_at, is_active

### API Endpoints

**Task Management**
- `GET /api/tasks` - List all tasks
- `POST /api/tasks` - Create new task
- `POST /api/tasks/<id>/start` - Start task execution
- `POST /api/tasks/<id>/cancel` - Cancel running task

**Configuration**
- `GET /api/config/product-options` - Get iPhone models, colors, storage options
- `GET /api/config/iphone-configs` - Get detailed iPhone configurations

**Account Management**
- `GET/POST/PUT/DELETE /api/accounts` - CRUD operations for Apple accounts

**Gift Card Management**  
- `GET/POST/PUT/DELETE /api/gift-cards` - CRUD operations for gift cards

**System Status**
- `GET /api/system/status` - Current system status and active tasks
- `POST /api/system/rotate-ip` - Manual IP rotation trigger

### WebSocket Events

- `task_created` - New task added
- `task_update` - Task status/progress changed  
- `task_log` - Real-time log messages from automation

### Configuration Management

**Environment Variables**
- `MAX_CONCURRENT_TASKS` - Maximum parallel tasks (default: 3)
- `PROXY_ROTATION_ENABLED` - Enable proxy rotation
- `PROXY_API_URL` - Proxy service endpoint
- `FLASK_CONFIG` - Environment (development/production)

**Product Configuration Format**
```json
{
  "name": "Task Name",
  "url": "https://www.apple.com/uk/shop/buy-iphone/...",
  "product_config": {
    "model": "iPhone 16 Pro 6.3-inch display",
    "finish": "Natural Titanium", 
    "storage": "256GB",
    "trade_in": "No trade-in",
    "payment": "Buy",
    "apple_care": "No AppleCare+ Coverage"
  },
  "account_config": {
    "email": "your@email.com",
    "password": "password",
    "phone_number": "07700900000"
  },
  "gift_cards": [{"number": "XXXX", "expected_status": "has_balance"}],
  "use_proxy": false
}
```

### Error Handling & Debugging

The system includes comprehensive error handling:
- Task-level error capturing and logging
- Screenshot capture on automation failures
- HTML page dumps for debugging
- Detailed WebSocket error broadcasting
- Database transaction rollbacks

Debug files are created in `backend/` directory:
- `debug_gift_card_<task_id>.log` - Gift card application debugging
- `debug_gift_card_<task_id>.html` - Page HTML snapshots
- `error_gift_card_<task_id>.png` - Error screenshots
- `final_purchase_<task_id>.png` - Final state screenshots

### Security Considerations

- Browser contexts are isolated per task
- No actual purchase execution (stops at confirmation screen)
- Sensitive data (passwords) only in database/memory, not logs
- Optional proxy rotation for anonymity
- Rate limiting through concurrent task caps

### Browser Automation Patterns

The automation service uses sophisticated selection strategies:
- Multiple fallback selectors for each UI element
- Retry mechanisms with exponential backoff
- Smart element detection (visible, enabled, clickable checks)
- Contextual element finding (within fieldsets, forms)
- Cross-browser compatibility patterns
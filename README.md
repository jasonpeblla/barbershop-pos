# 💈 Barbershop POS

A complete Point of Sale system for barbershops, featuring walk-in queue management, barber scheduling, service menu, commission tracking, and customer history.

## ✨ Features

### Core POS
- ✂️ **Service Menu** - Haircuts, beard services, combos, and add-ons with customizable pricing
- 💰 **Payment Processing** - Cash, card, Apple Pay with automatic tax calculation
- 🧾 **Receipt Generation** - Print-ready receipts with shop branding
- 📝 **Service Notes** - Add special instructions per service (fade style, length, etc.)

### Queue Management
- 📋 **Walk-in Queue** - Real-time queue with position tracking
- ⏱️ **Wait Time Estimates** - Automatic calculation based on queue length
- 📢 **Customer Calling** - Mark customers as called when it's their turn
- 🔄 **Quick Service Start** - Jump to POS directly from queue

### Appointments
- 📅 **Appointment Booking** - Multi-step booking wizard
- 🕐 **Available Time Slots** - Automatic slot availability based on barber schedules
- 👤 **Barber Preference** - Request specific barbers for appointments

### Barber Management
- 👔 **Clock In/Out** - Track barber work hours
- 📊 **Commission Tracking** - Automatic commission calculation per barber
- 💵 **Tip Handling** - Track tips per service
- 📈 **Earnings Reports** - Period-based earnings summaries

### Customer Management
- 👤 **Customer Profiles** - Store preferences, notes, and contact info
- 📜 **Visit History** - Complete service history with spending stats
- ⭐ **Favorite Services** - Track most-used services per customer

### Retail
- 🛍️ **Product Sales** - Sell hair products, styling tools, etc.
- 📦 **Inventory Tracking** - Stock levels with low-stock alerts
- 🏷️ **Product Categories** - Styling, beard care, hair care, tools

### Business Tools
- 💰 **Cash Drawer** - Open/close, add/remove cash with reconciliation
- 📊 **Daily Reports** - Revenue, tips, customer count, avg ticket
- 📈 **Earnings Reports** - Barber commission and tips summaries
- 📝 **Feedback System** - Bug reports and feature requests

## 🛠️ Tech Stack

- **Backend**: FastAPI + SQLite (Python 3.9+)
- **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS

## 🚀 Quick Start

### Backend
```bash
cd ~/barbershop-pos
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

### Frontend
```bash
cd ~/barbershop-pos/frontend
npm install
npm run dev
```

## 🌐 Ports

| Service | URL |
|---------|-----|
| Backend API | http://localhost:8002 |
| Frontend | http://localhost:3004 |
| API Docs | http://localhost:8002/docs |

## 📡 API Endpoints

### Customers
- `GET /customers/` - List customers
- `GET /customers/search?q=` - Search by phone/name
- `POST /customers/` - Create customer
- `GET /customers/{id}/history` - Customer visit history

### Services
- `GET /services/` - List all services
- `GET /services/categories` - Get categories

### Barbers
- `GET /barbers/` - List barbers
- `GET /barbers/available` - Available barbers
- `POST /barbers/{id}/clock-in` - Clock in
- `POST /barbers/{id}/clock-out` - Clock out
- `GET /barbers/{id}/earnings` - Commission report

### Queue
- `GET /queue/` - Current queue
- `POST /queue/` - Add to queue
- `POST /queue/{id}/call` - Call customer
- `POST /queue/{id}/remove` - Remove from queue
- `GET /queue/stats` - Queue statistics

### Orders
- `GET /orders/` - List orders
- `POST /orders/` - Create order
- `PATCH /orders/{id}/status` - Update status
- `GET /orders/{id}/receipt` - Get receipt

### Appointments
- `GET /appointments/` - List appointments
- `GET /appointments/available-slots` - Get available times
- `POST /appointments/` - Book appointment
- `DELETE /appointments/{id}` - Cancel appointment

### Payments
- `POST /payments/` - Process payment

### Products
- `GET /products/` - List products
- `POST /products/sell` - Record sale
- `GET /products/low-stock` - Low stock alerts

### Cash Drawer
- `GET /cash-drawer/status` - Drawer status
- `POST /cash-drawer/open` - Open drawer
- `POST /cash-drawer/close` - Close & reconcile
- `POST /cash-drawer/add` - Add cash
- `POST /cash-drawer/remove` - Remove cash

### Reports
- `GET /reports/daily` - Daily summary
- `GET /reports/earnings` - Barber earnings
- `GET /reports/services` - Service popularity
- `GET /reports/customers/top` - Top customers

### Feedback
- `POST /feedback/` - Submit feedback
- `GET /feedback/` - List feedback

## 📁 Project Structure

```
barbershop-pos/
├── app/
│   ├── main.py           # FastAPI app entry
│   ├── database.py       # SQLite connection
│   ├── models.py         # SQLAlchemy models
│   └── routers/          # API endpoints
│       ├── customers.py
│       ├── barbers.py
│       ├── services.py
│       ├── orders.py
│       ├── payments.py
│       ├── queue.py
│       ├── appointments.py
│       ├── reports.py
│       ├── products.py
│       ├── cash_drawer.py
│       └── feedback.py
├── frontend/
│   ├── src/
│   │   ├── App.tsx       # Main React app
│   │   ├── main.tsx      # Entry point
│   │   └── index.css     # Tailwind styles
│   ├── package.json
│   └── vite.config.ts
├── memory/               # Development notes
├── requirements.txt
└── README.md
```

## 📄 License

MIT

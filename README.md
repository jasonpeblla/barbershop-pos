# Barbershop POS

A complete Point of Sale system for barbershops, featuring walk-in queue management, barber scheduling, service menu, commission tracking, and customer history.

## Features

- 💈 **Service Menu** - Haircuts, beard services, combos, and add-ons
- 📋 **Walk-in Queue** - Real-time queue management with estimated wait times
- ✂️ **Barber Management** - Track availability, clock in/out, and commissions
- 💰 **Commission Tracking** - Automatic commission calculation per barber
- 💵 **Tip Handling** - Easy tip entry with percentage presets
- 👤 **Customer History** - Track preferences, visits, and spending
- 📊 **Reports** - Daily summaries and earnings reports

## Tech Stack

- **Backend**: FastAPI + SQLite
- **Frontend**: React + Vite + Tailwind CSS

## Quick Start

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

## Ports

- Backend API: http://localhost:8002
- Frontend: http://localhost:3004
- API Docs: http://localhost:8002/docs

## API Endpoints

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

### Payments
- `POST /payments/` - Process payment

### Reports
- `GET /reports/daily` - Daily summary
- `GET /reports/earnings` - Barber earnings
- `GET /reports/services` - Service popularity
- `GET /reports/customers/top` - Top customers

# 🥐 Sweet Crumbs — Bakery Management System
**SAD Project | Flask + SQLite + HTML/CSS**

## Project Structure
```
bakery/
├── app.py                  ← Flask backend (all routes & DB logic)
├── bakery.db               ← SQLite database (auto-created)
├── requirements.txt
├── static/
│   ├── css/style.css       ← Warm artisan theme
│   ├── js/main.js          ← Image drag-drop & preview
│   └── uploads/            ← Product images stored here
└── templates/
    ├── base.html           ← Layout with sidebar navigation
    ├── index.html          ← Dashboard with stats
    ├── products.html       ← Product list + search/filter
    ├── product_form.html   ← Add / Edit product (with image upload)
    ├── customers.html      ← Customer list + search
    ├── customer_form.html  ← Add / Edit customer
    ├── orders.html         ← Orders list + status filter
    ├── order_form.html     ← New order (dynamic multi-item)
    └── order_detail.html   ← Order detail + status update
```

## Database Schema
- **category** — product categories (Bread, Pastry, Cake, Cookie, Drink)
- **product** — bakery items with name, price, stock, image
- **customer** — customer records
- **order** — order header (customer, total, status)
- **order_item** — line items linking order ↔ product

## Setup & Run
```bash
# 1. Install dependencies
pip install flask werkzeug

# 2. Run the app
python app.py

# 3. Open in browser
# http://127.0.0.1:5000
```

## CRUD Features
| Module    | Create | Read | Update | Delete |
|-----------|--------|------|--------|--------|
| Products  | ✅ + image upload | ✅ search/filter | ✅ | ✅ |
| Customers | ✅ | ✅ search | ✅ | ✅ |
| Orders    | ✅ multi-item | ✅ filter by status | ✅ status | ✅ |

## SAD Diagrams (in project report)
- Use Case Diagram
- DFD Level 0 (Context)
- DFD Level 1 (Processes)
- ERD (Entity Relationship Diagram)
- System Flowchart

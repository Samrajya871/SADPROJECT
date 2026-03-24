from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from functools import wraps
import sqlite3
import os
import logging
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-key-change-in-production')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

DB_PATH = os.getenv('DB_PATH', 'bakery.db')

# ── Role permissions map ──────────────────────────────────────────────────────
# admin   → full access
# manager → products, customers, orders (no user management)
# staff   → orders only (read + create)

ROLE_PERMISSIONS = {
    'admin':   {'dashboard','products','customers','orders','users'},
    'manager': {'dashboard','products','customers','orders'},
    'staff':   {'dashboard','orders'},
}

# ── Input Validation ──────────────────────────────────────────────────────────

def validate_username(username):
    """Validate username format"""
    if not username or len(username) < 3 or len(username) > 50:
        return False
    return username.replace('_', '').replace('-', '').isalnum()

def validate_email(email):
    """Validate email format"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 6:
        return False, 'Password must be at least 6 characters'
    return True, ''

def sanitize_input(text):
    """Sanitize user input"""
    if not isinstance(text, str):
        return ''
    return text.strip()[:500]

# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f'Database connection error: {e}')
        raise

def init_db():
    try:
        conn = get_db()
        c = conn.cursor()
        c.executescript('''
            CREATE TABLE IF NOT EXISTS staff (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'staff',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS category (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS product (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL,
                stock_qty INTEGER NOT NULL DEFAULT 0,
                category_id INTEGER,
                image_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES category(id)
            );

            CREATE TABLE IF NOT EXISTS customer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                address TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS "order" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                total_price REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                order_date TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customer(id)
            );

            CREATE TABLE IF NOT EXISTS order_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES "order"(id),
                FOREIGN KEY (product_id) REFERENCES product(id)
            );
        ''')

        # Seed categories
        c.execute("SELECT COUNT(*) FROM category")
        if c.fetchone()[0] == 0:
            for cat in ['Bread', 'Pastry', 'Cake', 'Cookie', 'Drink']:
                c.execute("INSERT INTO category (name) VALUES (?)", (cat,))

        # Seed default admin account
        c.execute("SELECT COUNT(*) FROM staff")
        if c.fetchone()[0] == 0:
            accounts = [
                ('Admin User',    'admin',   'admin123',   'admin'),
                ('Store Manager', 'manager', 'manager123', 'manager'),
                ('Floor Staff',   'staff',   'staff123',   'staff'),
            ]
            for name, uname, pwd, role in accounts:
                c.execute("INSERT INTO staff (name, username, password_hash, role) VALUES (?,?,?,?)",
                          (name, uname, generate_password_hash(pwd), role))

        conn.commit()
        logger.info('Database initialized successfully')
    except Exception as e:
        logger.error(f'Database initialization error: {e}')
    finally:
        conn.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ── Auth decorators ───────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'info')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def requires_permission(module):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            role = session.get('role', 'staff')
            if module not in ROLE_PERMISSIONS.get(role, set()):
                logger.warning(f'Access denied for user {session.get("user_id")} to module {module}')
                flash(f'Access denied. Your role ({role}) cannot access {module}.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator

# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        try:
            username = sanitize_input(request.form.get('username', ''))
            password = request.form.get('password', '')
            
            if not username or not password:
                flash('Username and password are required.', 'danger')
                return render_template('login.html')
            
            conn = get_db()
            user = conn.execute("SELECT * FROM staff WHERE username=? AND active=1", (username,)).fetchone()
            conn.close()
            
            if user and check_password_hash(user['password_hash'], password):
                session.clear()
                session['user_id']   = user['id']
                session['username']  = user['username']
                session['name']      = user['name']
                session['role']      = user['role']
                logger.info(f'User {username} logged in successfully')
                flash(f'Welcome back, {user["name"]}!', 'success')
                return redirect(url_for('index'))
            logger.warning(f'Failed login attempt for username: {username}')
            flash('Invalid username or password.', 'danger')
        except Exception as e:
            logger.error(f'Login error: {e}')
            flash('An error occurred during login.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    username = session.get('username', 'Unknown')
    session.clear()
    logger.info(f'User {username} logged out')
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    try:
        conn = get_db()
        stats = {
            'products': conn.execute("SELECT COUNT(*) FROM product").fetchone()[0],
            'customers': conn.execute("SELECT COUNT(*) FROM customer").fetchone()[0],
            'orders': conn.execute("SELECT COUNT(*) FROM \"order\"").fetchone()[0],
            'revenue': conn.execute("SELECT COALESCE(SUM(total_price),0) FROM \"order\" WHERE status='completed'").fetchone()[0],
            'pending': conn.execute("SELECT COUNT(*) FROM \"order\" WHERE status='pending'").fetchone()[0],
            'low_stock': conn.execute("SELECT COUNT(*) FROM product WHERE stock_qty < 5").fetchone()[0],
        }
        recent_orders = conn.execute('''
            SELECT o.id, c.name as customer_name, o.total_price, o.status, o.order_date
            FROM \"order\" o JOIN customer c ON o.customer_id = c.id
            ORDER BY o.order_date DESC LIMIT 5
        ''').fetchall()
        conn.close()
        return render_template('index.html', stats=stats, recent_orders=recent_orders)
    except Exception as e:
        logger.error(f'Dashboard error: {e}')
        flash('Error loading dashboard.', 'danger')
        return render_template('index.html', stats={}, recent_orders=[])

# ── Users (admin only) ────────────────────────────────────────────────────────

@app.route('/users')
@requires_permission('users')
def users():
    try:
        conn = get_db()
        staff = conn.execute("SELECT id,name,username,role,active,created_at FROM staff ORDER BY created_at DESC").fetchall()
        conn.close()
        return render_template('users.html', staff=staff)
    except Exception as e:
        logger.error(f'Users page error: {e}')
        flash('Error loading users.', 'danger')
        return redirect(url_for('index'))

@app.route('/users/add', methods=['GET','POST'])
@requires_permission('users')
def add_user():
    if request.method == 'POST':
        try:
            name     = sanitize_input(request.form.get('name', ''))
            username = sanitize_input(request.form.get('username', ''))
            password = request.form.get('password', '')
            role     = request.form.get('role', 'staff')
            
            if not all([name, username, password]):
                flash('All fields are required.', 'danger')
                return render_template('user_form.html', user=None)
            
            if not validate_username(username):
                flash('Invalid username format.', 'danger')
                return render_template('user_form.html', user=None)
            
            valid, msg = validate_password(password)
            if not valid:
                flash(msg, 'danger')
                return render_template('user_form.html', user=None)
            
            conn = get_db()
            conn.execute("INSERT INTO staff (name,username,password_hash,role) VALUES (?,?,?,?)",
                        (name, username, generate_password_hash(password), role))
            conn.commit()
            conn.close()
            logger.info(f'New staff member added: {username}')
            flash(f'Staff member "{name}" added!', 'success')
        except sqlite3.IntegrityError:
            logger.warning(f'Duplicate username attempt: {username}')
            flash('Username already taken.', 'danger')
        except Exception as e:
            logger.error(f'Error adding user: {e}')
            flash('Error adding staff member.', 'danger')
        return redirect(url_for('users'))
    return render_template('user_form.html', user=None)

@app.route('/users/edit/<int:uid>', methods=['GET','POST'])
@requires_permission('users')
def edit_user(uid):
    try:
        conn = get_db()
        user = conn.execute("SELECT * FROM staff WHERE id=?", (uid,)).fetchone()
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('users'))
        if request.method == 'POST':
            name     = sanitize_input(request.form.get('name', ''))
            username = sanitize_input(request.form.get('username', ''))
            role     = request.form.get('role', 'staff')
            active   = 1 if request.form.get('active') else 0
            new_pwd  = request.form.get('password','').strip()
            
            if not all([name, username]):
                flash('Name and username are required.', 'danger')
                return render_template('user_form.html', user=user)
            
            if not validate_username(username):
                flash('Invalid username format.', 'danger')
                return render_template('user_form.html', user=user)
            
            try:
                if new_pwd:
                    valid, msg = validate_password(new_pwd)
                    if not valid:
                        flash(msg, 'danger')
                        return render_template('user_form.html', user=user)
                    conn.execute("UPDATE staff SET name=?,username=?,role=?,active=?,password_hash=? WHERE id=?",
                                (name, username, role, active, generate_password_hash(new_pwd), uid))
                else:
                    conn.execute("UPDATE staff SET name=?,username=?,role=?,active=? WHERE id=?",
                                (name, username, role, active, uid))
                conn.commit()
                logger.info(f'User updated: {username}')
                flash('User updated!', 'success')
                conn.close()
                return redirect(url_for('users'))
            except sqlite3.IntegrityError:
                logger.warning(f'Duplicate username in update: {username}')
                flash('Username already taken.', 'danger')
                conn.close()
                return render_template('user_form.html', user=user)
        return render_template('user_form.html', user=user)
    except Exception as e:
        logger.error(f'Error editing user: {e}')
        flash('Error editing user.', 'danger')
        return redirect(url_for('users'))
    
    return render_template('user_form.html', user=user)

@app.route('/users/delete/<int:uid>', methods=['POST'])
@requires_permission('users')
def delete_user(uid):
    try:
        if uid == session.get('user_id'):
            flash("You can't delete your own account.", 'danger')
            return redirect(url_for('users'))
        conn = get_db()
        user = conn.execute("SELECT username FROM staff WHERE id=?", (uid,)).fetchone()
        conn.execute("DELETE FROM staff WHERE id=?", (uid,))
        conn.commit()
        conn.close()
        logger.info(f'User deleted: {user["username"] if user else "Unknown"}')
        flash('User deleted.', 'danger')
    except Exception as e:
        logger.error(f'Error deleting user: {e}')
        flash('Error deleting user.', 'danger')
    return redirect(url_for('users'))

# ── Profile (change own password) ────────────────────────────────────────────

@app.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    try:
        conn = get_db()
        user = conn.execute("SELECT * FROM staff WHERE id=?", (session['user_id'],)).fetchone()
        if request.method == 'POST':
            current = request.form.get('current_password', '')
            new_pwd = request.form.get('new_password', '')
            confirm = request.form.get('confirm_password', '')
            
            if not check_password_hash(user['password_hash'], current):
                flash('Current password is incorrect.', 'danger')
            elif new_pwd != confirm:
                flash('New passwords do not match.', 'danger')
            else:
                valid, msg = validate_password(new_pwd)
                if not valid:
                    flash(msg, 'danger')
                else:
                    conn.execute("UPDATE staff SET password_hash=? WHERE id=?",
                                (generate_password_hash(new_pwd), session['user_id']))
                    conn.commit()
                    logger.info(f'Password changed for user: {user["username"]}')
                    flash('Password changed successfully!', 'success')
        conn.close()
        return render_template('profile.html', user=user)
    except Exception as e:
        logger.error(f'Profile error: {e}')
        flash('Error updating profile.', 'danger')
        return redirect(url_for('index'))

# ── Products ──────────────────────────────────────────────────────────────────

@app.route('/products')
@requires_permission('products')
def products():
    try:
        conn = get_db()
        search = sanitize_input(request.args.get('search', ''))
        cat_filter = request.args.get('category', '')
        query = '''SELECT p.*, c.name as category_name FROM product p
                   LEFT JOIN category c ON p.category_id = c.id WHERE 1=1'''
        params = []
        if search:
            query += " AND p.name LIKE ?"
            params.append(f'%{search}%')
        if cat_filter:
            query += " AND p.category_id = ?"
            params.append(cat_filter)
        query += " ORDER BY p.created_at DESC"
        products = conn.execute(query, params).fetchall()
        categories = conn.execute("SELECT * FROM category ORDER BY name").fetchall()
        conn.close()
        return render_template('products.html', products=products, categories=categories,
                               search=search, cat_filter=cat_filter)
    except Exception as e:
        logger.error(f'Products page error: {e}')
        flash('Error loading products.', 'danger')
        return redirect(url_for('index'))

@app.route('/products/add', methods=['GET', 'POST'])
@requires_permission('products')
def add_product():
    try:
        conn = get_db()
        categories = conn.execute("SELECT * FROM category ORDER BY name").fetchall()
        if request.method == 'POST':
            try:
                name = sanitize_input(request.form.get('name', ''))
                desc = sanitize_input(request.form.get('description', ''))
                price = float(request.form.get('price', 0))
                stock = int(request.form.get('stock_qty', 0))
                cat_id = request.form.get('category_id') or None
                image_path = None
                
                if not name or price < 0 or stock < 0:
                    flash('Invalid product data.', 'danger')
                    return render_template('product_form.html', categories=categories, product=None)
                
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename and allowed_file(file.filename):
                        try:
                            filename = secure_filename(file.filename)
                            ts = datetime.now().strftime('%Y%m%d%H%M%S')
                            filename = f"{ts}_{filename}"
                            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                            image_path = filename
                            logger.info(f'Image uploaded: {filename}')
                        except Exception as e:
                            logger.error(f'Image upload failed: {str(e)}')
                            flash(f'Failed to upload image: {str(e)}', 'danger')
                            return render_template('product_form.html', categories=categories, product=None)
                    elif file and file.filename:
                        flash('Invalid image format. Allowed: PNG, JPG, JPEG, GIF, WEBP', 'danger')
                        return render_template('product_form.html', categories=categories, product=None)
                
                conn.execute('INSERT INTO product (name,description,price,stock_qty,category_id,image_path) VALUES (?,?,?,?,?,?)',
                            (name, desc, price, stock, cat_id, image_path))
                conn.commit()
                logger.info(f'Product added: {name}')
                flash('Product added!', 'success')
            except ValueError:
                flash('Invalid price or stock value.', 'danger')
                return render_template('product_form.html', categories=categories, product=None)
            conn.close()
            return redirect(url_for('products'))
        conn.close()
        return render_template('product_form.html', categories=categories, product=None)
    except ValueError:
        flash('Invalid price or stock value.', 'danger')
        return render_template('product_form.html', categories=categories, product=None)
    except Exception as e:
        logger.error(f'Error adding product: {e}')
        flash('Error adding product.', 'danger')
        return redirect(url_for('products'))

@app.route('/products/edit/<int:pid>', methods=['GET', 'POST'])
@requires_permission('products')
def edit_product(pid):
    try:
        conn = get_db()
        categories = conn.execute("SELECT * FROM category ORDER BY name").fetchall()
        product = conn.execute("SELECT * FROM product WHERE id=?", (pid,)).fetchone()
        if not product:
            flash('Product not found.', 'danger')
            return redirect(url_for('products'))
        if request.method == 'POST':
            try:
                name = sanitize_input(request.form.get('name', ''))
                desc = sanitize_input(request.form.get('description', ''))
                price = float(request.form.get('price', 0))
                stock = int(request.form.get('stock_qty', 0))
                cat_id = request.form.get('category_id') or None
                image_path = product['image_path']
                
                if not name or price < 0 or stock < 0:
                    flash('Invalid product data.', 'danger')
                    return render_template('product_form.html', categories=categories, product=product)
                
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename and allowed_file(file.filename):
                        try:
                            filename = secure_filename(file.filename)
                            ts = datetime.now().strftime('%Y%m%d%H%M%S')
                            filename = f"{ts}_{filename}"
                            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                            image_path = filename
                            logger.info(f'Image uploaded: {filename}')
                        except Exception as e:
                            logger.error(f'Image upload failed: {str(e)}')
                            flash(f'Failed to upload image: {str(e)}', 'danger')
                            conn.close()
                            return render_template('product_form.html', categories=categories, product=product)
                    elif file and file.filename:
                        flash('Invalid image format. Allowed: PNG, JPG, JPEG, GIF, WEBP', 'danger')
                        conn.close()
                        return render_template('product_form.html', categories=categories, product=product)
                
                conn.execute('UPDATE product SET name=?,description=?,price=?,stock_qty=?,category_id=?,image_path=? WHERE id=?',
                            (name, desc, price, stock, cat_id, image_path, pid))
                conn.commit()
                logger.info(f'Product updated: {name}')
                flash('Product updated!', 'success')
            except ValueError:
                flash('Invalid price or stock value.', 'danger')
                return render_template('product_form.html', categories=categories, product=product)
            conn.close()
            return redirect(url_for('products'))
        conn.close()
        return render_template('product_form.html', categories=categories, product=product)
    except ValueError:
        flash('Invalid price or stock value.', 'danger')
        return redirect(url_for('products'))
    except Exception as e:
        logger.error(f'Error editing product: {e}')
        flash('Error editing product.', 'danger')
        return redirect(url_for('products'))

@app.route('/products/delete/<int:pid>', methods=['POST'])
@requires_permission('products')
def delete_product(pid):
    try:
        conn = get_db()
        product = conn.execute("SELECT * FROM product WHERE id=?", (pid,)).fetchone()
        if product and product['image_path']:
            img = os.path.join(app.config['UPLOAD_FOLDER'], product['image_path'])
            if os.path.exists(img):
                os.remove(img)
        conn.execute("DELETE FROM product WHERE id=?", (pid,))
        conn.commit()
        conn.close()
        logger.info(f'Product deleted: {product["name"] if product else "Unknown"}')
        flash('Product deleted.', 'danger')
    except Exception as e:
        logger.error(f'Error deleting product: {e}')
        flash('Error deleting product.', 'danger')
    return redirect(url_for('products'))

# ── Customers ─────────────────────────────────────────────────────────────────

@app.route('/customers')
@requires_permission('customers')
def customers():
    try:
        conn = get_db()
        search = sanitize_input(request.args.get('search', ''))
        query = "SELECT * FROM customer WHERE 1=1"
        params = []
        if search:
            query += " AND (name LIKE ? OR email LIKE ?)"
            params.extend([f'%{search}%', f'%{search}%'])
        query += " ORDER BY created_at DESC"
        customers = conn.execute(query, params).fetchall()
        conn.close()
        return render_template('customers.html', customers=customers, search=search)
    except Exception as e:
        logger.error(f'Customers page error: {e}')
        flash('Error loading customers.', 'danger')
        return redirect(url_for('index'))

@app.route('/customers/add', methods=['GET', 'POST'])
@requires_permission('customers')
def add_customer():
    if request.method == 'POST':
        try:
            name = sanitize_input(request.form.get('name', ''))
            email = sanitize_input(request.form.get('email', ''))
            phone = sanitize_input(request.form.get('phone', ''))
            address = sanitize_input(request.form.get('address', ''))
            
            if not all([name, email]):
                flash('Name and email are required.', 'danger')
                return render_template('customer_form.html', customer=None)
            
            if not validate_email(email):
                flash('Invalid email format.', 'danger')
                return render_template('customer_form.html', customer=None)
            
            conn = get_db()
            conn.execute("INSERT INTO customer (name,email,phone,address) VALUES (?,?,?,?)",
                        (name, email, phone, address))
            conn.commit()
            conn.close()
            logger.info(f'Customer added: {name}')
            flash('Customer added!', 'success')
        except sqlite3.IntegrityError:
            logger.warning(f'Duplicate email: {email}')
            flash('Email already exists.', 'danger')
        except Exception as e:
            logger.error(f'Error adding customer: {e}')
            flash('Error adding customer.', 'danger')
        return redirect(url_for('customers'))
    return render_template('customer_form.html', customer=None)

@app.route('/customers/edit/<int:cid>', methods=['GET', 'POST'])
@requires_permission('customers')
def edit_customer(cid):
    try:
        conn = get_db()
        customer = conn.execute("SELECT * FROM customer WHERE id=?", (cid,)).fetchone()
        if not customer:
            flash('Customer not found.', 'danger')
            return redirect(url_for('customers'))
        if request.method == 'POST':
            name = sanitize_input(request.form.get('name', ''))
            email = sanitize_input(request.form.get('email', ''))
            phone = sanitize_input(request.form.get('phone', ''))
            address = sanitize_input(request.form.get('address', ''))
            
            if not all([name, email]):
                flash('Name and email are required.', 'danger')
                return render_template('customer_form.html', customer=customer)
            
            if not validate_email(email):
                flash('Invalid email format.', 'danger')
                return render_template('customer_form.html', customer=customer)
            
            try:
                conn.execute("UPDATE customer SET name=?,email=?,phone=?,address=? WHERE id=?",
                            (name, email, phone, address, cid))
                conn.commit()
                logger.info(f'Customer updated: {name}')
                flash('Customer updated!', 'success')
                conn.close()
                return redirect(url_for('customers'))
            except sqlite3.IntegrityError:
                logger.warning(f'Duplicate email in update: {email}')
                flash('Email already in use.', 'danger')
                conn.close()
                return render_template('customer_form.html', customer=customer)
        conn.close()
        return render_template('customer_form.html', customer=customer)
    except Exception as e:
        logger.error(f'Error editing customer: {e}')
        flash('Error editing customer.', 'danger')
        return redirect(url_for('customers'))
    
    return render_template('customer_form.html', customer=customer)

@app.route('/customers/delete/<int:cid>', methods=['POST'])
@requires_permission('customers')
def delete_customer(cid):
    try:
        conn = get_db()
        customer = conn.execute("SELECT name FROM customer WHERE id=?", (cid,)).fetchone()
        conn.execute("DELETE FROM customer WHERE id=?", (cid,))
        conn.commit()
        conn.close()
        logger.info(f'Customer deleted: {customer["name"] if customer else "Unknown"}')
        flash('Customer deleted.', 'danger')
    except Exception as e:
        logger.error(f'Error deleting customer: {e}')
        flash('Error deleting customer.', 'danger')
    return redirect(url_for('customers'))

# ── Orders ────────────────────────────────────────────────────────────────────

@app.route('/orders')
@requires_permission('orders')
def orders():
    try:
        conn = get_db()
        status_filter = request.args.get('status', '')
        query = '''SELECT o.id, c.name as customer_name, o.total_price, o.status, o.order_date
                   FROM \"order\" o JOIN customer c ON o.customer_id = c.id WHERE 1=1'''
        params = []
        if status_filter:
            query += " AND o.status=?"
            params.append(status_filter)
        query += " ORDER BY o.order_date DESC"
        orders = conn.execute(query, params).fetchall()
        conn.close()
        return render_template('orders.html', orders=orders, status_filter=status_filter)
    except Exception as e:
        logger.error(f'Orders page error: {e}')
        flash('Error loading orders.', 'danger')
        return redirect(url_for('index'))

@app.route('/orders/add', methods=['GET', 'POST'])
@requires_permission('orders')
def add_order():
    try:
        conn = get_db()
        customers = conn.execute("SELECT * FROM customer ORDER BY name").fetchall()
        products = [dict(r) for r in conn.execute(
            "SELECT p.*, c.name as cat FROM product p LEFT JOIN category c ON p.category_id=c.id WHERE p.stock_qty > 0 ORDER BY p.name"
        ).fetchall()]
        if request.method == 'POST':
            customer_id = int(request.form.get('customer_id', 0))
            product_ids = request.form.getlist('product_id[]')
            quantities  = request.form.getlist('quantity[]')
            total = 0.0
            items = []
            
            if not customer_id:
                flash('Please select a customer.', 'danger')
                return render_template('order_form.html', customers=customers, products=products)
            
            for pid, qty in zip(product_ids, quantities):
                try:
                    pid, qty = int(pid), int(qty)
                except ValueError:
                    continue
                if qty <= 0:
                    continue
                prod = conn.execute("SELECT * FROM product WHERE id=?", (pid,)).fetchone()
                if prod and prod['stock_qty'] >= qty:
                    total += prod['price'] * qty
                    items.append((pid, qty, prod['price']))
            
            if not items:
                flash('No valid items in order.', 'danger')
                return render_template('order_form.html', customers=customers, products=products)
            
            cur = conn.execute('INSERT INTO \"order\" (customer_id, total_price) VALUES (?,?)', (customer_id, total))
            oid = cur.lastrowid
            for pid, qty, uprice in items:
                conn.execute("INSERT INTO order_item (order_id,product_id,quantity,unit_price) VALUES (?,?,?,?)",
                            (oid, pid, qty, uprice))
                conn.execute("UPDATE product SET stock_qty = stock_qty - ? WHERE id=?", (qty, pid))
            conn.commit()
            logger.info(f'Order created: #{oid} with total NPR {total:.2f}')
            flash(f'Order #{oid} placed! Total: NPR {total:.2f}', 'success')
            return redirect(url_for('orders'))
        conn.close()
        return render_template('order_form.html', customers=customers, products=products)
    except ValueError:
        flash('Invalid customer or product selection.', 'danger')
        return redirect(url_for('orders'))
    except Exception as e:
        logger.error(f'Error adding order: {e}')
        flash('Error creating order.', 'danger')
        return redirect(url_for('orders'))

@app.route('/orders/<int:oid>')
@requires_permission('orders')
def order_detail(oid):
    try:
        conn = get_db()
        order = conn.execute('''SELECT o.*, c.name as customer_name, c.email, c.phone
                                FROM \"order\" o JOIN customer c ON o.customer_id=c.id
                                WHERE o.id=?''', (oid,)).fetchone()
        if not order:
            flash('Order not found.', 'danger')
            return redirect(url_for('orders'))
        items = conn.execute('''SELECT oi.*, p.name as product_name, p.image_path
                                FROM order_item oi JOIN product p ON oi.product_id=p.id
                                WHERE oi.order_id=?''', (oid,)).fetchall()
        conn.close()
        return render_template('order_detail.html', order=order, items=items)
    except Exception as e:
        logger.error(f'Error loading order detail: {e}')
        flash('Error loading order.', 'danger')
        return redirect(url_for('orders'))

@app.route('/orders/<int:oid>/status', methods=['POST'])
@requires_permission('orders')
def update_order_status(oid):
    try:
        status = request.form.get('status', 'pending')
        if status not in ['pending', 'processing', 'completed', 'cancelled']:
            flash('Invalid order status.', 'danger')
            return redirect(url_for('order_detail', oid=oid))
        
        conn = get_db()
        conn.execute('UPDATE \"order\" SET status=? WHERE id=?', (status, oid))
        conn.commit()
        conn.close()
        logger.info(f'Order #{oid} status updated to: {status}')
        flash('Order status updated.', 'success')
    except Exception as e:
        logger.error(f'Error updating order status: {e}')
        flash('Error updating order status.', 'danger')
    return redirect(url_for('order_detail', oid=oid))

@app.route('/orders/delete/<int:oid>', methods=['POST'])
@requires_permission('orders')
def delete_order(oid):
    try:
        conn = get_db()
        conn.execute("DELETE FROM order_item WHERE order_id=?", (oid,))
        conn.execute('DELETE FROM \"order\" WHERE id=?', (oid,))
        conn.commit()
        conn.close()
        logger.info(f'Order deleted: #{oid}')
        flash('Order deleted.', 'danger')
    except Exception as e:
        logger.error(f'Error deleting order: {e}')
        flash('Error deleting order.', 'danger')
    return redirect(url_for('orders'))

# ── API ────────────────────────────────────────────────────────────────────────

@app.route('/api/product/<int:pid>')
@login_required
def api_product(pid):
    try:
        conn = get_db()
        p = conn.execute("SELECT id,name,price,stock_qty FROM product WHERE id=?", (pid,)).fetchone()
        conn.close()
        if p:
            return jsonify(dict(p))
        return jsonify({}), 404
    except Exception as e:
        logger.error(f'API error: {e}')
        return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(404)
def not_found(e):
    logger.warning(f'404 error: {request.path}')
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f'500 error: {str(e)}')
    return render_template('500.html'), 500

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    app.run(debug=True)
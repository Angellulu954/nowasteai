import os
import sqlite3
from datetime import datetime
from passlib.hash import pbkdf2_sha256
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, jsonify

from utils.recipe_engine import suggest_recipes, normalize_ingredient_list

DATABASE = os.path.join(os.path.dirname(__file__), 'database.db')
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-me')

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['DATABASE'] = DATABASE

# ------------- DB Helpers -------------
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS pantry_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        added_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    );
    CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        recipe_name TEXT NOT NULL,
        saved_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    );
    CREATE TABLE IF NOT EXISTS searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        ingredients TEXT NOT NULL,
        results_count INTEGER NOT NULL,
        searched_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    );
    CREATE TABLE IF NOT EXISTS cooked_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        recipe_name TEXT NOT NULL,
        grams_saved INTEGER NOT NULL,
        cooked_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    );
    ''')
    db.commit()

@app.before_request
def ensure_db():
    init_db()

# ------------- Auth -------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        if not username or not password:
            flash('Username and password are required.', 'error')
            return redirect(url_for('register'))
        db = get_db()
        try:
            db.execute('INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)', 
                       (username, pbkdf2_sha256.hash(password), datetime.utcnow().isoformat()))
            db.commit()
            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists. Choose another.', 'error')
            return redirect(url_for('register'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if row and pbkdf2_sha256.verify(password, row['password_hash']):
            session['user_id'] = row['id']
            session['username'] = row['username']
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('index'))

def current_user_id():
    return session.get('user_id')

# ------------- Pages -------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if not current_user_id():
        return redirect(url_for('login'))
    db = get_db()
    pantry = db.execute('SELECT * FROM pantry_items WHERE user_id = ? ORDER BY added_at DESC', (current_user_id(),)).fetchall()
    favs = db.execute('SELECT * FROM favorites WHERE user_id = ? ORDER BY saved_at DESC LIMIT 10', (current_user_id(),)).fetchall()
    return render_template('dashboard.html', pantry=pantry, favorites=favs)

# Pantry management
@app.route('/pantry/add', methods=['POST'])
def pantry_add():
    if not current_user_id():
        return redirect(url_for('login'))
    name = request.form.get('item', '').strip()
    if name:
        db = get_db()
        db.execute('INSERT INTO pantry_items (user_id, name, added_at) VALUES (?, ?, ?)', 
                   (current_user_id(), name.lower(), datetime.utcnow().isoformat()))
        db.commit()
        flash(f'Added "{name}" to pantry.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/pantry/remove/<int:item_id>', methods=['POST'])
def pantry_remove(item_id):
    if not current_user_id():
        return redirect(url_for('login'))
    db = get_db()
    db.execute('DELETE FROM pantry_items WHERE id = ? AND user_id = ?', (item_id, current_user_id()))
    db.commit()
    flash('Removed item.', 'info')
    return redirect(url_for('dashboard'))

# ------------- Recipe Suggestion -------------
@app.route('/suggest', methods=['POST'])
def suggest():
    # From index quick form (no login required)
    ingredients_text = request.form.get('ingredients', '')
    user_ing = normalize_ingredient_list(ingredients_text)
    recs = suggest_recipes(user_ing)
    db = get_db()
    db.execute('INSERT INTO searches (user_id, ingredients, results_count, searched_at) VALUES (?, ?, ?, ?)', 
               (current_user_id(), ','.join(sorted(user_ing)), len(recs), datetime.utcnow().isoformat()))
    db.commit()
    return render_template('results.html', recipes=recs, ingredients=user_ing, show_save=bool(current_user_id()))

@app.route('/suggest_from_pantry', methods=['POST'])
def suggest_from_pantry():
    if not current_user_id():
        return redirect(url_for('login'))
    db = get_db()
    rows = db.execute('SELECT name FROM pantry_items WHERE user_id = ?', (current_user_id(),)).fetchall()
    user_ing = {r['name'] for r in rows}
    recs = suggest_recipes(user_ing)
    return render_template('results.html', recipes=recs, ingredients=user_ing, show_save=True)

@app.route('/favorite', methods=['POST'])
def favorite():
    if not current_user_id():
        return redirect(url_for('login'))
    recipe_name = request.form.get('recipe_name')
    if recipe_name:
        db = get_db()
        db.execute('INSERT INTO favorites (user_id, recipe_name, saved_at) VALUES (?, ?, ?)', 
                   (current_user_id(), recipe_name, datetime.utcnow().isoformat()))
        db.commit()
        flash(f'Saved "{recipe_name}" to favorites.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/favorites')
def favorites():
    if not current_user_id():
        return redirect(url_for('login'))
    db = get_db()
    favs = db.execute('SELECT * FROM favorites WHERE user_id = ? ORDER BY saved_at DESC', (current_user_id(),)).fetchall()
    return render_template('favorites.html', favorites=favs)

# Health/Nutrition quick API (for demo)
@app.route('/api/nutrition', methods=['POST'])
def api_nutrition():
    data = request.get_json(force=True)
    ingredients = normalize_ingredient_list(data.get('ingredients', ''))
    recs = suggest_recipes(ingredients)
    return jsonify(recs[:5])

@app.route('/cooked', methods=['POST'])
def cooked():
    if not current_user_id():
        return redirect(url_for('login'))
    recipe_name = request.form.get('recipe_name')
    # Simple heuristic: grams_saved = number of ingredients used * 120 (approx 120g per ingredient saved)
    grams_saved = int(request.form.get('grams_saved') or 0)
    if not grams_saved:
        # fallback heuristic based on recipe in data file
        try:
            import json, os
            data_path = os.path.join(os.path.dirname(__file__), 'data', 'recipes.json')
            with open(data_path, 'r', encoding='utf-8') as f:
                recipes = json.load(f)
            recipe = next((x for x in recipes if x.get('name') == recipe_name), None)
            if recipe:
                grams_saved = max(100, len(recipe.get('ingredients', [])) * 120)
            else:
                grams_saved = 250
        except Exception:
            grams_saved = 250
    db = get_db()
    db.execute('INSERT INTO cooked_logs (user_id, recipe_name, grams_saved, cooked_at) VALUES (?, ?, ?, ?)', 
               (current_user_id(), recipe_name, grams_saved, datetime.utcnow().isoformat()))
    db.commit()
    flash(f'Recorded cooking of "{recipe_name}" — estimated {grams_saved}g saved from waste.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/stats')
def stats():
    if not current_user_id():
        return redirect(url_for('login'))
    db = get_db()
    rows = db.execute('SELECT SUM(grams_saved) as total_saved, COUNT(*) as cooked_count FROM cooked_logs WHERE user_id = ?', (current_user_id(),)).fetchone()
    total = rows['total_saved'] or 0
    cooked_count = rows['cooked_count'] or 0
    return render_template('stats.html', total_saved=total, cooked_count=cooked_count)



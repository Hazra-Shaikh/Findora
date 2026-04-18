from flask import Flask, render_template, request, redirect, session, flash, send_from_directory
import sqlite3
import os
import uuid
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret123"

# DB
conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# home page
@app.route('/')
def home():
    if 'user_id' in session:
        search = request.args.get('search')

        if search:
            query = "SELECT * FROM items WHERE title LIKE ? ORDER BY id DESC"
            cursor.execute(query, ('%' + search + '%',))
        else:
            query = "SELECT * FROM items ORDER BY id DESC"
            cursor.execute(query)

        items = cursor.fetchall()
    else:
        items = []

    return render_template('index.html', items=items)

# sign-up page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        hashed_password = generate_password_hash(request.form['password'])
        cursor.execute(
            "INSERT INTO users (name,email,password) VALUES (?,?,?)",
            (request.form['name'], request.form['email'],hashed_password)
        )
        conn.commit()
        flash("Signup successful!", "success")
        return redirect('/login')
    return render_template('signup.html')

# login page
@app.route('/login', methods=['GET', 'POST'])
def login():   
    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']

        cursor.execute(
            "SELECT * FROM users WHERE email=?",
            (email,)
        )
        user = cursor.fetchone()

        # DEBUG (optional)
        print("USER:", user)

        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            session['role'] = user[4]

            flash("Login successful!", "success")
            return redirect('/')

        else:
            flash("Invalid credentials", "danger")

    return render_template('login.html')

# profile page
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect('/login')

    cursor.execute("SELECT * FROM users WHERE id=?", (session['user_id'],))
    user = cursor.fetchone()

    return render_template('profile.html', user=user)

# edit profile
@app.route('/edit_profile', methods=['GET','POST'])
def edit_profile():
    if request.method == 'POST':
        cursor.execute("""
        UPDATE users SET name=?, email=? WHERE id=?
        """, (request.form['name'], request.form['email'], session['user_id']))
        conn.commit()

        session['user_name'] = request.form['name']  # update navbar name
        flash("Profile updated!", "success")
        return redirect('/profile')

    cursor.execute("SELECT * FROM users WHERE id=?", (session['user_id'],))
    user = cursor.fetchone()

    return render_template('edit_profile.html', user=user)

# delete account
@app.route('/delete_account')
def delete_account():
    cursor.execute("DELETE FROM users WHERE id=?", (session['user_id'],))
    conn.commit()

    session.clear()
    flash("Account deleted", "danger")
    return redirect('/')

@app.context_processor
def inject_user():
    user_id = session.get('user_id')

    if user_id:
        cursor.execute("SELECT name FROM users WHERE id=?", (user_id,))
        user = cursor.fetchone()

        if user:
            return dict(current_user=user[0])

    return dict(current_user=None)
    

# logout 
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect('/')

# post item

@app.route('/post', methods=['GET', 'POST'])
def post_item():
    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':

        # =========================
        # 1. HANDLE MULTIPLE IMAGES
        # =========================
        files = request.files.getlist('images')
        saved_files = []

        for file in files:
            if file and file.filename != "":
                # Create unique filename
                filename = str(uuid.uuid4()) + "_" + secure_filename(file.filename)

                # Save file
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)

                # Store filename
                saved_files.append(filename)

        # First image = main image (for card)
        main_image = saved_files[0] if saved_files else ""

        # =========================
        # 2. LOCATION LOGIC
        # =========================
        place = request.form.get('place')
        hostel_type = request.form.get('hostel_type')
        lab_block = request.form.get('lab_block')

        extra_info = ""

        if place == "Hostel":
            extra_info = hostel_type
        elif place == "Lab":
            extra_info = lab_block

        # =========================
        # 3. INSERT INTO ITEMS TABLE
        # =========================
        cursor.execute("""
        INSERT INTO items 
        (title, description, category, location, image, type, user_id, contact, place, extra_info)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            request.form['title'],
            request.form['description'],
            request.form['category'],
            request.form['location'],
            main_image,
            request.form['type'],
            session['user_id'],
            request.form['contact'],
            place,
            extra_info
        ))

        # Get inserted item ID
        item_id = cursor.lastrowid

        # =========================
        # 4. INSERT ALL IMAGES INTO item_images
        # =========================
        for fname in saved_files:
            cursor.execute("""
            INSERT INTO item_images (item_id, image_path)
            VALUES (?, ?)
            """, (item_id, fname))

        conn.commit()

        flash("Item posted successfully!", "success")
        return redirect('/')

    return render_template('post_item.html')


# for returned
@app.route('/mark_returned/<int:item_id>')
def mark_returned(item_id):
    cursor.execute("UPDATE items SET is_returned=TRUE WHERE id=?", (item_id,))
    conn.commit()

    flash("Item marked as returned!", "success")
    return redirect('/dashboard')

# for img upload route
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    # app.config['UPLOAD_FOLDER'] = 'uploads'
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# item details
@app.route('/item/<int:item_id>')
def item_detail(item_id):

    # GET ITEM
    cursor.execute("SELECT * FROM items WHERE id=?", (item_id,))
    item = cursor.fetchone()

    if not item:
        return "Item not found"

    # GET ALL IMAGES
    cursor.execute("SELECT * FROM item_images WHERE item_id=?", (item_id,))
    images = cursor.fetchall()

    user_id = session.get('user_id')
    item_owner = (user_id == item[7])

    # CHECK CLAIM ACCEPTED
    claim_accepted = False
    if user_id:
        cursor.execute("""
        SELECT * FROM claims 
        WHERE item_id=? AND user_id=? AND status='accepted'
        """, (item_id, user_id))
        if cursor.fetchone():
            claim_accepted = True

    return render_template(
        'item_detail.html',
        item=item,
        images=images,
        item_owner=item_owner,
        claim_accepted=claim_accepted
    )

# claim button
@app.route('/claim/<int:item_id>', methods=['POST'])
def claim_item(item_id):
    message = request.form['message']

    cursor.execute("""
        INSERT INTO claims (item_id, user_id, message, status)
        VALUES (?, ?, ?, 'pending')
    """, (item_id, session['user_id'], message))

    conn.commit()

    flash("Claim request sent!", "success")
    return redirect(f'/item/{item_id}')

# Admin route
@app.route('/admin')
def admin():

    if session.get('role') != 'admin':
        return "Access Denied"

    cursor.execute("""
    SELECT items.*, users.name 
    FROM items
    JOIN users ON items.user_id = users.id
    """)
    items = cursor.fetchall()

    cursor.execute("""
    SELECT claims.*, users.name, items.title, items.is_returned
    FROM claims
    JOIN users ON claims.user_id = users.id
    JOIN items ON claims.item_id = items.id
    """)
    claims = cursor.fetchall()

    return render_template('admin.html', items=items, claims=claims)

# dashboard
@app.route('/dashboard')
def dashboard():
    user_id = session['user_id']

    cursor.execute("SELECT * FROM items WHERE user_id=?", (user_id,))
    my_items = cursor.fetchall()

    cursor.execute("""
    SELECT claims.id, items.title, users.name, claims.status, claims.message
    FROM claims
    JOIN items ON claims.item_id = items.id
    JOIN users ON claims.user_id = users.id
    WHERE items.user_id = ?
    """, (user_id,))
    claims = cursor.fetchall()

    return render_template('dashboard.html', my_items=my_items, claims=claims)

# update claim
@app.route('/update_claim/<int:claim_id>/<status>')
def update_claim(claim_id, status):

    cursor.execute("UPDATE claims SET status=? WHERE id=?", (status, claim_id))
    conn.commit()

    flash("Claim updated!", "info")
    return redirect('/dashboard')

# delete item
@app.route('/delete_item/<int:item_id>')
def delete_item(item_id):
    cursor.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()
    flash("Deleted!", "danger")
    return redirect('/dashboard')

cursor.execute("DELETE FROM items WHERE id = 1;")
conn.commit()


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
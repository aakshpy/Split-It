from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import db_manager as db

app = Flask(__name__)
app.secret_key = "fd27835ea6f4d916997005820e78453a"

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if 'register_check' in request.form:
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            if db.create_user(username, email, password):
                flash("Account created! Please log in.", "success")
            else:
                flash("Email already exists!", "error")
        else:
            email = request.form['email']
            password = request.form['password']
            user = db.check_login(email, password)
            if user:
                session['user_id'] = user['user_id']
                session['username'] = user['username']
                return redirect(url_for('dashboard'))
            else:
                flash("Invalid Email or Password", "error")
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    groups = db.get_user_groups(user_id)
    return render_template('dashboard.html', username=session['username'], groups=groups)

@app.route('/create_group', methods=['POST'])
def create_group():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    group_name = request.form['group_name']
    if group_name:
        db.create_group(session['user_id'], group_name)
        flash(f"Group '{group_name}' created!", "success")
    else:
        flash("Group name cannot be empty", "error")
    return redirect(url_for('dashboard'))

@app.route('/group/<int:group_id>')
def group_details(group_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM ExpenseGroups WHERE group_id = %s", (group_id,))
    group = cursor.fetchone()
    cursor.close()
    conn.close()

    if not group:
        return "Group not found", 404

    members = db.get_group_members(group_id)
    expenses = db.get_expenses(group_id)
    balances = db.get_balances(group_id)
    
    return render_template('group_details.html', group=group, members=members, expenses=expenses, balances=balances)

@app.route('/add_member/<int:group_id>', methods=['POST'])
def add_member_route(group_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    email = request.form['email']
    result = db.add_member(group_id, email)
    if result == "Success":
        flash("Member added successfully!", "success")
    else:
        flash(result, "error")
    return redirect(url_for('group_details', group_id=group_id))

@app.route('/add_expense/<int:group_id>', methods=['POST'])
def add_expense_route(group_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    amount = float(request.form['amount'])
    desc = request.form['description']
    payer_id = request.form['payer_id']
    if db.add_expense(group_id, payer_id, amount, desc):
        flash("Expense added!", "success")
    else:
        flash("Failed to add expense.", "error")
    return redirect(url_for('group_details', group_id=group_id))

@app.route('/settle_up/<int:group_id>', methods=['POST'])
def settle_up_route(group_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    payer_id = request.form['payer_id']
    receiver_id = request.form['receiver_id']
    amount = float(request.form['amount'])
    if payer_id == receiver_id:
        flash("You cannot settle up with yourself!", "error")
        return redirect(url_for('group_details', group_id=group_id))
    if db.settle_up(group_id, payer_id, receiver_id, amount):
        flash("Settlement recorded successfully!", "success")
    else:
        flash("Failed to record settlement.", "error")
    return redirect(url_for('group_details', group_id=group_id))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# NEW API ROUTE FOR DRILL DOWN
@app.route('/api/breakdown/<int:group_id>/<int:user_id>')
def get_breakdown(group_id, user_id):
    if 'user_id' not in session: 
        return jsonify({'error': 'Unauthorized'}), 401
    data = db.get_user_debt_breakdown(group_id, user_id)
    return jsonify(data)
# 6. API: Get Filtered Activity Log
@app.route('/api/activity/<int:group_id>')
def get_activity_log(group_id):
    if 'user_id' not in session: 
        return jsonify({'error': 'Unauthorized'}), 401

    # Get filters from URL parameters (e.g., ?search=john&time=24h)
    search = request.args.get('search')
    time_filter = request.args.get('time')

    data = db.get_filtered_expenses(group_id, search, time_filter)
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
import mysql.connector
import hashlib

# 1. Database Connection Function
def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Legion15ACH6H", 
        database="split_it_db"
    )

# 2. Security: Hash Password
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# 3. Register User Function
def create_user(username, email, password):
    conn = get_connection()
    cursor = conn.cursor()
    hashed_pw = hash_password(password)
    try:
        query = "INSERT INTO Users (username, email, password) VALUES (%s, %s, %s)"
        cursor.execute(query, (username, email, hashed_pw))
        conn.commit()
        return True
    except mysql.connector.Error as err:
        return False
    finally:
        cursor.close()
        conn.close()

# 4. Login Function
def check_login(email, password):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    hashed_pw = hash_password(password)
    query = "SELECT user_id, username FROM Users WHERE email = %s AND password = %s"
    cursor.execute(query, (email, hashed_pw))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

# 5. Create a Group
def create_group(user_id, group_name):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        query1 = "INSERT INTO ExpenseGroups (group_name, created_by) VALUES (%s, %s)"
        cursor.execute(query1, (group_name, user_id))
        group_id = cursor.lastrowid
        query2 = "INSERT INTO GroupMembers (group_id, user_id) VALUES (%s, %s)"
        cursor.execute(query2, (group_id, user_id))
        conn.commit()
        return True
    except mysql.connector.Error as err:
        conn.rollback() 
        return False
    finally:
        cursor.close()
        conn.close()

# 6. Fetch Groups for a User
def get_user_groups(user_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
    SELECT g.group_id, g.group_name, g.created_at 
    FROM ExpenseGroups g
    JOIN GroupMembers m ON g.group_id = m.group_id
    WHERE m.user_id = %s
    ORDER BY g.created_at DESC
    """
    cursor.execute(query, (user_id,))
    groups = cursor.fetchall()
    cursor.close()
    conn.close()
    return groups

# 7. Add a Member
def add_member(group_id, user_email):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id FROM Users WHERE email = %s", (user_email,))
        result = cursor.fetchone()
        if not result:
            return "User not found"
        new_member_id = result[0]
        query = "INSERT INTO GroupMembers (group_id, user_id) VALUES (%s, %s)"
        cursor.execute(query, (group_id, new_member_id))
        conn.commit()
        return "Success"
    except mysql.connector.Error as err:
        if err.errno == 1062: 
            return "User is already in this group"
        return str(err)
    finally:
        cursor.close()
        conn.close()

# 8. Get All Members
def get_group_members(group_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
    SELECT u.user_id, u.username, u.email 
    FROM Users u
    JOIN GroupMembers m ON u.user_id = m.user_id
    WHERE m.group_id = %s
    """
    cursor.execute(query, (group_id,))
    members = cursor.fetchall()
    cursor.close()
    conn.close()
    return members

# 9. Create Expense
def add_expense(group_id, payer_id, amount, description):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        query_exp = "INSERT INTO Expenses (group_id, payer_id, amount, description) VALUES (%s, %s, %s, %s)"
        cursor.execute(query_exp, (group_id, payer_id, amount, description))
        expense_id = cursor.lastrowid
        
        cursor.execute("SELECT user_id FROM GroupMembers WHERE group_id = %s", (group_id,))
        members = cursor.fetchall() 
        
        if not members:
            raise Exception("No members in group!")

        num_members = len(members)
        split_amount = amount / num_members
        
        query_split = "INSERT INTO ExpenseSplits (expense_id, user_id, amount_owed) VALUES (%s, %s, %s)"
        
        for member in members:
            m_id = member[0]
            cursor.execute(query_split, (expense_id, m_id, split_amount))
            
        conn.commit()
        return True
    except mysql.connector.Error as err:
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# 10. Get Expenses
def get_expenses(group_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
    SELECT e.expense_id, e.amount, e.description, e.expense_date, u.username as payer_name
    FROM Expenses e
    JOIN Users u ON e.payer_id = u.user_id
    WHERE e.group_id = %s
    ORDER BY e.expense_date DESC
    """
    cursor.execute(query, (group_id,))
    expenses = cursor.fetchall()
    cursor.close()
    conn.close()
    return expenses

# 11. Calculate Balances (UPDATED)
def get_balances(group_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    balances = []
    
    cursor.execute("""
        SELECT u.user_id, u.username 
        FROM Users u
        JOIN GroupMembers m ON u.user_id = m.user_id
        WHERE m.group_id = %s
    """, (group_id,))
    members = cursor.fetchall()
    
    for member in members:
        u_id = member['user_id']
        
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total_paid 
            FROM Expenses 
            WHERE group_id = %s AND payer_id = %s
        """, (group_id, u_id))
        paid = cursor.fetchone()['total_paid']
        
        cursor.execute("""
            SELECT COALESCE(SUM(s.amount_owed), 0) as total_owed
            FROM ExpenseSplits s
            JOIN Expenses e ON s.expense_id = e.expense_id
            WHERE e.group_id = %s AND s.user_id = %s
        """, (group_id, u_id))
        owed = cursor.fetchone()['total_owed']
        
        net_balance = paid - owed
        
        balances.append({
            "user_id": u_id,      # <--- ADDED THIS!
            "user": member['username'],
            "net": net_balance
        })
        
    cursor.close()
    conn.close()
    return balances

# 12. Settle Debt
def settle_up(group_id, payer_id, receiver_id, amount):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        desc = "Settlement Payment"
        query_exp = "INSERT INTO Expenses (group_id, payer_id, amount, description) VALUES (%s, %s, %s, %s)"
        cursor.execute(query_exp, (group_id, payer_id, amount, desc))
        expense_id = cursor.lastrowid
        
        query_split = "INSERT INTO ExpenseSplits (expense_id, user_id, amount_owed) VALUES (%s, %s, %s)"
        cursor.execute(query_split, (expense_id, receiver_id, amount))
            
        conn.commit()
        return True
    except mysql.connector.Error as err:
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# 13. NEW: Get Breakdown for Drill-Down Feature
def get_user_debt_breakdown(group_id, user_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = """
    SELECT 
        e.description, 
        e.expense_date, 
        s.amount_owed, 
        u.username as payer_name
    FROM ExpenseSplits s
    JOIN Expenses e ON s.expense_id = e.expense_id
    JOIN Users u ON e.payer_id = u.user_id
    WHERE e.group_id = %s 
      AND s.user_id = %s 
      AND s.amount_owed > 0
    ORDER BY e.expense_date DESC
    """
    
    cursor.execute(query, (group_id, user_id))
    breakdown = cursor.fetchall()
    
    # --- FIX: Convert Decimals/Dates to JSON-friendly format ---
    for item in breakdown:
        # Convert Decimal(100.00) -> 100.0 (Float)
        if item['amount_owed']:
            item['amount_owed'] = float(item['amount_owed'])
            
        # Convert DateTime -> String
        if item['expense_date']:
            item['expense_date'] = str(item['expense_date'])
    # -----------------------------------------------------------
    
    cursor.close()
    conn.close()
    return breakdown
# 14. NEW: Get Filtered Activity Log
def get_filtered_expenses(group_id, search_query=None, time_filter=None):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Base Query
    query = """
    SELECT e.description, e.amount, e.expense_date, u.username as payer_name
    FROM Expenses e
    JOIN Users u ON e.payer_id = u.user_id
    WHERE e.group_id = %s
    """
    params = [group_id]

    # 1. Apply Search (Username OR Description)
    if search_query:
        query += " AND (u.username LIKE %s OR e.description LIKE %s)"
        search_term = f"%{search_query}%"
        params.extend([search_term, search_term])

    # 2. Apply Time Filter
    if time_filter == '24h':
        query += " AND e.expense_date >= NOW() - INTERVAL 1 DAY"
    elif time_filter == '7d':
        query += " AND e.expense_date >= NOW() - INTERVAL 7 DAY"
    elif time_filter == '30d':
        query += " AND e.expense_date >= NOW() - INTERVAL 30 DAY"

    query += " ORDER BY e.expense_date DESC"

    cursor.execute(query, tuple(params))
    expenses = cursor.fetchall()

    # Format Data for JSON
    for exp in expenses:
        if exp['amount']: exp['amount'] = float(exp['amount'])
        if exp['expense_date']: exp['expense_date'] = str(exp['expense_date'])

    cursor.close()
    conn.close()
    return expenses
import sqlite3
import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from src.agents.ai_agent import TutorAgent, AgentState
from langchain_core.messages import messages_to_dict, messages_from_dict
import datetime

# --- App and DB Setup ---
app = Flask(__name__)
app.secret_key = 'your_super_secret_key' # Change this in production

# Use an in-memory cache for agent instances to avoid re-initializing them on every request
agent_cache = {}

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the SQLite database with required tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')
    # Agent state table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_state (
            user_id INTEGER PRIMARY KEY,
            state_json TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    # Chat history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sender TEXT NOT NULL, -- 'user' or 'ai'
            message TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

# --- Helper Functions for State and History ---
def get_user_id(username):
    """Gets user ID from username."""
    conn = get_db_connection()
    user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return user['id'] if user else None

def save_agent_state(user_id, state):
    """Serializes and saves the agent's state to the database."""
    state_to_save = state.copy()
    state_to_save['messages'] = messages_to_dict(state['messages'])
    state_json = json.dumps(state_to_save)
    
    conn = get_db_connection()
    conn.execute(
        'INSERT OR REPLACE INTO agent_state (user_id, state_json) VALUES (?, ?)',
        (user_id, state_json)
    )
    conn.commit()
    conn.close()

def load_agent_state(user_id):
    """Loads and deserializes the agent's state from the database."""
    conn = get_db_connection()
    row = conn.execute('SELECT state_json FROM agent_state WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if row:
        state_json = row['state_json']
        loaded_state = json.loads(state_json)
        loaded_state['messages'] = messages_from_dict(loaded_state['messages'])
        return loaded_state
    return None

def save_chat_message(user_id, sender, message):
    """Saves a chat message to the history table."""
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO chat_history (user_id, sender, message) VALUES (?, ?, ?)',
        (user_id, sender, message)
    )
    conn.commit()
    conn.close()

def load_chat_history(user_id):
    """Loads all chat messages for a user."""
    conn = get_db_connection()
    messages = conn.execute(
        'SELECT sender, message, timestamp FROM chat_history WHERE user_id = ? ORDER BY timestamp ASC',
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(msg) for msg in messages]

def clear_user_session(user_id):
    """Clears agent state and chat history for a user."""
    conn = get_db_connection()
    conn.execute('DELETE FROM agent_state WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM chat_history WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# --- User Authentication Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['logged_in'] = True
            session['username'] = user['username']
            return redirect(url_for('product'))
        else:
            return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        hashed_password = generate_password_hash(password)
        
        try:
            conn = get_db_connection()
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
            conn.commit()
            conn.close()
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('product'))
        except sqlite3.IntegrityError:
            return render_template('signin.html', error='Username already exists')
    return render_template('signin.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- Main Application Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/product')
def product():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('product.html', username=session.get('username'))

# --- API Routes for Chat Logic ---
@app.route('/api/session', methods=['GET', 'DELETE'])
def manage_session():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    username = session.get('username')
    user_id = get_user_id(username)
    if not user_id:
        return jsonify({'error': 'User not found'}), 404

    if request.method == 'GET':
        history = load_chat_history(user_id)
        state = load_agent_state(user_id)
        return jsonify({
            'history': history,
            'state': state is not None
        })

    if request.method == 'DELETE':
        clear_user_session(user_id)
        return jsonify({'status': 'ok'})

@app.route('/api/chat', methods=['POST'])
def chat():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    user_input = data.get('message')
    username = session.get('username')
    user_id = get_user_id(username)

    if not user_id:
        return jsonify({'error': 'User not found'}), 404

    save_chat_message(user_id, 'user', user_input)

    # Get or create agent instance
    if username not in agent_cache:
        agent_cache[username] = TutorAgent()
    agent = agent_cache[username]
    
    current_state = load_agent_state(user_id)
    response_data = {}

    if current_state is None:
        print(f"---STARTING NEW SESSION FOR {username}---")
        initial_state = AgentState(
            topic=user_input, messages=[], user_response="", lesson_plan=[], current_lesson_index=0)
        final_state = agent.graph.invoke(initial_state)
    else:
        print(f"---CONTINUING SESSION FOR {username}---")
        current_state['user_response'] = user_input
        final_state = agent.graph.invoke(current_state)

    if final_state is None:
        response_data['message'] = "Congratulations! You have completed the lesson plan."
        response_data['is_finished'] = True
        clear_user_session(user_id) # Clean up the session from DB
    else:
        ai_message = final_state['messages'][-1].content
        response_data['lesson_plan'] = final_state.get('lesson_plan')
        response_data['message'] = ai_message
        save_agent_state(user_id, final_state)
        save_chat_message(user_id, 'ai', ai_message)
            
    return jsonify(response_data)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5001)
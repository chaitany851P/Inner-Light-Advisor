from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///user.db'
app.config['SECRET_KEY'] = 'your_secret_key'  # Set your secret key for Flask sessions
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Define the User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    dob = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Route to render index.html
@app.route('/')
def index():
    return render_template('index.html')

# Route to handle user login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Login Unsuccessful. Please check your email and password', 'danger')
    return render_template('login.html')

# Route to handle user signup
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        dob = request.form['dob']
        phone = request.form['phone']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        # Check if username or email already exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or Email already exists!', 'danger')
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password)
        new_user = User(name=name, dob=dob, phone=phone, username=username, email=email, password=hashed_password, role=role)
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)  # Login the user after successful signup
        return redirect(url_for('test'))  # Redirect to test.html after signup
    
    return render_template('test.html') 

@app.route('/vcoures.html')
def vcoures():
    return render_template('student/vcoures.html')

@app.route('/acoures.html')
def acoures():
    return render_template('student/acoures.html')

@app.route('/kcoures.html')
def kcoures():
    return render_template('student/kcoures.html')

@app.route('/submit', methods=['POST'])
def submit():
    data = request.form

    countA = sum(1 for k, v in data.items() if v == 'A')
    countB = sum(1 for k, v in data.items() if v == 'B')
    countC = sum(1 for k, v in data.items() if v == 'C')

    total = countA + countB + countC
    percentA = (countA / total) * 100
    percentB = (countB / total) * 100
    percentC = (countC / total) * 100

    # Determine the highest percentage
    if percentA > percentB and percentA > percentC:
        redirect_url = url_for('vcoures')
    elif percentB > percentA and percentB > percentC:
        redirect_url = url_for('acoures')
    else:
        redirect_url = url_for('kcoures')

    return render_template('results.html', percentA=percentA, percentB=percentB, percentC=percentC, redirect_url=redirect_url)

@app.route('/chatbot', methods=['POST'])
def chatbot():
    user_message = request.json['message']

    # Replace with your actual chatbot API endpoint
    api_endpoint = 'https://client.crisp.chat/l.js  '

    # Example: Sending user message to chatbot API
    response = requests.post(api_endpoint, json={'message': user_message})
    
    if response.status_code == 200:
        bot_response = response.json()['message']
    else:
        bot_response = "Sorry, I couldn't process your request at the moment."

    return jsonify({'message': bot_response})

@app.route('/tinfo')
def tinfo():
    return render_template('tinfo.html', user=user_data)

@app.route('/update_email', methods=['POST'])
def update_email():
    new_email = request.form['email']
    user_data['email'] = new_email
    return redirect(url_for('index'))

@app.route('/update_password', methods=['POST'])
def update_password():
    new_password = request.form['password']
    # Here you would add logic to update the password in your database
    return redirect(url_for('index'))

@app.route('/add_education', methods=['POST'])
def add_education():
    education_info = {
        'degree': request.form['degree'],
        'university': request.form['university'],
        'year': request.form['year']
    }
    user_data['education'].append(education_info)
    return redirect(url_for('tinfo'))

@app.route('/logout')
def logout():
    # Add your logout logic here
    return redirect(url_for('index'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        # Add logic to handle the password reset process
        if user_exists(email):  # Replace with actual user existence check
            send_password_reset_email(email)  # Replace with actual email sending logic
            message = "A password reset link has been sent to your email address."
            return render_template('forgot_password.html', message=message)
        else:
            error = "No account found with that email address."
            return render_template('forgot_password.html', error=error)
    return render_template('forgot_password.html')

def user_exists(email):
    # Implement your user existence check logic here
    return True  # Example return value 

# Route to render user dashboard (protected route)
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', username=current_user.username)



# Route to render test.html for signup form
@app.route('/test')
def test():

    return render_template('test.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create database tables based on the models
    app.run(debug=True)

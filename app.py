from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///user.db'
app.config['SECRET_KEY'] = 'your_secret_key'
db = SQLAlchemy(app)

# Flask-Login configuration
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Define the User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    phone_number = db.Column(db.String(15), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    learner_style = db.Column(db.String(50), nullable=False)
    __mapper_args__ = {'polymorphic_identity': 'user', 'polymorphic_on': 'role'}

class Student(User):
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    courses_enrolled = db.Column(db.PickleType, nullable=False)
    courses_completed = db.Column(db.PickleType, nullable=False)
    img = db.Column(db.String(200), nullable=True)
    __mapper_args__ = {'polymorphic_identity': 'student'}

class Teacher(User):
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    education = db.Column(db.PickleType, nullable=False)
    img = db.Column(db.String(200), nullable=True)
    courses = db.Column(db.PickleType, nullable=False)
    __mapper_args__ = {'polymorphic_identity': 'teacher'}

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(100), nullable=False)
    language = db.Column(db.String(50), nullable=False)
    payment = db.Column(db.String(50), nullable=False)
    mode_of_class = db.Column(db.String(50), nullable=False)
    learner_type = db.Column(db.PickleType, nullable=False)
    img = db.Column(db.String(200), nullable=True)


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
            if user.role == 'student':
                return redirect(url_for('student_dashboard'))
            elif user.role == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            else:
                flash('Unknown role!', 'danger')
                return redirect(url_for('index'))
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

        # Redirect logic based on role
        if role == 'student':
            return redirect(url_for('student_test'))
        elif role == 'teacher':
            return redirect(url_for('teacher_test'))
        else:
            flash('Unknown role!', 'danger')
            return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


# Route to render student test.html
@app.route('/student/test')
def student_test():
    if current_user.is_authenticated and current_user.role == 'student':
        return render_template('student/test.html')
    else:
        flash('Access Denied! You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))
    
@app.route('/student/dashboard')
def student_dashboard():
    if current_user.is_authenticated and current_user.role == 'student':
        return render_template('student/dashboard.html')
    else:
        flash('Access Denied! You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))

# Route to render teacher test.html
@app.route('/teacher/test')
def teacher_test():
    if current_user.is_authenticated and current_user.role == 'teacher':
        return render_template('teacher/test.html')
    else:
        flash('Access Denied! You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))
    
@app.route('/teacher/dashboard')
def teacher_dashboard():
    if current_user.is_authenticated and current_user.role == 'teacher':
        return render_template('teacher/dashboard.html')
    else:
        flash('Access Denied! You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))

# Route to render user dashboard (protected route)
@app.route('/dashboard')
def dashboard():
    if current_user.role == 'student':
        return render_template('student/dashboard.html')
    elif current_user.role == 'teacher':
        return render_template('teacher/dashboard.html')
    else:
        flash('Access Denied! You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))
    
@app.route('/profile')
def profile():
    if current_user.role == 'student':
        return render_template('student/info.html')
    elif current_user.role == 'teacher':
        return render_template('teacher/info.html')
    else:
        flash('Access Denied! You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))

@app.route('/coures')
def coures():
    if current_user.learning_style == 'Visual':
        return render_template('student/vcoures.html')
    elif current_user.learning_style == 'Auditory':
        return render_template('student/acoures.html')
    elif current_user.learning_style == 'Kinesthetic':
        return render_template('student/kcoures.html')
    else:
        flash('Access Denied! You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))
    

# Route to handle forgot password
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        # Add logic to handle the password reset process
        if user_exists(email):  # Replace with actual user existence check
            # send_password_reset_email(email)  # Replace with actual email sending logic
            message = "A password reset link has been sent to your email address."
            return render_template('forgot_password.html', message=message)
        else:
            error = "No account found with that email address."
            return render_template('forgot_password.html', error=error)
    return render_template('forgot_password.html')

def user_exists(email):
    # Implement your user existence check logic here
    return True  # Example return value 

# Route to handle form submission from learning style test
@app.route('/submit', methods=['POST'])
def submit():
    if request.method == 'POST':
     if current_user.role == 'student':
            form_data = request.form
            # Assuming you have form_data['q1'] to form_data['q10'] for answers
            answers = [form_data[f'q{i}'] for i in range(1, 11)]
            
            countA = answers.count('A')
            countB = answers.count('B')
            countC = answers.count('C')

            total = len(answers)
            percentA = (countA / total) * 100
            percentB = (countB / total) * 100
            percentC = (countC / total) * 100

            # Determine the learning style based on max percentage
            if percentA >= percentB and percentA >= percentC:
                learning_style = 'Visual'
            elif percentB >= percentA and percentB >= percentC:
                learning_style = 'Auditory'
            else:
                learning_style = 'Kinesthetic'

            # Update the current user's learning style if logged in
            if current_user.is_authenticated:
                current_user.learning_style = learning_style
                db.session.commit()

                # Redirect logic based on the learning style
                if learning_style == 'Visual':
                    return redirect(url_for('vcourse'))
                elif learning_style == 'Auditory':
                    return redirect(url_for('acourse'))
                elif learning_style == 'Kinesthetic':
                    return redirect(url_for('kcourse'))
                else:
                    flash('Unknown learning style!', 'danger')
                    return redirect(url_for('signup'))
     elif current_user.role == 'teacher':
            form_data = request.form
            # Assuming you have form_data['q1'] to form_data['q10'] for answers
            answers = [form_data[f'q{i}'] for i in range(1, 11)]
            
            countA = answers.count('A')
            countB = answers.count('B')
            countC = answers.count('C')

            total = len(answers)
            percentA = (countA / total) * 100
            percentB = (countB / total) * 100
            percentC = (countC / total) * 100

            # Determine the learning style based on max percentage
            if percentA >= percentB and percentA >= percentC:
                learning_style = 'Visual'
            elif percentB >= percentA and percentB >= percentC:
                learning_style = 'Auditory'
            else:
                learning_style = 'Kinesthetic'

            # Update the current user's learning style if logged in
            if current_user.is_authenticated:
                current_user.learning_style = learning_style
                db.session.commit()

                # Redirect logic based on the learning style
                if learning_style == 'Visual':
                    return redirect(url_for('teacher_dashboard'))
                elif learning_style == 'Auditory':
                    return redirect(url_for('teacher_dashboard'))
                elif learning_style == 'Kinesthetic':
                    return redirect(url_for('teacher_dashboard'))
                else:
                    flash('Unknown learning style!', 'danger')
                    return redirect(url_for('signup'))
    else:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))

# Route to render Visual course page
@app.route('/vcourse')
def vcourse():
    if current_user.is_authenticated and current_user.learning_style == 'Visual':
        return render_template('student/vcoures.html')
    else:
        flash('Access Denied! You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))

# Route to render Auditory course page
@app.route('/acourse')
def acourse():
    if current_user.is_authenticated and current_user.learning_style == 'Auditory':
        return render_template('student/acoures.html')
    else:
        flash('Access Denied! You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))

# Route to render Kinesthetic course page
@app.route('/kcourse')
def kcourse():
    if current_user.is_authenticated and current_user.learning_style == 'Kinesthetic':
        return render_template('student/kcoures.html')
    else:
        flash('Access Denied! You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists('user.db'):  # Check if the database file doesn't exist
            db.create_all()  # Create database tables based on the models
    app.run(debug=True)

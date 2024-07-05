from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_required, login_user, current_user, logout_user 
import os 
import openai
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.dialects.sqlite import JSON

# Initialize OpenAI API key
openai.api_key = 'sk-proj-ZmiMDvR0hy8qAULmD9J5T3BlbkFJTCdpG2tlo9MryTGRMl8L'

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
    dob = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    learning_style = db.Column(db.String(50), nullable=False)
    __mapper_args__ = {'polymorphic_identity': 'user', 'polymorphic_on': 'role'}

class Student(User):
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    courses_enrolled = db.Column(db.PickleType, nullable=False)
    courses_completed = db.Column(db.PickleType, nullable=False)
    img = db.Column(db.String(200), nullable=True)
    __mapper_args__ = {'polymorphic_identity': 'student'}

class Teacher(User):
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    education = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    img = db.Column(db.String(200), nullable=True)
    courses = db.Column(db.PickleType, nullable=False)
    __mapper_args__ = {'polymorphic_identity': 'teacher'}

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(1000), nullable=False)
    level = db.Column(db.String(50), nullable=False)
    domain = db.Column(db.String(100), nullable=False)
    language = db.Column(db.String(50), nullable=False)
    payment = db.Column(db.String(50), nullable=False)
    mode_of_class = db.Column(db.String(50), nullable=False)
    learner_type = db.Column(db.String(50), nullable=False)
    thumbnail_img = db.Column(db.String(200), nullable=True)
    temp_video = db.Column(db.String(200), nullable=True)
    chapter = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    # teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    # teacher = db.relationship('Teacher', backref=db.backref('courses', lazy=True))

    # def __repr__(self):
    #     return f"Course(name={self.name}, level={self.level}, domain={self.domain})"


    def __repr__(self):
        return f"Course(name={self.name}, level={self.level}, domain={self.domain})"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    return render_template('index.html')

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

        # Hash the password before storing it
        hashed_password = generate_password_hash(password)

        # Create a new user instance based on the selected role
        if role == 'student':
            new_user = Student(name=name, dob=dob, phone=phone, username=username, email=email, password=hashed_password, role=role, courses_enrolled=[], courses_completed=[], learning_style='Unassigned')
        elif role == 'teacher':
            new_user = Teacher(name=name, dob=dob, phone=phone, username=username, email=email, password=hashed_password, role=role, education=[], courses=[], learning_style='Unassigned')
        else:
            flash('Invalid role selected!', 'danger')
            return redirect(url_for('signup'))

        # Add the new user to the database
        db.session.add(new_user)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while signing up. Please try again.', 'danger')
            return redirect(url_for('signup'))

        # Log in the new user after successful registration
        login_user(new_user)

        # Redirect to a success page or another route
        return redirect(url_for('test'))

    # If the request method is GET, render the signup form
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            # Implement your password reset logic here
            flash('A password reset link has been sent to your email address.', 'success')
            return redirect(url_for('login'))
        else:
            flash('No account found with that email address.', 'danger')
    return render_template('forgot_password.html')

@app.route('/test')
def test():
    return render_template('test.html')

@app.route('/submit', methods=['POST'])
@login_required
def submit():
    if request.method == 'POST':
        form_data = request.form
        answers = [form_data[f'q{i}'] for i in range(1, 11)]

        countA = answers.count('A')
        countB = answers.count('B')
        countC = answers.count('C')

        total = len(answers)
        percentA = (countA / total) * 100
        percentB = (countB / total) * 100
        percentC = (countC / total) * 100

        if percentA >= percentB and percentA >= percentC:
            learning_style = 'Visual'
        elif percentB >= percentA and percentB >= percentC:
            learning_style = 'Auditory'
        else:
            learning_style = 'Kinesthetic'

        current_user.learning_style = learning_style
        try:
            db.session.commit()
            return redirect(url_for('courses'))
        except:
            flash('An error occurred while saving your learning style.', 'danger')
            return redirect(url_for('index'))

@app.route('/update_email', methods=['POST'])
@login_required
def update_email():
    new_email = request.form['email']
    current_user.email = new_email
    db.session.commit()
    flash('Email updated successfully!', 'success')
    return redirect(url_for('profile'))

@app.route('/update_password', methods=['POST'])
@login_required
def update_password():
    new_password = request.form['password']
    current_user.password = generate_password_hash(new_password)
    db.session.commit()
    flash('Password updated successfully!', 'success')
    return redirect(url_for('profile'))

@app.route('/coures_info')
def coures_info():
    return render_template('student/coures_info.html')

@app.route('/coures_video')
def coures_video():
    return render_template('student/coures_video.html')

@app.route('/courses')
@login_required
def courses():
        return render_template('courses.html')

@app.route('/add_education', methods=['POST'])
@login_required
def add_education():
    if current_user.role == 'teacher':
        degree = request.form['degree']
        university = request.form['university']
        year = request.form['year']
        
        # Retrieve the Teacher instance for the current user
        teacher = Teacher.query.get(current_user.id)

        # Create a new education dictionary
        new_education = {
            'degree': degree,
            'university': university,
            'year': year
        }

        # Append new education to the teacher's education list
        if teacher.education:
            teacher.education.append(new_education)
        else:
            teacher.education = [new_education]

        # Commit the changes to the database
        db.session.commit()
        
        flash('Education added successfully!', 'success')
    else:
        flash('Only teachers can add education details.', 'danger')
    
    return redirect(url_for('profile'))

# @app.route('/chatbot')
# def chatbot():
#     data = request.get_json()
#     user_message = data.get('message')

#     try:
#         response = openai.ChatCompletion.create(
#             model="gpt-3.5-turbo",
#             messages=[
#                 {"role": "user", "content": user_message}
#             ]
#         )
#         response_message = response.choices[0].message['content']
#         return jsonify(response=response_message)
#     except Exception as e:
#         return jsonify(error=str(e)), 500

@app.route('/chatbot')
def chatbot():
    
    return render_template('chatbot.html')
    
@app.route('/update_user_info', methods=['POST'])
@login_required
def update_user_info():
    current_user.name = request.form['name']
    current_user.dob = request.form['dob']
    db.session.commit()
    flash('User information updated successfully!', 'success')
    return redirect(url_for('profile'))

@app.route('/edit_education', methods=['POST'])
@login_required
def edit_education():
    if current_user.role == 'teacher':
        index = int(request.form['index'])
        degree = request.form['degree']
        university = request.form['university']
        year = request.form['year']
        
        current_user.education[index] = {
            'degree': degree,
            'university': university,
            'year': year
        }
        
        db.session.commit()
        flash('Education details updated successfully!', 'success')
    else:
        flash('Only teachers can edit education details.', 'danger')
    
    return redirect(url_for('profile'))


# @app.route('/chat', methods=['POST'])
# def chat():
#     data = request.get_json()
#     user_message = data.get('message')

#     response = openai.ChatCompletion.create(
#         model="gpt-3.5-turbo",
#         messages=[
#             {"role": "user", "content": user_message}
#         ]
#     )

#     response_message = response.choices[0].message['content']
#     return jsonify(response=response_message)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']

        # You can add code here to save the message to a database or send it via email

        flash('Your message has been sent successfully!', 'success')
        return redirect(url_for('contact'))
    return render_template('contect.html')

@app.route('/FAQs')
def FAQs():
    return render_template('faqs.html')

@app.route('/ac')
def ac():
    return render_template('temp.html')
@app.route('/add_course', methods=['GET', 'POST'])
@login_required
def add_course():
    if request.method == 'POST':
        # Handle form submission
        # Existing code...

        # Retrieve chapter data from the form
        chapter = []
        chapter_count = int(request.form.get('chapter_count', 0))
        for i in range(chapter_count):
            chapter_name = request.form.get(f'chapter_name_{i}')
            chapter_description = request.form.get(f'chapter_description_{i}')
            chapter_video = request.form.get(f'chapter_video_{i}')
            chapter_assignment_file = request.files.get(f'chapter_assignment_{i}')
            chapter_resource_link = request.form.get(f'chapter_resource_{i}')
            chapter_notes = request.form.get(f'chapter_notes_{i}')

            # Example of how to handle file uploads (adjust as needed)
            if chapter_assignment_file:
                filename = (chapter_assignment_file.filename)
                chapter_assignment_file.save(os.path.join(app.config['templates/teacher/img'], filename))
                chapter_assignment_filename = filename
            else:
                chapter_assignment_filename = None

            chapter.append({
                'name': chapter_name,
                'description': chapter_description,
                'video': chapter_video,
                'assignment_file': chapter_assignment_filename,
                'resource_link': chapter_resource_link,
                'notes': chapter_notes
            })

        new_course = Course(
            # Existing fields...
            chapter=chapter,
            teacher_id=current_user.id
        )

        db.session.add(new_course)
        db.session.commit()
        flash('Course added successfully!', 'success')
        return redirect(url_for('courses'))

    return render_template('temp.html')

if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists('user.db'):  # Check if the database file doesn't exist
            db.create_all()  # Create database tables based on the models
    app.run(debug=True)

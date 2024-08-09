from email.message import EmailMessage
from mailbox import Message
from multiprocessing import reduction
import shutil
import smtplib
import tempfile
import zipfile
from flask import Flask, abort, after_this_request, jsonify, render_template, request, redirect, send_from_directory, url_for, flash , send_file
# from flask_mail import Mail, Message
# from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_required, login_user, current_user, logout_user 
import os 
import json
from werkzeug.utils import secure_filename
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.types import JSON
import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///user.db'
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')  # Define upload folder
app.config['MAIL_USERNAME'] = 'innerlightadvisor@gmail.com'
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

db = SQLAlchemy(app)
# mail = Mail(app)

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
    courses_enrolled = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    courses_completed = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    img = db.Column(db.String(200), nullable=True)
    __mapper_args__ = {'polymorphic_identity': 'student'}

    enrolled_courses = db.relationship('Course', secondary='student_courses_enrolled')
    completed_courses = db.relationship('Course', secondary='student_courses_completed')

    def __init__(self, name, dob, phone, username, email, password, learning_style, img=None):
        super().__init__(name=name, dob=dob, phone=phone, username=username, email=email, password=password, role='student', learning_style=learning_style)
        self.img = img

student_courses_enrolled = db.Table(
    'student_courses_enrolled',
    db.Column('student_id', db.Integer, db.ForeignKey('student.id'), primary_key=True),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True)
)

student_courses_completed = db.Table(
    'student_courses_completed',
    db.Column('student_id', db.Integer, db.ForeignKey('student.id'), primary_key=True),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True)
)

class Teacher(User):
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    education = db.Column(MutableList.as_mutable(JSON), nullable=True, default=[])
    img = db.Column(db.String(200), nullable=True)
    courses = db.relationship('Course', backref='teacher', lazy=True)
    tasks = db.relationship('Task', backref='assigned_teacher', lazy=True)
    signature = db.Column(db.String(255), nullable=True) 
    upi_qr = db.Column(db.String(500), nullable=True)
    __mapper_args__ = {'polymorphic_identity': 'teacher'}

    def __init__(self, name, dob, phone, username, email, password, learning_style, education=None, img=None, signature=None):
        super().__init__(name=name, dob=dob, phone=phone, username=username, email=email, password=password, role='teacher', learning_style=learning_style)
        self.education = education if education is not None else []
        self.img = img
        self.signature = signature


tm = datetime.date.today() + datetime.timedelta(days=1)
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pending')  # Example status field
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    due_date = db.Column(db.String(20), default=[tm])

    def __repr__(self):
        return f"<Task(title='{self.title}', status='{self.status}')>"


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True,unique=True,autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(1000), nullable=False)
    level = db.Column(db.String(50), nullable=False)
    domain = db.Column(db.String(100), nullable=False)
    language = db.Column(db.String(50), nullable=False)
    payment = db.Column(db.String(50000), nullable=False)
    fees = db.Column(db.String(50), nullable=True)
    mode_of_class = db.Column(db.String(50), nullable=False)
    learner_type = db.Column(db.String(50), nullable=False)
    thumbnail_img = db.Column(db.String(200), nullable=True)
    temp_video = db.Column(db.String(200), nullable=True)
    chapters = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    quizzes = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    __mapper_args__ = {'polymorphic_identity': 'course'}

 

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/base')
def base():
    return render_template('base.html')

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
            new_user = Student(name=name, dob=dob, phone=phone, username=username, email=email, password=hashed_password, learning_style='Unassigned')
        elif role == 'teacher':
            new_user = Teacher(name=name, dob=dob, phone=phone, username=username, email=email, password=hashed_password, learning_style='Unassigned')
        else:
            flash('Invalid role selected!', 'danger')
            return redirect(url_for('signup'))

        # Add the new user to the database
        db.session.add(new_user)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # Log the full error for debugging
            print("Error during user signup:", str(e))
            # Flash a user-friendly error message
            flash('An error occurred while signing up. Please try again. Error: {}'.format(str(e)), 'danger')
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

now = datetime.datetime.now()

current_date = now.strftime('%Y-%m-%d')
current_time = now.strftime('%H:%M')
@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'student':
        enrolled_courses = current_user.enrolled_courses  # Assuming Student model has enrolled_courses relationship
        completed_courses = current_user.completed_courses  # Query completed courses for the current_user
        live_classes = []
        for course in enrolled_courses:
            if course.mode_of_class == 'Live':
                for index, chapter in enumerate(course.chapters):
                    if chapter.get('date') >= current_date:
                        if chapter.get('time') >= current_time:
                            live_classes.append({
                                "title": chapter.get('title'),
                                "date": chapter.get('date'),
                                "time": chapter.get('time'),
                                "course_id": course.id,
                                "chapter_index": index  # Include chapter index
                            })
        return render_template('dashboard.html', enrolled_courses=enrolled_courses, completed_courses=completed_courses, live_classes=live_classes)

    elif current_user.role == 'teacher':
        courses = current_user.courses  # Query courses created by the current_user
        upcoming_tasks = Task.query.filter_by(teacher_id=current_user.id).all()  # Query tasks assigned to the current_user
        live_classes = []
        for course in courses:
            if course.teacher_id == current_user.id:
                if course.mode_of_class == 'Live':
                    for index, chapter in enumerate(course.chapters):
                        if chapter.get('date') >= current_date:
                            if chapter.get('time') >= current_time:
                                live_classes.append({
                                    "title": chapter.get('title'),
                                    "date": chapter.get('date'),
                                    "time": chapter.get('time'),
                                    "course_id": course.id,
                                    "chapter_index": index  # Include chapter index
                                })
        return render_template('dashboard.html', upcoming_tasks=upcoming_tasks, live_classes=live_classes)
    else:
        return redirect(url_for('login'))
    
@app.route('/add_task', methods=['GET', 'POST'])
def add_task():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        teacher_id = current_user.id  # Assuming current_user is authenticated and has an id attribute
        due_date = request.form['due_date']

        new_task = Task(title=title, description=description, teacher_id=teacher_id, due_date=due_date)

        try:
            db.session.add(new_task)
            db.session.commit()
            return redirect(url_for('dashboard'))  # Redirect to dashboard or wherever appropriate
        except Exception as e:
            db.session.rollback()
            print(f"Error adding task: {e}")
            # Handle error, possibly redirect to an error page or show an error message

    return render_template('add_task.html')

@app.route('/edit_task/<int:task_id>', methods=['GET', 'POST'])
def edit_task(task_id):
    task = Task.query.get(task_id)
    

    if request.method == 'POST':
        task.title = request.form['title']
        task.description = request.form['description']
        task.status = request.form['status']
        task.due_date = request.form['due_date']
        # if satus == Completed then delete task
        if task.status == 'Completed':
            db.session.delete(task)
            db.session.commit()
            return redirect(url_for('dashboard'))  # Redirect to dashboard or wherever appropriate
        db.session.commit()
        return redirect(url_for('dashboard'))  # Redirect to dashboard or wherever appropriate

    return render_template('edit_task.html', task=task)

@app.route('/task/<int:task_id>/delete', methods=['GET', 'POST'])
@login_required  # Assuming you have a login_required decorator for authentication
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)

    if request.method == 'POST':
        try:
            db.session.delete(task)
            db.session.commit()
            flash('Task deleted successfully', 'success')
            return redirect(url_for('dashboard'))  # Redirect to dashboard or any other appropriate route
        except Exception as e:
            db.session.rollback()
            flash(f'Error deleting task: {str(e)}', 'error')
            return redirect(url_for('dashboard'))  # Redirect to dashboard with error message

    return render_template('delete_task.html', task=task)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        # Handle profile image upload
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename != '':
                # Handle existing image deletion
                old_profile_image = None
                if current_user.role == 'student':
                    student = Student.query.filter_by(username=current_user.username).first()
                    if student:
                        old_profile_image = student.img
                elif current_user.role == 'teacher':
                    teacher = Teacher.query.filter_by(username=current_user.username).first()
                    if teacher:
                        old_profile_image = teacher.img

                # Save new profile image
                filepath = save_profile_image(file, current_user.id)

                # Delete old profile image if it exists
                if old_profile_image and os.path.exists(os.path.join('static', old_profile_image)):
                    os.remove(os.path.join('static', old_profile_image))

                # Update database
                if current_user.role == 'student':
                    if student:
                        student.img = filepath
                        db.session.commit()
                elif current_user.role == 'teacher':
                    if teacher:
                        teacher.img = filepath
                        db.session.commit()

                flash('Profile image updated successfully', 'success')
                return redirect(url_for('profile'))

        # Handle signature image upload
        if 'signature_image' in request.files:
            file = request.files['signature_image']
            if file and file.filename != '':
                # Handle existing signature deletion
                old_signature_image = None
                if current_user.role == 'teacher':
                    teacher = Teacher.query.filter_by(username=current_user.username).first()
                    if teacher:
                        old_signature_image = teacher.signature

                # Save new signature image
                filepath = save_signature_image(file, current_user.id)

                # Delete old signature image if it exists
                if old_signature_image and os.path.exists(os.path.join('static', old_signature_image)):
                    os.remove(os.path.join('static', old_signature_image))

                # Update database
                if current_user.role == 'teacher':
                    if teacher:
                        teacher.signature = filepath
                        db.session.commit()

                flash('Signature updated successfully', 'success')
                return redirect(url_for('profile'))

        # Handle UPI QR image upload
        if 'upi_qr_image' in request.files:
            file = request.files['upi_qr_image']
            if file and file.filename != '':
                # Handle existing UPI QR image deletion
                old_upi_qr_image = None
                if current_user.role == 'teacher':
                    teacher = Teacher.query.filter_by(username=current_user.username).first()
                    if teacher:
                        old_upi_qr_image = teacher.upi_qr

                # Save new UPI QR image
                filepath = save_upi_qr_image(file, current_user.id)

                # Delete old UPI QR image if it exists
                if old_upi_qr_image and os.path.exists(os.path.join('static', old_upi_qr_image)):
                    os.remove(os.path.join('static', old_upi_qr_image))

                # Update database
                if current_user.role == 'teacher':
                    if teacher:
                        teacher.upi_qr = filepath
                        db.session.commit()

                flash('UPI QR code updated successfully', 'success')
                return redirect(url_for('profile'))

    # Fetch the user's profile image path
    if current_user.role == 'student':
        user = Student.query.filter_by(username=current_user.username).first()
        profile_image = user.img if user else None
    elif current_user.role == 'teacher':
        user = Teacher.query.filter_by(username=current_user.username).first()
        profile_image = user.img if user else None
    else:
        profile_image = None

    # Fetch signature for teacher
    if current_user.role == 'teacher':
        user = Teacher.query.filter_by(username=current_user.username).first()
        signature_image = user.signature if user else None
        upi_qr_image = user.upi_qr if user else None
    else:
        signature_image = None
        upi_qr_image = None

    return render_template('profile.html', img=profile_image, signature=signature_image, upi_qr=upi_qr_image)


def save_profile_image(file, user_id):
    upload_folder = 'static/uploads/Profile'
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

    filename = f'{user_id}_{secure_filename(file.filename)}'
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)
    
    return f'uploads/Profile/{filename}'

def save_signature_image(file, user_id):
    upload_folder = 'static/uploads/teacher'
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

    filename = f'{user_id}_{secure_filename(file.filename)}'
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)

    return f'uploads/teacher/{filename}'

def save_upi_qr_image(file, user_id):
    upload_folder = 'static/uploads/upi_qr'
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

    filename = f'{user_id}_{secure_filename(file.filename)}'
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)

    return f'uploads/upi_qr/{filename}'


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
@app.route('/join2')
def join2():
    return render_template('join.html')

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



@app.route('/update_password', methods=['POST'])
@login_required
def update_password():
    new_password = request.form['password']
    current_user.password = generate_password_hash(new_password)
    db.session.commit()
    flash('Password updated successfully!', 'success')
    return redirect(url_for('profile'))

@app.route('/course/<int:course_id>')
def course_detail(course_id):
    course = Course.query.get(course_id)
    # pass course if it's not in current_user.enrolled_courses
    if course in current_user.enrolled_courses or course in current_user.completed_courses:
        return render_template('coures_detail.html', course=course)
        
    
    return render_template('coures_detail.html', course=course)

@app.route('/coures_video')
def coures_video():
    return render_template('student/coures_video.html')

@app.route('/courses', methods=['GET', 'POST'])
def courses():
    courses_query = Course.query

    if request.method == 'POST':
        # Get form data with default to None
        language = request.form.get('language', None)
        payment = request.form.get('payment', None)
        domain = request.form.get('domain', None)
        level = request.form.get('level', None)
        mode_of_class = request.form.get('mode_of_class', None)

        # Apply filters if they are not empty
        if language:
            courses_query = courses_query.filter_by(language=language)
        if payment:
            courses_query = courses_query.filter_by(payment=payment)
        if domain:
            courses_query = courses_query.filter_by(domain=domain)
        if level:
            courses_query = courses_query.filter_by(level=level)
        if mode_of_class:
            courses_query = courses_query.filter_by(mode_of_class=mode_of_class)

    courses = courses_query.all()  # Retrieve filtered or all courses

    if current_user.role == 'student':
        # Filter out courses based on enrollment and completion
        available_courses = [
            course for course in courses
            if course not in current_user.enrolled_courses and
               course not in current_user.completed_courses and
               course.learner_type == current_user.learning_style
        ]
        return render_template('courses.html', courses=available_courses)
    
    elif current_user.role == 'teacher':
        # Filter courses created by the current teacher
        teacher_courses = [
            course for course in courses
            if course.teacher_id == current_user.id
        ]
        return render_template('courses.html', courses=teacher_courses)

    # Redirect to home if role is not recognized
    return redirect(url_for('home'))

@app.route('/quiz/<int:course_id>', methods=['POST'])
@login_required
def quiz(course_id):
    course = Course.query.get_or_404(course_id)
    if request.method == 'POST':
        course = Course.query.get_or_404(course_id)
        name = current_user.name
        email = current_user.email
        message = request.form['message']
        # cc_recipient = 'chaitanyathaker777@gmail.com'
        bcc_recipient = 'chaitanyathaker777@gmail.com', course.teacher.email
        # Basic form validation (optional)
        # User-friendly error message
        # new_feedback = Feedback(name=name, email=email, message=message)
        
        # if message is not null
        if message == '':
            return render_template('quiz.html', course=course)
           
        else:
                try:
                    msg = EmailMessage()
                    msg['From'] = 'innerlightadvisor@gmail.com'
                    msg['To'] = email
                    msg['Bcc'] = bcc_recipient
                    msg['Subject'] = 'Thank you for your feedback'
                    msg.set_content(f"Hi {name},\n\nThanks for your feedback!\nAbout {message}\nWe'll get back to you soon.\n\nBest,\nInner Light Advisor Team")
                    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                        smtp.login('innerlightadvisor@gmail.com', app.config['MAIL_PASSWORD'])
                        smtp.send_message(msg)
                        return render_template('quiz.html', course=course)
                except (ConnectionRefusedError, smtplib.SMTPException) as e:
                    print(f"Error sending email: {e}")
                    return 'There was a problem sending your email. Please try again later.'
    else:        
        return render_template('quiz.html', course=course)

# @app.route('/quiz/<int:course_id>')
# def feedback(course_id):
    
@app.route('/submit_quiz/<int:course_id>', methods=['POST'])
@login_required
def submit_quiz(course_id):
    course = Course.query.get_or_404(course_id)
    total_questions = len(course.quizzes)
    correct_answers = 0

    print("Submitting quiz for course:", course_id)  # Debug statement
    print("Form data received:", request.form)  # Debug statement

    for index, quiz in enumerate(course.quizzes):
        user_answer = request.form.get(f'question{index + 1}')
        correct_answer = quiz['correct_answer']
        print(f"Question {index + 1}: User answer: {user_answer}, Correct answer: {correct_answer}")  # Debug statement
        if user_answer and int(user_answer) == correct_answer:
            correct_answers += 1

    percentage_score = (correct_answers / total_questions) * 100
    passed = percentage_score >= 60

    print(f"Total Questions: {total_questions}, Correct Answers: {correct_answers}, Percentage Score: {percentage_score}, Passed: {passed}")  # Debug statement

    if passed:
        if course not in current_user.completed_courses:
            current_user.completed_courses.append(course)
            if course in current_user.enrolled_courses:
                current_user.enrolled_courses.remove(course)
            db.session.commit()
            return jsonify(success=True, message='Congratulations! You passed the quiz and completed the course.', passed=True, course_id=course.id)
        else:
            return jsonify(success=True, message='You already completed this course.', passed=True, course_id=course.id)
    else:
        return jsonify(success=True, message='Sorry, you did not pass the quiz. Please try again.', passed=False, course_id=course.id)

    



@app.route('/certificate/<int:course_id>')
@login_required
def certificate(course_id):
    course = Course.query.get_or_404(course_id)
    if course.id in current_user.enrolled_courses:
        flash('You have not completed this course yet.', 'danger')
        return redirect(url_for('view_chapter', course_id=course.id))
    
    # return redirect('profile')

    return render_template('certificate.html', course=course, user=current_user )
    # return render_template('certificate.html', course=course, user=current_user)






@app.route('/add_education', methods=['POST'])
@login_required
def add_education():
    degree = request.form.get('degree')
    university = request.form.get('university')
    year = request.form.get('year')

    # Assuming current_user is a Teacher model with education as a list
    current_user.education.append({
        'degree': degree,
        'university': university,
        'year': year
    })
    db.session.commit()
    flash('Education added successfully.', 'success')
    return redirect(url_for('profile'))  # Redirect to user info page

@app.route('/delete_education', methods=['POST'])
@login_required
def delete_education():
    try:
        index = int(request.form['index']) - 1
        user_id = int(request.form['user_id'])

        # Retrieve current user based on user_id
        current_user = Teacher.query.get(user_id)
        if not current_user:
            return "User not found", 404

        # Remove education details if index is valid
        if current_user.education and 0 <= index < len(current_user.education):
            current_user.education.pop(index)
            db.session.commit()
            return redirect(url_for('profile'))
        else:
            return "Invalid index or education details", 400

    except Exception as e:
        return f"Error: {str(e)}", 500
    

    

# @app.route('/chatbot')
# def chatbot():
    
    
    

@app.route('/chatbot')
def chatbot():
    
    return render_template('chatbot.html')
    


@app.route('/update_user_info', methods=['POST'])
@login_required
def update_user_info():
    current_user.name = request.form['name']
    current_user.dob = request.form['dob']
    current_user.email = request.form['email']
    db.session.commit()
    flash('User information updated successfully!', 'success')
    return redirect(url_for('profile'))


# @app.route('/chat', methods=['POST'])
# def chat():
#     if request.method == 'POST':
#         prompt = request.form['prompt']
#         response = client.chat.completions.create(
#             model="gpt-3.5-turbo",
#             messages=[
#                 {"role": "system", "content": "You are a poetic assistant, skilled in explaining complex programming concepts with creative flair."},
#                 {"role": "user", "content": prompt}
#             ]
#         )
#         return render_template('chatbot.html', prompt=prompt, response=response.choices[0].message.content)
#     else:
#         return render_template('chatbot.html')
#     # return render_template('')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']
        # cc_recipient = 'chaitanyathaker777@gmail.com'
        bcc_recipient = 'chaitanyathaker777@gmail.com'

        # Basic form validation (optional)
        if not name or not email or not message:
            return 'Please fill in all fields.'  # User-friendly error message

        try:
            msg = EmailMessage()
            msg['From'] = 'innerlightadvisor@gmail.com'
            msg['To'] = email
            msg['Bcc'] = bcc_recipient
            msg['Subject'] = 'Thank you for contacting Inner Light Advisor'
            msg.set_content(f"Hi {name},\n\nThanks for your message!\nAbout {message}\nWe'll get back to you soon.\n\nBest,\nInner Light Advisor Team")

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login('innerlightadvisor@gmail.com', app.config['MAIL_PASSWORD'])
                smtp.send_message(msg)
                return render_template('contect.html')
        except (ConnectionRefusedError, smtplib.SMTPException) as e:
            print(f"Error sending email: {e}")
            return 'There was a problem sending your email. Please try again later.'

    return render_template('contect.html')
# feedback form


@app.route('/FAQs')
def FAQs():
    return render_template('faqs.html')



@app.route('/add_course', methods=['GET', 'POST'])
@login_required
def add_course():
    if request.method == 'POST':
        if current_user.role != 'teacher':
            flash('Only teachers can add courses.', 'danger')
            return redirect(url_for('dashboard'))

        # Retrieve form fields
        name = request.form.get('name')
        description = request.form.get('description')
        level = request.form.get('level')
        domain = request.form.get('domain')
        language = request.form.get('language')
        payment = request.form.get('payment')
        mode_of_class = request.form.get('mode_of_class')
        learner_type = request.form.get('learner_type')
        fees = request.form.get('fees')

        # Save course details to the database first to get the course ID
        new_course = Course(
            name=name,
            description=description,
            level=level,
            domain=domain,
            language=language,
            payment=payment,
            mode_of_class=mode_of_class,
            learner_type=learner_type,
            fees=fees,
            teacher_id=current_user.id
        )

        db.session.add(new_course)
        db.session.commit()  # Commit to get the course ID

        course_id = new_course.id  # Now you have the course ID

        # Save uploaded files with new naming convention
        thumbnail_img = request.files.get('thumbnail_img')
        if thumbnail_img and thumbnail_img.filename != '':
            thumbnail_img_filename = f'{course_id}_thumbnail_{secure_filename(thumbnail_img.filename)}'
            thumbnail_img.save(os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnail', thumbnail_img_filename))
            new_course.thumbnail_img = thumbnail_img_filename
        else:
            thumbnail_img_filename = None

        temp_video = request.files.get('temp_video')
        if temp_video and temp_video.filename != '':
            temp_video_filename = f'{course_id}_sample_video_{secure_filename(temp_video.filename)}'
            temp_video.save(os.path.join(app.config['UPLOAD_FOLDER'], 'sample_video', temp_video_filename))
            new_course.temp_video = temp_video_filename
        else:
            temp_video_filename = None

        # Handle chapters
        chapters = []
        chapter_count = int(request.form.get('chapter_count', 0))
        for i in range(1, chapter_count + 1):
            chapter_title = request.form.get(f'chapter_{i}_title')
            chapter_description = request.form.get(f'chapter_{i}_description')
            chapter_assignment_file = request.files.get(f'chapter_{i}_assignment_file')
            chapter_resources_files = request.files.getlist(f'chapter_{i}_resources')
            chapter_note = request.form.get(f'chapter_{i}_note')
            chapter_course_file = request.files.get(f'chapter_{i}_course_file')
            chapter_resource_link = request.form.get(f'chapter_{i}_resource_link')
            chapter_meeting_link = request.form.get(f'chapter_{i}_meeting_link')
            chapter_date = request.form.get(f'chapter_{i}_date')
            chapter_time = request.form.get(f'chapter_{i}_time')
            chapter_course_link = request.form.get(f'chapter_{i}_course_link')

            # Initialize resources_filenames if needed
            assignment_filename = None
            if chapter_assignment_file and chapter_assignment_file.filename != '':
                assignment_filename = f'{course_id}_file-for_chapter-{i}_{secure_filename(chapter_assignment_file.filename)}'
                assignment_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Assignment', assignment_filename)
                chapter_assignment_file.save(assignment_path)

            # Save resources files if provided
            resources_filenames = []
            for file in chapter_resources_files:
                if file and file.filename != '':
                    filename = f'{course_id}_file-for_chapter-{i}_{secure_filename(file.filename)}'
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Resource', filename)
                    file.save(file_path)
                    resources_filenames.append(filename)

            # Save course file if provided
            course_filename = None
            if chapter_course_file and chapter_course_file.filename != '':
                course_filename = f'{course_id}_file-for_chapter-{i}_{secure_filename(chapter_course_file.filename)}'
                course_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Course', course_filename)
                chapter_course_file.save(course_path)

            chapters.append({
                'title': chapter_title,
                'description': chapter_description,
                'assignment_file': assignment_filename,
                'resources_files': resources_filenames,  # Use the list here
                'note': chapter_note,
                'course_file': course_filename,
                'course_link': chapter_course_link,
                'resource_link': chapter_resource_link,
                'meeting_link': chapter_meeting_link,
                'date': chapter_date,
                'time': chapter_time
            })

        # Handle quizzes (outside the chapter loop)
        try:
            quizzes = []
            quiz_count = int(request.form.get('quiz_count', 0))
            for i in range(1, quiz_count + 1):
                quiz_question = request.form.get(f'quiz_{i}_question')
                quiz_options = [
                    request.form.get(f'quiz_{i}_option_1'),
                    request.form.get(f'quiz_{i}_option_2'),
                    request.form.get(f'quiz_{i}_option_3'),
                    request.form.get(f'quiz_{i}_option_4')
                ]
                quiz_correct_answer = request.form.get(f'quiz_{i}_correct_answer')
                if quiz_correct_answer is not None:
                    quiz_correct_answer = int(quiz_correct_answer)
                else:
                    quiz_correct_answer = -1  # Assign a default value to handle missing correct answer

                quizzes.append({
                    'question': quiz_question,
                    'options': quiz_options,
                    'correct_answer': quiz_correct_answer
                })
        except Exception :
            pass
        # Update the course with chapter and quiz data
        new_course.chapters = chapters
        new_course.quizzes = quizzes  # Add quizzes to the course

        # Commit the updates
        db.session.commit()

        flash('Course added successfully!', 'success')
        return redirect(url_for('courses'))

    return render_template('add_course.html')
@app.route("/meeting2")
def meeting2():
    return render_template("meeting.html", username=current_user.username)

@app.route('/view_chapter/<int:course_id>/', defaults={'chapter_index': 0})
@app.route('/view_chapter/<int:course_id>/<int:chapter_index>')
@login_required
def view_chapter(course_id, chapter_index):
    course = Course.query.get_or_404(course_id)
    if chapter_index < 0 or chapter_index >= len(course.chapters):
        return jsonify({'message': 'Invalid chapter index'}), 400
    chapter = course.chapters[chapter_index]
    return render_template('view_chapter.html', course=course, chapter=chapter, chapter_index=chapter_index)

@app.route('/meeting/<int:course_id>/', defaults={'chapter_index': 0})
@app.route('/meeting/<int:course_id>/<int:chapter_index>')
@login_required
def meeting(course_id, chapter_index):
    course = Course.query.get_or_404(course_id)
    if chapter_index < 0 or chapter_index >= len(course.chapters):
        return jsonify({'message': 'Invalid chapter index'}), 400
    chapter = course.chapters[chapter_index]
    room_id = request.args.get('roomID')
    role = request.args.get('role', 'Host')
    return render_template('view_chapter.html', username=current_user.username, course=course, chapter=chapter, chapter_index=chapter_index, room_id=room_id, role=role)

@app.route('/join/<int:course_id>/', defaults={'chapter_index': 0}, methods=['GET', 'POST'])
@app.route('/join/<int:course_id>/<int:chapter_index>', methods=['GET', 'POST'])
@login_required
def join(course_id, chapter_index):
    if request.method == 'POST':
        room_id = request.form.get('roomID')
        course = Course.query.get_or_404(course_id)
        if chapter_index < 0 or chapter_index >= len(course.chapters):
            return jsonify({'message': 'Invalid chapter index'}), 400
        if current_user.role == 'student':
            return redirect(url_for('meeting', course_id=course_id, chapter_index=chapter_index, roomID=room_id, role='Audience'))
        elif current_user.role == 'teacher':
            return redirect(url_for('meeting', course_id=course_id, chapter_index=chapter_index, roomID=room_id))
    else:
        course = Course.query.get_or_404(course_id)
        if chapter_index < 0 or chapter_index >= len(course.chapters):
            return jsonify({'message': 'Invalid chapter index'}), 400
        chapter = course.chapters[chapter_index]
        return render_template('view_chapter.html', username=current_user.username, course=course, chapter=chapter, chapter_index=chapter_index)

@app.route('/delete_course/<int:course_id>', methods=['POST'])
@login_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)

    # Ensure the current user is the teacher who created the course
    if course.teacher_id != current_user.id:
        return jsonify({'message': 'You do not have permission to delete this course.'}), 403

    # Delete course files from the server
    def delete_file(file_path):
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    
    if course.thumbnail_img:
        thumbnail_path = os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnail', course.thumbnail_img)
        delete_file(thumbnail_path)
    
    if course.temp_video:
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], 'sample_video', course.temp_video)
        delete_file(video_path)
    
    for chapter in course.chapters:
        if 'resources_files' in chapter and chapter['resources_files']:
            for resource in chapter['resources_files']:
                resource_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Resource', resource)
                delete_file(resource_path)
        
        if 'assignment_file' in chapter and chapter['assignment_file']:
            assignment_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Assignment', chapter['assignment_file'])
            delete_file(assignment_path)
                
        if 'course_file' in chapter and chapter['course_file']:
            course_file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Coures', chapter['course_file'])
            delete_file(course_file_path)

    # Delete the course from the database by id
    try:
        db.session.query(Course).filter_by(id=course_id).delete()
        db.session.query(student_courses_enrolled).filter_by(course_id=course_id).delete()
        db.session.query(student_courses_completed).filter_by(course_id=course_id).delete()

        db.session.commit()
    except Exception as e:
        db.session.rollback()  # Rollback in case of error
        return jsonify({'message': f'Failed to delete course from database: {str(e)}'}), 500
    
    return redirect(url_for('courses'))
    
# @app.route('/edit_course/<int:course_id>', methods=['GET', 'POST'])
# @login_required
# def edit_course(course_id):
#     course = Course.query.get_or_404(course_id)

#     if current_user.role != 'teacher' or current_user.id != course.teacher_id:
#         flash('Unauthorized to edit this course.', 'danger')
#         return redirect(url_for('dashboard'))

#     if request.method == 'POST':
#         course.name = request.form['name']
#         course.description = request.form['description']
#         course.level = request.form['level']
#         course.domain = request.form['domain']
#         course.language = request.form['language']
#         course.payment = request.form['payment']
#         course.mode_of_class = request.form['mode_of_class']
#         course.learner_type = request.form['learner_type']

#         # Handle thumbnail image update
#         thumbnail_img = request.files.get('thumbnail_img')
#         if thumbnail_img and thumbnail_img.filename != '':
#             thumbnail_img_filename = secure_filename(thumbnail_img.filename)
#             thumbnail_img.save(os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnail', thumbnail_img_filename))
#             course.thumbnail_img = thumbnail_img_filename

#         # Handle sample video update
#         temp_video = request.files.get('temp_video')
#         if temp_video and temp_video.filename != '':
#             temp_video_filename = secure_filename(temp_video.filename)
#             temp_video.save(os.path.join(app.config['UPLOAD_FOLDER'], 'sample_video', temp_video_filename))
#             course.temp_video = temp_video_filename

#         # Handle chapters
#         chapter_count = int(request.form.get('chapter_count', 0))
#         updated_chapters = []

#         for i in range(1, chapter_count + 1):
#             chapter_title = request.form.get(f'chapter_{i}_title')
#             chapter_description = request.form.get(f'chapter_{i}_description')
#             chapter_note = request.form.get(f'chapter_{i}_note')
#             chapter_meeting_link = request.form.get(f'chapter_{i}_meeting_link')
#             chapter_course_link = request.form.get(f'chapter_{i}_course_link')
#             chapter_resource_link = request.form.get(f'chapter_{i}_resource_link')

#             existing_chapter = next((c for c in course.chapters if c['title'] == chapter_title), {})

#             chapter = {
#                 'title': chapter_title,
#                 'description': chapter_description,
#                 'assignment_file': existing_chapter.get('assignment_file', ''),
#                 'resources_files': existing_chapter.get('resources_files', []),
#                 'course_file': existing_chapter.get('course_file', ''),
#                 'note': chapter_note,
#                 'meeting_link': chapter_meeting_link,
#                 'course_link': chapter_course_link,
#                 'resource_link': chapter_resource_link if chapter_resource_link else existing_chapter.get('resource_link', '')
#             }

#             # Handle assignment file update
#             chapter_assignment_file = request.files.get(f'chapter_{i}_assignment_file')
#             if chapter_assignment_file and chapter_assignment_file.filename != '':
#                 assignment_filename = secure_filename(chapter_assignment_file.filename)
#                 assignment_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Assignment', assignment_filename)
#                 chapter_assignment_file.save(assignment_path)
#                 chapter['assignment_file'] = assignment_filename
#             else:
#                 chapter['assignment_file'] = existing_chapter.get('assignment_file', '')

#             # Handle course file update if mode is 'Recorded'
#             if course.mode_of_class == 'Recorded':
#                 chapter_course_file = request.files.get(f'chapter_{i}_course_file')
#                 if chapter_course_file and chapter_course_file.filename != '':
#                     course_filename = secure_filename(chapter_course_file.filename)
#                     course_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Course', course_filename)
#                     try:
#                         chapter_course_file.save(course_path)
#                         chapter['course_file'] = course_filename
#                     except FileNotFoundError as e:
#                         flash(f'Error saving course file: {e}', 'danger')
#                         return redirect(url_for('edit_course', course_id=course_id))
#                 else:
#                     chapter['course_file'] = existing_chapter.get('course_file', '')

#             # Handle resources files update
#             chapter_resources_files = request.files.getlist(f'chapter_{i}_resources')
#             if chapter_resources_files:
#                 for file in chapter_resources_files:
#                     if file and file.filename != '':
#                         filename = secure_filename(file.filename)
#                         file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Resource', filename)
#                         file.save(file_path)
#                         chapter['resources_files'].append(filename)
#             else:
#                 chapter['resources_files'] = existing_chapter.get('resources_files', [])

#             updated_chapters.append(chapter)

#         course.chapters = updated_chapters
#         db.session.commit()

#         flash('Course updated successfully!', 'success')
#         return redirect(url_for('courses'))

#     return render_template('edit_course.html', course=course)
@app.route('/edit_course/<int:course_id>', methods=['GET', 'POST'])
@login_required
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)

    if current_user.role != 'teacher' or current_user.id != course.teacher_id:
        flash('Unauthorized to edit this course.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        course.name = request.form['name']
        course.description = request.form['description']
        course.level = request.form['level']
        course.domain = request.form['domain']
        course.language = request.form['language']
        course.payment = request.form['payment']
        course.mode_of_class = request.form['mode_of_class']
        course.learner_type = request.form['learner_type']
        course.fees = request.form['fees']

        # Handle thumbnail image update
        thumbnail_img = request.files.get('thumbnail_img')
        if thumbnail_img and thumbnail_img.filename != '':
            old_thumbnail_img = course.thumbnail_img
            thumbnail_img_filename = f'{course_id}_thumbnail_{secure_filename(thumbnail_img.filename)}'
            thumbnail_img.save(os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnail', thumbnail_img_filename))
            course.thumbnail_img = thumbnail_img_filename

            # Delete old thumbnail image if it exists
            if old_thumbnail_img and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnail', old_thumbnail_img)):
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnail', old_thumbnail_img))

        # Handle sample video update
        temp_video = request.files.get('temp_video')
        if temp_video and temp_video.filename != '':
            old_temp_video = course.temp_video
            temp_video_filename = f'{course_id}_temp_video_{secure_filename(temp_video.filename)}'
            temp_video.save(os.path.join(app.config['UPLOAD_FOLDER'], 'sample_video', temp_video_filename))
            course.temp_video = temp_video_filename

            # Delete old sample video if it exists
            if old_temp_video and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'sample_video', old_temp_video)):
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], 'sample_video', old_temp_video))

        # Handle chapters
        chapter_count = int(request.form.get('chapter_count', 0))
        updated_chapters = []

        for i in range(1, chapter_count + 1):
            chapter_title = request.form.get(f'chapter_{i}_title')
            chapter_description = request.form.get(f'chapter_{i}_description')
            chapter_note = request.form.get(f'chapter_{i}_note')
            chapter_meeting_link = request.form.get(f'chapter_{i}_meeting_link')
            chapter_date = request.form.get(f'chapter_{i}_date')
            chapter_time = request.form.get(f'chapter_{i}_time')
            chapter_course_link = request.form.get(f'chapter_{i}_course_link')
            chapter_resource_link = request.form.get(f'chapter_{i}_resource_link')

            existing_chapter = next((c for c in course.chapters if c['title'] == chapter_title), {})

            chapter = {
                'title': chapter_title,
                'description': chapter_description,
                'assignment_file': existing_chapter.get('assignment_file', ''),
                'resources_files': existing_chapter.get('resources_files', ''),
                'course_file': existing_chapter.get('course_file', ''),
                'note': chapter_note,
                'meeting_link': chapter_meeting_link,
                'date': chapter_date,
                'time': chapter_time,
                'course_link': chapter_course_link,
                'resource_link': chapter_resource_link if chapter_resource_link else existing_chapter.get('resource_link', '')
            }

            # Handle assignment file update
            chapter_assignment_file = request.files.get(f'chapter_{i}_assignment_file')
            if chapter_assignment_file and chapter_assignment_file.filename != '':
                old_assignment_file = existing_chapter.get('assignment_file', '')
                assignment_filename = f'{course_id}_chapter_{i}_assignment_{secure_filename(chapter_assignment_file.filename)}'
                assignment_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Assignment', assignment_filename)
                chapter_assignment_file.save(assignment_path)
                chapter['assignment_file'] = assignment_filename

                # Delete old assignment file if it exists
                if old_assignment_file and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'Assignment', old_assignment_file)):
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], 'Assignment', old_assignment_file))

            # Handle course file update if mode is 'Recorded'
            if course.mode_of_class == 'Recorded':
                chapter_course_file = request.files.get(f'chapter_{i}_course_file')
                if chapter_course_file and chapter_course_file.filename != '':
                    old_course_file = existing_chapter.get('course_file', '')
                    course_filename = f'{course_id}_chapter_{i}_course_{secure_filename(chapter_course_file.filename)}'
                    course_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Course', course_filename)
                    try:
                        chapter_course_file.save(course_path)
                        chapter['course_file'] = course_filename

                        # Delete old course file if it exists
                        if old_course_file and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'Course', old_course_file)):
                            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], 'Course', old_course_file))
                    except FileNotFoundError as e:
                        flash(f'Error saving course file: {e}', 'danger')
                        return redirect(url_for('edit_course', course_id=course_id))
                else:
                    chapter['course_file'] = existing_chapter.get('course_file', '')

            # Handle resources files update
            chapter_resource_file = request.files.get(f'chapter_{i}_resource_file')
            old_resource_file = existing_chapter.get('resources_files', '')

            if chapter_resource_file and chapter_resource_file.filename != '':
                resource_filename = f'{course_id}_chapter_{i}_resource_{secure_filename(chapter_resource_file.filename)}'
                resource_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Resource', resource_filename)
                
                try:
                    # Save the new resource file
                    chapter_resource_file.save(resource_path)
                    chapter['resources_files'] = resource_filename  # Save only the new file name
                    
                    # Delete old resource file if it exists and is different from the new one
                    if old_resource_file and old_resource_file != resource_filename:
                        old_resource_file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Resource', old_resource_file)
                        if os.path.exists(old_resource_file_path):
                            os.remove(old_resource_file_path)
                except FileNotFoundError as e:
                    flash(f'Error saving resource file: {e}', 'danger')
                    return redirect(url_for('edit_course', course_id=course_id))
            else:
                chapter['resources_files'] = old_resource_file  # Keep the old file if no new file is uploaded

            updated_chapters.append(chapter)

        course.chapters = updated_chapters

        quiz_count = int(request.form.get('quiz_count', 0))
        updated_quizzes = []

        for i in range(1, quiz_count + 1):
            question = request.form.get(f'quiz_{i}_question')
            options = [
                request.form.get(f'quiz_{i}_option_1'),
                request.form.get(f'quiz_{i}_option_2'),
                request.form.get(f'quiz_{i}_option_3'),
                request.form.get(f'quiz_{i}_option_4')
            ]
            correct_answer = int(request.form.get(f'quiz_{i}_correct_answer'))

            updated_quizzes.append({
                'question': question,
                'options': options,
                'correct_answer': correct_answer
            })

        course.quizzes = updated_quizzes

        db.session.commit()

        flash('Course updated successfully!', 'success')
        return redirect(url_for('courses'))

    return render_template('edit_course.html', course=course)
    
# @app.route('/view_chapter/<int:course_id>/', defaults={'chapter_index': 0})
# @app.route('/view_chapter/<int:course_id>/<int:chapter_index>')
# @login_required
# def view_chapter(course_id, chapter_index):
#     course = Course.query.get_or_404(course_id)
#     if chapter_index < 0 or chapter_index >= len(course.chapters):
#         return jsonify({'message': 'Invalid chapter index'}), 400
#     # save last view chapter and redirect ti that
    
#     chapter = course.chapters[chapter_index]
#     return render_template('view_chapter.html', course=course, chapter=chapter, chapter_index=chapter_index)

@app.route('/enroll/<int:course_id>', methods=['POST'])
@login_required
def enroll(course_id):
    course = Course.query.get_or_404(course_id)
    student = Student.query.get_or_404(current_user.id)

    # Check if the student is already enrolled in the course
    if course in student.enrolled_courses or student.courses_completed:
        flash('You are already enrolled in this course.', 'info')
        return redirect(url_for('view_chapter', course_id=course_id))

    payment_link = None

    try:
        # Debugging: Print course details
        print(f"Course Payment: {course.payment}")
        print(f"Course Level: {course.level}")
        print(f"Course Fees: {course.fees}")

        # Ensure fees is an integer
        if isinstance(course.fees, str):
            course.fees = int(course.fees)
        
        # Determine the payment link based on course payment status, level, and fees
        if course.payment == 'Paid':
            if course.level == 'Beginner':
                payment_links = {
                    500: 'https://payments-test.cashfree.com/forms/beginer',
                    600: 'https://payments-test.cashfree.com/forms/beginner-600',
                    750: 'https://payments-test.cashfree.com/forms/beginner-750',
                    900: 'https://payments-test.cashfree.com/forms/beginner-900'
                }
            elif course.level == 'Intermediate':
                payment_links = {
                    900: 'https://payments-test.cashfree.com/forms/intermediate-900',
                    1000: 'https://payments-test.cashfree.com/forms/intermediate-1000',
                    1500: 'https://payments-test.cashfree.com/forms/intermediate-1500',
                    2000: 'https://payments-test.cashfree.com/forms/intermediate-2000'
                }
            elif course.level == 'Advanced':
                payment_links = {
                    1500: 'https://payments-test.cashfree.com/forms/advanced-1500',
                    2000: 'https://payments-test.cashfree.com/forms/advanced-2000',
                    2500: 'https://payments-test.cashfree.com/forms/advanced-2500',
                    3500: 'https://payments-test.cashfree.com/forms/advanced-3500'
                }
            else:
                raise ValueError("Invalid course level.")
            
            payment_link = payment_links.get(course.fees, None)
        
        elif course.payment == 'Free':
            payment_link = url_for('view_chapter', course_id=course_id)

        print(f"Payment Link: {payment_link}")

        if payment_link is None:
            raise ValueError("No payment link available.")

    except Exception as e:
        flash(f'An error occurred during payment processing: {str(e)}', 'danger')
        return redirect(url_for('courses'))

    # Enroll the student in the course if payment_link is valid
    if payment_link:
        # if it's in completed coures table then do not add in enrolled coures table
        if db.session.query(student_courses_completed).filter_by(course_id=course_id, student_id=current_user.id):
            student.enrolled_courses.append(course)
            db.session.commit()
            return redirect(payment_link)

    # If no payment link, should not reach here
    flash('An unexpected error occurred.', 'danger')
    return redirect(url_for('courses'))

    # Redirect to the payment link or directly to view_chapter if the course is free

@app.route('/admin')
def admin():
    return render_template('admin.html')



@app.route('/download/<filename>')
def download_file(filename):
    # Define the path to your instance folder
    directory = os.path.join(app.instance_path)  # Replace 'your_folder' with the appropriate folder name

    try:
        # Send the file from the directory
        return send_from_directory(directory, filename, as_attachment=True)
    except FileNotFoundError:
        abort(404)

def zip_directory(directory_path, zip_filename):
    """Create a zip file from a directory and return the zip file path."""
    shutil.make_archive(zip_filename, 'zip', directory_path)
    return f'{zip_filename}.zip'

@app.route('/download-directory')
def download_directory():
    # Define the directory to be zipped
    directory = os.path.join(app.static_folder, 'uploads')
    
    # Define the path for the zip file in the uploads folder
    zip_filename = 'uploads_directory.zip'
    zip_filepath = os.path.join(app.static_folder, 'uploads', zip_filename)

    try:
        # Create the zip file in the uploads folder
        with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, directory)
                    zipf.write(file_path, arcname)

        @after_this_request
        def remove_file(response):
            try:
                os.remove(zip_filepath)
            except Exception as e:
                print(f"Error removing file: {e}")
            return response

        # Serve the zip file
        return send_file(zip_filepath, as_attachment=True)

    except FileNotFoundError:
        abort(404)
if __name__ == '__main__':
    with app.app_context():
            db.create_all()  # Create database tables based on the models
    app.run(debug=True,host='0.0.0.0',port='5000')

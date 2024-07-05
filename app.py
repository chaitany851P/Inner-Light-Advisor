from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_required, login_user, current_user, logout_user 
import os 
import openai
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.dialects.sqlite import JSON

from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.types import JSON
 

# Initialize OpenAI API key
openai.api_key = 'sk-proj-I59lHlwYy3Ns6mpMga8aT3BlbkFJYmnAY7QXsjUSueUG7sae'

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///user.db'
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')  # Define upload folder

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
    courses_enrolled = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    courses_completed = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    img = db.Column(db.String(200), nullable=True)
    __mapper_args__ = {'polymorphic_identity': 'student'}

class Teacher(User):
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    education = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    img = db.Column(db.String(200), nullable=True)
    courses = db.relationship('Course', backref='teacher', lazy=True)
    __mapper_args__ = {'polymorphic_identity': 'teacher'}

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(1000), nullable=False)
    level = db.Column(db.String(50), nullable=False)
    domain = db.Column(db.String(100), nullable=False)
    language = db.Column(db.String(50), nullable=False)
    payment = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    mode_of_class = db.Column(db.String(50), nullable=False)
    learner_type = db.Column(db.String(50), nullable=False)
    thumbnail_img = db.Column(db.String(200), nullable=True)
    temp_video = db.Column(db.String(200), nullable=True)
    chapters = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    videos = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    quizzes = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    __mapper_args__ = {'polymorphic_identity': 'course'}

class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"<ContactMessage(name={self.name}, email={self.email})>"


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

        new_contact = ContactMessage(name=name, email=email, message=message)
        
        try:
            db.session.add(new_contact)
            db.session.commit()
            return redirect('/contact')  # Redirect to home or success page
        except:
            return 'There was an issue adding your contact information.'

    return render_template('contect.html')

@app.route('/FAQs')
def FAQs():
    return render_template('faqs.html')

@app.route('/ac')
def ac():
    return render_template('temp.html')

@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    if request.method == 'POST':
        # Retrieve other form fields
        name = request.form['name']
        description = request.form['description']
        level = request.form['level']
        domain = request.form['domain']
        language = request.form['language']
        payment = request.form['payment']
        mode_of_class = request.form['mode_of_class']
        learner_type = request.form['learner_type']

        # Save uploaded files
        thumbnail_img = request.files['thumbnail_img']
        if thumbnail_img.filename != '':
            thumbnail_img.save(os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnails', thumbnail_img.filename))

        temp_video = request.files['temp_video']
        if temp_video.filename != '':
            temp_video.save(os.path.join(app.config['UPLOAD_FOLDER'], 'videos', temp_video.filename))

        chapters = {}
        for i in range(1, chapter_count + 1):
            chapter_title = request.form[f'chapter_{i}_title']
            chapter_description = request.form[f'chapter_{i}_description']
            chapter_assignment_file = request.files.get(f'chapter_{i}_assignment_file')
            chapter_resources_files = request.files.getlist(f'chapter_{i}_resources')  # Retrieve multiple files
            chapter_note = request.form[f'chapter_{i}_note']
            chapter_course_file = request.files.get(f'chapter_{i}_course_file')

            # Save assignment file if provided
            if chapter_assignment_file and chapter_assignment_file.filename != '':
                chapter_assignment_file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'assignments', secure_filename(chapter_assignment_file.filename)))

            # Save resources files if provided
            resources_filenames = []
            for file in chapter_resources_files:
                if file.filename != '':
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'resources', filename)
                    file.save(file_path)
                    resources_filenames.append(filename)

            # Save course file if provided
            if chapter_course_file and chapter_course_file.filename != '':
                chapter_course_file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'courses', secure_filename(chapter_course_file.filename)))

            chapters[f'chapter_{i}'] = {
                'title': chapter_title,
                'description': chapter_description,
                'assignment_file': chapter_assignment_file.filename if chapter_assignment_file else None,
                'resources_files': resources_filenames,
                'note': chapter_note,
                'course_file': chapter_course_file.filename if chapter_course_file else None
            }

        # Save course details to database
        new_course = Course(name=name, description=description, level=level, domain=domain, language=language,
                            payment=payment, mode_of_class=mode_of_class, learner_type=learner_type,
                            thumbnail_img=thumbnail_img.filename if thumbnail_img else None,
                            temp_video=temp_video.filename if temp_video else None,
                            chapters=str(chapters))
        
        db.session.add(new_course)
        db.session.commit()

        return "Course added successfully!"
    
    return render_template('temp.html')

if __name__ == '__main__':
    with app.app_context():
            db.create_all()  # Create database tables based on the models
    app.run(debug=True)

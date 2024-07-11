from multiprocessing import reduction
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_required, login_user, current_user, logout_user 
import os 
import openai
from werkzeug.utils import secure_filename
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import relationship
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

    # Relationships
    # Assuming a relationship with courses table
    enrolled_courses = relationship('Course', secondary='student_courses_enrolled')
    completed_courses = relationship('Course', secondary='student_courses_completed')

    def __init__(self, username, email, password, img=None):
        super().__init__(username, email, password)
        self.img = img

# Define association tables for many-to-many relationships
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
    education = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    img = db.Column(db.String(200), nullable=True)
    courses = db.relationship('Course', backref='teacher', lazy=True)
    tasks = db.relationship('Task', backref='assigned_teacher', lazy=True)
    __mapper_args__ = {'polymorphic_identity': 'teacher'}
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pending')  # Example status field
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)

    def __repr__(self):
        return f"<Task(title='{self.title}', status='{self.status}')>"


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(1000), nullable=False)
    level = db.Column(db.String(50), nullable=False)
    domain = db.Column(db.String(100), nullable=False)
    language = db.Column(db.String(50), nullable=False)
    payment = db.Column(db.String(50000), nullable=False)
    mode_of_class = db.Column(db.String(50), nullable=False)
    learner_type = db.Column(db.String(50), nullable=False)
    thumbnail_img = db.Column(db.String(200), nullable=True)
    temp_video = db.Column(db.String(200), nullable=True)
    chapters = db.Column(MutableList.as_mutable(JSON), nullable=False, default=[])
    
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
    if current_user.role == 'student':
        enrolled_courses = current_user.enrolled_courses  # Assuming Student model has enrolled_courses relationship
        completed_courses = current_user.completed_courses  # Query completed courses for the current_user
        live_classes = []  # Query live classes for the current_user
        return render_template('dashboard.html', enrolled_courses=enrolled_courses, completed_courses=completed_courses, live_classes=live_classes)
    elif current_user.role == 'teacher':
        created_courses = []  # Query courses created by the current_user
        upcoming_tasks = Task.query.filter_by(teacher_id=current_user.id).all()  # Query tasks assigned to the current_user
        live_classes = []  # Query live classes for the current_user
        return render_template('dashboard.html', created_courses=created_courses, upcoming_tasks=upcoming_tasks, live_classes=live_classes)
    else:
        return redirect(url_for('login'))
    
@app.route('/edit_task/<int:task_id>', methods=['GET', 'POST'])
def edit_task(task_id):
    task = Task.query.get(task_id)
    

    if request.method == 'POST':
        task.title = request.form['title']
        task.description = request.form['description']
        task.status = request.form['status']
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
            if file.filename != '':
                filepath = save_profile_image(file)
                
                if current_user.role == 'student':
                    # Update profile image for student
                    student = Student.query.filter_by(username=current_user.username).first()
                    student.img = filepath
                    db.session.commit()
                elif current_user.role == 'teacher':
                    # Update profile image for teacher
                    teacher = Teacher.query.filter_by(username=current_user.username).first()
                    teacher.img = filepath
                    db.session.commit()

                flash('Profile image updated successfully')
                return redirect(url_for('profile'))  # Redirect to avoid re-posting on refresh

    # Fetch the user's profile image path
    if current_user.role == 'student':
        user = Student.query.filter_by(username=current_user.username).first()
        profile_image = user.img if user else None
    elif current_user.role == 'teacher':
        user = Teacher.query.filter_by(username=current_user.username).first()
        profile_image = user.img if user else None
    else:
        profile_image = None

    return render_template('profile.html', profile_image=profile_image)

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

@app.route('/course/<int:course_id>')
def course_detail(course_id):
    course = Course.query.get(course_id)
    return render_template('coures_detail.html', course=course)


@app.route('/coures_video')
def coures_video():
    return render_template('student/coures_video.html')

@app.route('/courses')
def courses():
    language = request.args.get('language', 'all')
    payment = request.args.get('payment', 'all')
    domain = request.args.get('domain', 'all')
    mode = request.args.get('mode', 'all')
    level = request.args.get('level', 'all')

    courses_query = Course.query

    if language != 'all':
        courses_query = courses_query.filter_by(language=language)
    if payment != 'all':
        courses_query = courses_query.filter_by(payment=payment)
    if domain != 'all':
        courses_query = courses_query.filter_by(domain=domain)
    if mode != 'all':
        courses_query = courses_query.filter_by(mode_of_class=mode)
    if level != 'all':
        courses_query = courses_query.filter_by(level=level)

    courses = courses_query.all()

    return render_template('courses.html', courses=courses)    

@app.route('/courses', methods=['POST'])
def course_list():
    language = request.args.get('language', 'all')
    payment = request.args.get('payment', 'all')
    domain = request.args.get('domain', 'all')
    mode = request.args.get('mode', 'all')
    level = request.args.get('level', 'all')

    filters = []
    if language != 'all':
        filters.append(Course.language == language)
    if payment != 'all':
        filters.append(Course.payment == payment)
    if domain != 'all':
        filters.append(Course.domain == domain)
    if mode != 'all':
        filters.append(Course.mode_of_class == mode)
    if level != 'all':
        filters.append(Course.level == level)

    if filters:
        courses = Course.query.filter(*filters).all()
    else:
        courses = Course.query.all()

    return render_template('courses.html', courses=courses)



@app.route('/edit_education', methods=['POST'])
def edit_education():
    if request.method == 'POST':
        try:
            
            degree = request.form['degree']
            university = request.form['university']
            year = int(request.form['year'])
            user_id = int(request.form['user_id'])

            # Retrieve current user based on user_id
            current_user = User.query.get(user_id)
            if not current_user:
                return "User not found", 404

            # Update education details if index is valid
            if current_user.education and index < len(current_user.education):
                current_user.education[index].degree = degree
                current_user.education[index].university = university
                current_user.education[index].year = year
                db.session.commit()
                return redirect(url_for('profile', user_id=user_id))
            else:
                return "Invalid index or education details", 400

        except Exception as e:
            return f"Error: {str(e)}", 500

    return redirect(url_for('profile')) 


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

@app.route('/delete_education/<int:index>', methods=['POST'])
@login_required
def delete_education(index):
    try:
        # Retrieve the current user's teacher instance
        teacher = Teacher.query.get(current_user.id)
        
        if not teacher:
            return jsonify({'message': 'Teacher not found.'}), 404
        
        # Ensure index is valid (1-based index in HTML form)
        if index <= 0 or index > len(teacher.education):
            raise ValueError("Invalid index provided")

        # Delete the education entry from the list
        del teacher.education[index - 1]  # Adjust index for zero-based list
        
        # Commit the updated teacher object to the database
        db.session.commit()
        
        return redirect(url_for('profile'))
    
    except Exception as e:
        return jsonify({'message': f'Failed to delete education: {str(e)}'}), 500

def save_profile_image(file):
    # Ensure the folder exists
    if not os.path.exists('static/uploads/Profile'):
        os.makedirs('static/uploads/Profile')

    filename = secure_filename(file.filename)
    filepath = os.path.join('static/uploads/Profile', filename)
    file.save(filepath)
    return filepath


    

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
    
@app.route('/add_task', methods=['GET', 'POST'])
def add_task():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        teacher_id = current_user.id  # Assuming current_user is authenticated and has an id attribute

        new_task = Task(title=title, description=description, teacher_id=teacher_id)

        try:
            db.session.add(new_task)
            db.session.commit()
            return redirect(url_for('dashboard'))  # Redirect to dashboard or wherever appropriate
        except Exception as e:
            db.session.rollback()
            print(f"Error adding task: {e}")
            # Handle error, possibly redirect to an error page or show an error message

    return render_template('add_task.html')

@app.route('/update_user_info', methods=['POST'])
@login_required
def update_user_info():
    current_user.name = request.form['name']
    current_user.dob = request.form['dob']
    db.session.commit()
    flash('User information updated successfully!', 'success')
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



@app.route('/add_course', methods=['GET', 'POST'])
@login_required
def add_course():
    if request.method == 'POST':
        if current_user.role != 'teacher':
            flash('Only teachers can add courses.', 'danger')
            return redirect(url_for('dashboard'))

        # Retrieve form fields
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
        if thumbnail_img and thumbnail_img.filename != '':
            thumbnail_img_filename = secure_filename(thumbnail_img.filename)
            thumbnail_img.save(os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnail', thumbnail_img_filename))
        else:
            thumbnail_img_filename = None

        temp_video = request.files['temp_video']
        if temp_video and temp_video.filename != '':
            temp_video_filename = secure_filename(temp_video.filename)
            temp_video.save(os.path.join(app.config['UPLOAD_FOLDER'], 'sample_video', temp_video_filename))
        else:
            temp_video_filename = None

        chapters = []
        chapter_count = int(request.form.get('chapter_count', 0))
        for i in range(1, chapter_count + 1):
            chapter_title = request.form[f'chapter_{i}_title']
            chapter_description = request.form[f'chapter_{i}_description']
            chapter_assignment_file = request.files.get(f'chapter_{i}_assignment_file')
            chapter_resources_files = request.files.getlist(f'chapter_{i}_resources')
            chapter_note = request.form[f'chapter_{i}_note']
            chapter_course_file = request.files.get(f'chapter_{i}_course_file')

            # Save assignment file if provided
            assignment_filename = None
            if chapter_assignment_file and chapter_assignment_file.filename != '':
                assignment_filename = secure_filename(chapter_assignment_file.filename)
                assignment_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Assignment', assignment_filename)
                chapter_assignment_file.save(assignment_path)

            # Save resources files if provided
            resources_filenames = []
            for file in chapter_resources_files:
                if file and file.filename != '':
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Resource', filename)
                    file.save(file_path)
                    resources_filenames.append(filename)

            # Save course file if provided
            course_filename = None
            if chapter_course_file and chapter_course_file.filename != '':
                course_filename = secure_filename(chapter_course_file.filename)
                course_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Coures', course_filename)
                chapter_course_file.save(course_path)

            chapters.append({
                'title': chapter_title,
                'description': chapter_description,
                'assignment_file': assignment_filename,
                'resources_files': resources_filenames,
                'note': chapter_note,
                'course_file': course_filename
            })

        # Save course details to the database
        new_course = Course(
            name=name,
            description=description,
            level=level,
            domain=domain,
            language=language,
            payment=payment,
            mode_of_class=mode_of_class,
            learner_type=learner_type,
            thumbnail_img=thumbnail_img_filename,
            temp_video=temp_video_filename,
            chapters=chapters,
            teacher_id=current_user.id  # Set the teacher_id to the current user's id
        )
        
        db.session.add(new_course)
        db.session.commit()

        flash('Course added successfully!', 'success')
        return redirect(url_for('courses'))
    
    return render_template('add_course.html')
    
@app.route('/edit_course/<int:course_id>', methods=['GET', 'POST'])
def edit_course(course_id):
    course = Course.query.get(course_id)

    if request.method == 'POST':
        # Update course details
        course.name = request.form['name']
        course.description = request.form['description']
        course.level = request.form['level']
        course.domain = request.form['domain']
        course.language = request.form['language']
        course.payment = request.form['payment']
        course.mode_of_class = request.form['mode_of_class']
        course.learner_type = request.form['learner_type']

        # Handle thumbnail image update if provided
        thumbnail_img = request.files.get('thumbnail_img')
        if thumbnail_img and thumbnail_img.filename != '':
            filename = secure_filename(thumbnail_img.filename)
            thumbnail_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Thumbnail', filename)
            thumbnail_img.save(thumbnail_path)
            course.thumbnail_img = filename

        # Handle sample video update if provided
        temp_video = request.files.get('temp_video')
        if temp_video and temp_video.filename != '':
            filename = secure_filename(temp_video.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Video', filename)
            temp_video.save(video_path)
            course.temp_video = filename

        # Update chapters
        chapters = []
        chapter_count = int(request.form.get('chapter_count', 0))
        for i in range(1, chapter_count + 1):
            chapter_title = request.form.get(f'chapter_{i}_title', '')
            chapter_description = request.form.get(f'chapter_{i}_description', '')
            chapter_assignment_file = request.files.get(f'chapter_{i}_assignment_file')
            chapter_resources_files = request.files.getlist(f'chapter_{i}_resources')
            chapter_note = request.form.get(f'chapter_{i}_note', '')
            chapter_course_file = request.files.get(f'chapter_{i}_course_file')

            # Save assignment file if provided
            assignment_filename = None
            if chapter_assignment_file and chapter_assignment_file.filename != '':
                assignment_filename = secure_filename(chapter_assignment_file.filename)
                assignment_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Assignment', assignment_filename)
                chapter_assignment_file.save(assignment_path)

            # Save resources files if provided
            resources_filenames = []
            for file in chapter_resources_files:
                if file and file.filename != '':
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Resource', filename)
                    file.save(file_path)
                    resources_filenames.append(filename)

            # Save course file if provided
            course_filename = None
            if chapter_course_file and chapter_course_file.filename != '':
                course_filename = secure_filename(chapter_course_file.filename)
                course_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Course', course_filename)
                chapter_course_file.save(course_path)

            chapters.append({
                'title': chapter_title,
                'description': chapter_description,
                'assignment_file': assignment_filename,
                'resources_files': resources_filenames,
                'note': chapter_note,
                'course_file': course_filename
            })

        course.chapters = chapters

        # Commit changes to the database
        db.session.commit()

        return redirect(url_for('courses'))

    # Render the edit course form with current course details
    return render_template('edit_course.html', course=course)

@app.route('/delete_course/<int:course_id>', methods=['POST'])
@login_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    # Ensure the current user is the teacher who created the course
    if course.teacher_id != current_user.id:
        return jsonify({'message': 'You do not have permission to delete this course.'}), 403
    
    # Delete course files from the server
    try:
        if course.thumbnail_img:
            thumbnail_path = os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnail', course.thumbnail_img)
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
        
        # Delete sample video if exists
        if course.temp_video:
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], 'sample_video', course.temp_video)
            if os.path.exists(video_path):
                os.remove(video_path)
        
        # Delete chapter assignment files
        for chapter in course.chapters:
            if chapter.assignment_file:
                assignment_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Assignment', chapter.assignment_file)
                if os.path.exists(assignment_path):
                    os.remove(assignment_path)
            
            # Delete resources files
            for resource in chapter.resources_files:
                resource_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Resource', chapter.resources_files)
                if os.path.exists(resource_path):
                    os.remove(resource_path)
            
            # Delete course file
            if chapter.course_file:
                course_file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'Course', chapter.course_file)
                if os.path.exists(course_file_path):
                    os.remove(course_file_path)

    except Exception as e:
        return jsonify({'message': f'Failed to delete course files: {str(e)}'}), 500
    
    # Delete the course from the database
    try:
        db.session.delete(course)
        db.session.commit()
        return redirect(url_for('courses'))
    except Exception as e:
        return jsonify({'message': f'Failed to delete course from database: {str(e)}'}), 500
    
    
@app.route('/view_chapter/<int:course_id>/', defaults={'chapter_index': 0})
@app.route('/view_chapter/<int:course_id>/<int:chapter_index>')
@login_required
def view_chapter(course_id, chapter_index):
    course = Course.query.get_or_404(course_id)
    if chapter_index < 0 or chapter_index >= len(course.chapters):
        return jsonify({'message': 'Invalid chapter index'}), 400
    
    chapter = course.chapters[chapter_index]
    return render_template('view_chapter.html', course=course, chapter=chapter, chapter_index=chapter_index)

@app.route('/enroll/<int:course_id>', methods=['POST'])
@login_required
def enroll(course_id):
    course = Course.query.get_or_404(course_id)
    student = Student.query.get_or_404(current_user.id)

    # Check if the student is already enrolled in the course
    
    student.enrolled_courses.append(course)
    db.session.commit()

    return redirect(url_for('view_chapter', course_id=course.id))  # Redirect to a relevant page
    

if __name__ == '__main__':
    with app.app_context():
            db.create_all()  # Create database tables based on the models
    app.run(debug=True)

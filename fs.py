import base64
from functools import wraps
from mailbox import Message
import re
import smtplib
from urllib.parse import parse_qs, urlparse
import uuid
from email.message import EmailMessage
from flask_mail import Mail, Message
from random import random
from venv import logger

from firebase_admin import firestore
import firebase_admin
from google.cloud.firestore_v1.base_query import FieldFilter

from firebase_admin import credentials, firestore
from flask import Flask, current_app, flash, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import os
import datetime
from socket import gaierror
import logging
from functools import wraps
from flask import redirect, url_for, flash
# from temp import send_reset_email
from decorators import student_required, teacher_required
# Initialize Flask App
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587  # For TLS
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_DEFAULT_SENDER'] = 'innerlightadvisor@gmail.com'
app.config['MAIL_USERNAME'] = 'innerlightadvisor@gmail.com'
app.config['MAIL_PASSWORD'] = 'rtbd qmce vzdu dzip'
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1MB limit (Firestore constraint)
mail = Mail(app)
# Initialize Firebase using the Firebase Admin SDK
cred = credentials.Certificate("firebase_config.json")  # Replace with your Firebase credentials file
firebase_admin.initialize_app(cred)
db = firestore.client()

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'




# Define the User base class for Flask-Login
class User(UserMixin):
    def __init__(self, id, name, email, role, enrolled_courses=None, completed_courses=None, learning_style=None):
        self.id = id
        self.name = name
        self.email = email
        self.role = role
        self.enrolled_courses = enrolled_courses if enrolled_courses is not None else []
        self.completed_courses = completed_courses if completed_courses is not None else []
        self.learning_style = learning_style

    def get_id(self):
        return self.id

class Student(User):
    def __init__(self, id, name, dob, phone, username, email, password, learning_style, img=None):
        super().__init__(
            id=id,
            name=name,
            email=email,
            role='student',
            learning_style=learning_style
        )
        self.dob = dob
        self.phone = phone
        self.username = username
        self.password = password  # Should be hashed
        self.img = img
        # No need for enrolled_courses in init as it's stored in Firestore

    def enroll_course(self, course_id, transaction=None):
        """Minimal enrollment - just course_id and empty completed_chapters"""
        updates = {
            f'courses_enrolled.{course_id}': {
                'completed_chapters': [],
                'enrolled_at': firestore.SERVER_TIMESTAMP
            },
            'last_updated': firestore.SERVER_TIMESTAMP
        }
        
        if transaction:
            student_ref = db.collection("students").document(self.id)
            transaction.update(student_ref, updates)
        else:
            db.collection("students").document(self.id).update(updates)

    def complete_chapter(self, course_id, chapter_index, transaction=None):
        """Mark a chapter as completed for a course"""
        updates = {
            f'courses_enrolled.{course_id}.completed_chapters': firestore.ArrayUnion([chapter_index]),
            'last_updated': firestore.SERVER_TIMESTAMP
        }
        
        if transaction:
            student_ref = db.collection("students").document(self.id)
            transaction.update(student_ref, updates)
        else:
            db.collection("students").document(self.id).update(updates)


# Task class for task management
class Task:
    def __init__(self, title, description, teacher_id, due_date, status="Pending"):
        self.title = title
        self.description = description
        self.teacher_id = teacher_id
        self.due_date = due_date
        self.status = status

    def save_to_firestore(self):
        """Saves the task to Firestore"""
        task_data = {
            "title": self.title,
            "description": self.description,
            "teacher_id": self.teacher_id,
            "due_date": self.due_date,
            "status": self.status
        }
        db.collection("tasks").add(task_data)

    @staticmethod
    def get_task(task_id):
        """Retrieves a task from Firestore by its ID"""
        task_ref = db.collection("tasks").document(task_id)
        task = task_ref.get()
        if task.exists:
            return task.to_dict()
        return None


# Teacher class
class Teacher(User):
    def __init__(self, id, name, dob, phone, username, email, password, learning_style, education=None, img=None, signature=None):
        super().__init__(id=id, name=name, email=email, role='teacher', learning_style=learning_style)
        self.dob = dob
        self.phone = phone
        self.username = username
        self.password = password  # Consider hashing before storing
        self.education = education if education else []
        self.img = img
        self.signature = signature
        self.courses_taught = []  # Courses created/taught by the teacher
        self.tasks = []
        self.upi_qr = None

class Admin(UserMixin):
    def __init__(self, id, username, email, password, permissions=None, img=None):
        self.id = id
        self.username = username
        self.email = email
        self.password = password
        self.permissions = permissions or []
        self.img = img
        self.role = "admin"

    def get_id(self):
        return str(self.id)

    @property
    def is_admin(self):
        return True

def create_admin(username, email, password, permissions=None, img_url=None):
    """Add a new admin to Firestore with hashed password"""
    try:
        # Check if email exists in any collection
        for collection in ['admins', 'teachers', 'students']:
            if db.collection(collection).where('email', '==', email).get():
                return False, f"Email {email} already exists in {collection}", None
        
        # Hash password
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        # Set default permissions if none provided
        if not permissions:
            permissions = ['manage_users', 'manage_courses', 'view_reports']
        
        # Admin data structure
        admin_data = {
            'username': username,
            'email': email,
            'password': hashed_password,
            'permissions': permissions,
            'role': 'admin',
            'created_at': firestore.SERVER_TIMESTAMP,
            'last_updated': firestore.SERVER_TIMESTAMP
        }
        
        # Add optional image URL
        if img_url:
            admin_data['img'] = img_url
        
        # Add to Firestore
        admin_ref = db.collection('admins').document()
        admin_ref.set(admin_data)
        
        return True, "Admin created successfully", admin_ref.id
        
    except Exception as e:
        return False, f"Error creating admin: {str(e)}", None


# Improved user loader that distinguishes between teacher and student
@login_manager.user_loader
def load_user(user_id):
    # Try to load as admin first
    admin_ref = db.collection("admins").document(user_id).get()
    if admin_ref.exists:
        admin_data = admin_ref.to_dict()
        return Admin(
            id=user_id,
            username=admin_data.get("username"),
            email=admin_data.get("email"),
            password=admin_data.get("password"),
            permissions=admin_data.get("permissions", []),
            img=admin_data.get("img", None)
        )

    # Then try to load as teacher
    teacher_ref = db.collection("teachers").document(user_id).get()
    if teacher_ref.exists:
        user_data = teacher_ref.to_dict()
        return Teacher(
            id=user_id,
            name=user_data.get("username"),
            dob=user_data.get("dob", ""),
            phone=user_data.get("phone", ""),
            username=user_data.get("username"),
            email=user_data.get("email"),
            password=user_data.get("password"),
            learning_style=user_data.get("learning_style"),
            education=user_data.get("education", []),
            img=user_data.get("img"),
            signature=user_data.get("signature")
        )

    # Finally try to load as student
    student_ref = db.collection("students").document(user_id).get()
    if student_ref.exists:
        user_data = student_ref.to_dict()
        return Student(
            id=user_id,
            name=user_data.get("username"),
            dob=user_data.get("dob", ""),
            phone=user_data.get("phone", ""),
            username=user_data.get("username"),
            email=user_data.get("email"),
            password=user_data.get("password"),
            learning_style=user_data.get("learning_style", "Unassigned"),
            img=user_data.get("img")
        )

    return None


# Signup route with teacher and student fields
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']  # 'student' or 'teacher'

        # Determine Firestore collection based on role
        collection_name = "students" if role == "student" else "teachers"
        users_ref = db.collection(collection_name)

        # Check if username or email already exists
        existing_user = users_ref.where("username", "==", username).stream()
        existing_email = users_ref.where("email", "==", email).stream()
        if any(existing_user) or any(existing_email):
            flash('Username or Email already exists!', 'danger')
            return redirect(url_for('signup'))

        # Hash the password
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # Create user data with role-specific fields
        if role == "teacher":
            user_data = {
                "username": username,
                "email": email,
                "password": hashed_password,
                "role": role,
                "learning_style": "Unassigned",
                "courses_taught": [],
                "dob": request.form.get("dob", ""),
                "phone": request.form.get("phone", ""),
                "education": request.form.get("education", ""),
                "img": None,
                "signature": None
            }
        else:  # student
            user_data = {
                "username": username,
                "email": email,
                "password": hashed_password,
                "role": role,
                "learning_style": "Unassigned",
                "courses_enrolled": [],
                "courses_completed": []
            }

        # Use username as document ID
        users_ref.document(username).set(user_data)
        session['username'] = username
        session['role'] = role

        flash('Signup successful!', 'success')
        return redirect(url_for('test'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter both email and password', 'danger')
            return redirect(url_for('login'))

        try:
            user_obj = None
            user_role = None
            
            # Search across all user collections
            for collection in ['admins', 'teachers', 'students']:
                users_ref = db.collection(collection).where('email', '==', email).limit(1).stream()
                
                for user in users_ref:
                    user_data = user.to_dict()
                    
                    # Verify password
                    if not check_password_hash(user_data.get('password', ''), password):
                        continue
                        
                    # Create appropriate user object based on role
                    if collection == 'admins':
                        user_obj = Admin(
                            id=user.id,
                            username=user_data.get('username', ''),
                            email=email,
                            password=user_data.get('password'),
                            permissions=user_data.get('permissions', []),
                            img=user_data.get('img')
                        )
                        user_role = 'admin'
                        
                    elif collection == 'teachers':
                        user_obj = Teacher(
                            id=user.id,
                            name=user_data.get('name', ''),
                            dob=user_data.get('dob'),
                            phone=user_data.get('phone', ''),
                            username=user_data.get('username', ''),
                            email=email,
                            password=user_data.get('password'),
                            learning_style=user_data.get('learning_style'),
                            education=user_data.get('education', []),
                            img=user_data.get('img')
                        )
                        user_role = 'teacher'
                        
                    elif collection == 'students':
                        user_obj = Student(
                            id=user.id,
                            name=user_data.get('name', ''),
                            dob=user_data.get('dob'),
                            phone=user_data.get('phone', ''),
                            username=user_data.get('username', ''),
                            email=email,
                            password=user_data.get('password'),
                            learning_style=user_data.get('learning_style'),
                            img=user_data.get('img')
                        )
                        user_role = 'student'
                    
                    break  # Exit loop if user found
                
                if user_obj:
                    break  # Exit collection loop if user found
            
            if not user_obj:
                flash('Invalid email or password', 'danger')
                return redirect(url_for('login'))
            
            # Login the user
            login_user(user_obj)
            session['role'] = user_role
            
            # Log login activity
            try:
                db.collection('login_activity').add({
                    'user_id': user_obj.id,
                    'email': email,
                    'role': user_role,
                    'timestamp': firestore.SERVER_TIMESTAMP,
                    'ip_address': request.remote_addr
                })
            except Exception as e:
                app.logger.error(f"Failed to log login activity: {str(e)}")
            
            flash('Login successful!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
            
        except Exception as e:
            app.logger.error(f"Login error: {str(e)}")
            flash('An error occurred during login', 'danger')
            return redirect(url_for('login'))
    
    return render_template('login.html')


# Courses route with filtering and learning style matching (uses consistent "learning_style")
@app.route('/courses')
@login_required
def courses():
    try:
        # Get filter parameters
        level = request.args.get('level', '')
        domain = request.args.get('domain', '')
        language = request.args.get('language', '')
        payment = request.args.get('payment', '')

        # Create current_filters dictionary to pass to template
        current_filters = {
            'level': level,
            'domain': domain,
            'language': language,
            'payment': payment
        }

        # Base query based on user role
        if current_user.role == 'admin':
            query = db.collection('courses')
            print("Admin: Fetching all courses")
        elif current_user.role == 'student':
            query = db.collection('courses').where(filter=FieldFilter('status', '==', 'active'))  # Changed to 'active'
            print(f"Student: Base query with status='active', Learning Style='{current_user.learning_style}'")
            if current_user.learning_style and current_user.learning_style in ['Visual', 'Auditory', 'Kinesthetic']:
                query = query.where(filter=FieldFilter('learner_type', '==', current_user.learning_style))
            else:
                print("Student: No valid learning style, skipping learner_type filter")
        elif current_user.role == 'teacher':
            query = db.collection('courses').where(filter=FieldFilter('teacher_id', '==', current_user.id))
            print(f"Teacher: Fetching courses for teacher_id='{current_user.id}'")

        # Apply filters dynamically
        if level:
            query = query.where(filter=FieldFilter('level', '==', level))
        if domain:
            query = query.where(filter=FieldFilter('domain', '==', domain))
        if language:
            query = query.where(filter=FieldFilter('language', '==', language))
        if payment:
            query = query.where(filter=FieldFilter('payment', '==', payment))

        # Execute query and debug
        docs = query.stream()
        courses = []
        for doc in docs:
            course = doc.to_dict()
            course['id'] = doc.id
            courses.append(course)
        print(f"{current_user.role}: Found {len(courses)} courses after filters:")
        for course in courses:
            print(f" - {course['name']}: status={course.get('status')}, learner_type={course.get('learner_type')}")

        # If no courses found for student, check all courses for debugging
        if current_user.role == 'student' and not courses:
            all_courses = db.collection('courses').stream()
            print("Student: No courses matched filters. All courses in Firestore:")
            for doc in all_courses:
                course_data = doc.to_dict()
                print(f" - {course_data['name']}: status={course_data.get('status')}, learner_type={course_data.get('learner_type')}")

        # Dynamically fetch domains and languages from Firestore
        domains_ref = db.collection('domains').stream()
        domains = [{'name': doc.to_dict().get('name', '')} for doc in domains_ref] or [{'name': 'Technology'}, {'name': 'Science'}]

        languages_ref = db.collection('languages').stream()
        languages = [{'name': doc.to_dict().get('name', '')} for doc in languages_ref] or [{'name': 'English'}, {'name': 'Spanish'}]

        return render_template('courses.html',
                               courses=courses,
                               domains=domains,
                               languages=languages,
                               current_filters=current_filters)

    except Exception as e:
        flash(f"Error loading courses: {str(e)}", "error")
        return redirect(url_for('index'))

@app.route('/add_course', methods=['GET', 'POST'])
@login_required
def add_course():
    if request.method == 'GET':
        domains = [{'name': 'Technology'}, {'name': 'Science'}]
        languages = [{'name': 'English'}, {'name': 'Spanish'}]
        return render_template('add_course.html', domains=domains, languages=languages)

    if request.method == 'POST':
        try:
            # Validate required fields
            required_fields = ['name', 'description', 'level', 'domain', 'language',
                             'payment', 'mode_of_class', 'learner_type', 'chapter_count']
            for field in required_fields:
                if field not in request.form or not request.form[field]:
                    raise ValueError(f"Missing or empty required field: {field}")

            # Handle new domain/language if selected
            domain = request.form['domain']
            if domain == 'Add New' and 'new_domain' in request.form and request.form['new_domain']:
                domain = request.form['new_domain'].strip()
            
            language = request.form['language']
            if language == 'Add New' and 'new_language' in request.form and request.form['new_language']:
                language = request.form['new_language'].strip()

            # Prepare course data (don't save to DB yet)
            course_data = {
                'name': request.form['name'],
                'description': request.form['description'],
                'level': request.form['level'],
                'domain': domain,
                'language': language,
                'payment': request.form['payment'],
                'mode_of_class': request.form['mode_of_class'],
                'learner_type': request.form['learner_type'],
                'chapter_count': int(request.form['chapter_count']),
                'quiz_count': int(request.form.get('quiz_count', 0)),
                'teacher_id': current_user.id,
                'teacher_name': current_user.name,
                'timestamp': firestore.SERVER_TIMESTAMP,
                'status': 'pending',
                'rating': 0.0,
                'rating_count': 0,
                'enrollment_count': 0
            }

            # Handle payment price
            if course_data['payment'] == 'Paid':
                if 'price' not in request.form or not request.form['price']:
                    raise ValueError("Price is required for paid courses")
                course_data['price'] = float(request.form['price'])
            else:
                course_data['price'] = 0.0

            # Handle thumbnail image
            file = request.files.get('thumbnail_img')
            if file and file.filename:
                if file.content_length and file.content_length < app.config['MAX_CONTENT_LENGTH']:
                    filename = secure_filename(file.filename)
                    image_data = base64.b64encode(file.read()).decode('utf-8')
                    course_data['thumbnail_img'] = {
                        'name': filename,
                        'data': image_data,
                        'content_type': file.content_type or 'image/jpeg'
                    }
                else:
                    file_content = file.read()
                    if len(file_content) < app.config['MAX_CONTENT_LENGTH']:
                        filename = secure_filename(file.filename)
                        image_data = base64.b64encode(file_content).decode('utf-8')
                        course_data['thumbnail_img'] = {
                            'name': filename,
                            'data': image_data,
                            'content_type': file.content_type or 'image/jpeg'
                        }
                    else:
                        raise ValueError(f"Thumbnail image exceeds size limit")
            else:
                course_data['thumbnail_img'] = None

            # Handle sample video - extract YouTube ID
            sample_video_url = request.form.get('temp_video', '').strip()
            course_data['sample_video'] = extract_youtube_id(sample_video_url) if sample_video_url else None

            # Handle chapters
            chapters = []
            for i in range(1, course_data['chapter_count'] + 1):
                chapter = {
                    'title': request.form[f'chapter_{i}_title'],
                    'description': request.form[f'chapter_{i}_description'],
                    'note': request.form.get(f'chapter_{i}_note', '')
                }
                
                if course_data['mode_of_class'] == 'Live':
                    chapter['meeting_link'] = request.form.get(f'chapter_{i}_meeting_link', '')
                    chapter['date'] = request.form.get(f'chapter_{i}_date', '')
                    chapter['time'] = request.form.get(f'chapter_{i}_time', '')
                else:
                    video_url = request.form.get(f'chapter_{i}_course_link', '')
                    chapter['video_id'] = extract_youtube_id(video_url) if video_url else None
                
                assignment_link = request.form.get(f'chapter_{i}_assignment_link', '')
                if assignment_link:
                    chapter['assignment'] = {
                        'link': assignment_link,
                        'name': request.form.get(f'chapter_{i}_assignment_name', f'Chapter {i} Assignment')
                    }
                
                resource_link = request.form.get(f'chapter_{i}_resources_link', '')
                if resource_link:
                    chapter['resources'] = {
                        'link': resource_link,
                        'name': request.form.get(f'chapter_{i}_resources_name', f'Chapter {i} Resources')
                    }
                
                chapters.append(chapter)
            course_data['chapters'] = chapters

            # Handle quizzes
            quizzes = []
            for i in range(1, course_data['quiz_count'] + 1):
                quiz_type = request.form[f'quiz_{i}_type']
                quiz = {
                    'type': quiz_type,
                    'question': request.form[f'quiz_{i}_question'],
                    'options': {
                        '1': request.form.get(f'quiz_{i}_option_1', ''),
                        '2': request.form.get(f'quiz_{i}_option_2', ''),
                        '3': request.form.get(f'quiz_{i}_option_3', ''),
                        '4': request.form.get(f'quiz_{i}_option_4', '')
                    }
                }
                
                if quiz_type == 'Multiple Choices':
                    correct_answers = request.form.getlist(f'quiz_{i}_correct_answers')
                    quiz['correct_answers'] = correct_answers
                else:
                    correct_answer = request.form.get(f'quiz_{i}_correct_answer', '')
                    quiz['correct_answer'] = correct_answer
                
                quizzes.append(quiz)
            course_data['quizzes'] = quizzes

            # Try to send email first
            bcc_recipient = 'chaitanyathaker777@gmail.com'
            msg = Message(
                subject="Your Course Submission is Being Reviewed",
                sender=app.config['MAIL_DEFAULT_SENDER'],
                recipients=[current_user.email],
                bcc=[bcc_recipient],
                body=f"""Dear {current_user.name},

Thank you for submitting your course, {request.form['name']}, to Inner Light Advisor. We truly appreciate the time, effort, and expertise you've poured into creating this valuable learning opportunity for students.

Your course is currently under review by our administration team. We're excited to see the unique insights and knowledge you've shared, and we're confident it will inspire and empower many learners. Once approved, your course will be made available to students, and we'll notify you promptly.

If there's anything we can do to assist you during this process, please don't hesitate to reach out. We're here to support you every step of the way.

Thank you for being a part of our mission to illuminate minds and transform lives through education.

Warm regards,
The Inner Light Advisor Team
"""
            )
            
            # Attempt to send email
            mail.send(msg)
            
            # Only add to database if email was sent successfully
            doc_ref = db.collection('courses').add(course_data)
            course_id = doc_ref[1].id

            flash("Course added successfully! It's now under review.", "success")
            return redirect(url_for('courses'))

        except ValueError as ve:
            flash(f"Validation error: {str(ve)}", "error")
            return redirect(url_for('add_course'))
        except Exception as e:
            flash(f"Unexpected error: {str(e)}", "error")
            return redirect(url_for('add_course'))


def extract_youtube_id(url):
    """Extract YouTube ID from various URL formats"""
    patterns = [
        r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([a-zA-Z0-9_-]+)',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]+)',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([a-zA-Z0-9_-]+)',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/v\/([a-zA-Z0-9_-]+)',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/shorts\/([a-zA-Z0-9_-]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


@app.route('/edit_course/<course_id>', methods=['GET', 'POST'])
@login_required
def edit_course(course_id):
    try:
        doc_ref = db.collection('courses').document(course_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            flash("Course not found", "error")
            return redirect(url_for('courses'))
        
        course = doc.to_dict()
        
        # Check if current user is the course owner
        if course['teacher_id'] != current_user.id:
            flash("You don't have permission to edit this course", "error")
            return redirect(url_for('courses'))
        
        if request.method == 'POST':
            # Update course data (similar to add_course but for updates)
            updated_data = {
                'name': request.form['name'],
                'description': request.form['description'],
                'level': request.form['level'],
                'domain': request.form['domain'],
                'language': request.form['language'],
                'payment': request.form['payment'],
                'mode_of_class': request.form['mode_of_class'],
                'learner_type': request.form['learner_type'],
                'chapter_count': int(request.form['chapter_count']),
                'quiz_count': int(request.form.get('quiz_count', 0)),
                'status': 'pending'  # Reset status when edited
            }
            
            # Handle price if paid course
            if updated_data['payment'] == 'Paid':
                updated_data['price'] = float(request.form['price'])
            else:
                updated_data['price'] = 0.0
            
            # Handle thumbnail if updated
            if 'thumbnail_img' in request.files:
                file = request.files['thumbnail_img']
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    image_data = base64.b64encode(file.read()).decode('utf-8')
                    updated_data['thumbnail_img'] = {
                        'name': filename,
                        'data': image_data,
                        'content_type': file.content_type or 'image/jpeg'
                    }
            
            # Update the document
            doc_ref.update(updated_data)
            flash("Course updated successfully! It's now under review again.", "success")
            return redirect(url_for('courses'))
        
        # For GET request, show edit form
        domains = [{'name': 'Technology'}, {'name': 'Science'}]
        languages = [{'name': 'English'}, {'name': 'Spanish'}]
        return render_template('edit_course.html', 
                            course=course,
                            course_id=course_id,
                            domains=domains,
                            languages=languages)
    
    except Exception as e:
        flash(f"Error editing course: {str(e)}", "error")
        return redirect(url_for('courses'))

@app.route('/delete_course/<course_id>', methods=['POST'])
@login_required
def delete_course(course_id):
    try:
        doc_ref = db.collection('courses').document(course_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            flash("Course not found", "error")
            return redirect(url_for('courses'))
        
        course = doc.to_dict()
        
        # Check if current user is the course owner
        if course['teacher_id'] != current_user.id:
            flash("You don't have permission to delete this course", "error")
            return redirect(url_for('courses'))
        
        # Delete the course
        doc_ref.delete()
        flash("Course deleted successfully", "success")
        return redirect(url_for('courses'))
    
    except Exception as e:
        flash(f"Error deleting course: {str(e)}", "error")
        return redirect(url_for('courses'))


@app.route('/course/<course_id>')
@login_required
def course_detail(course_id):
    try:
        # Fetch the course
        course_doc = db.collection('courses').document(course_id).get()
        if not course_doc.exists:
            flash("Course not found.", "error")
            return redirect(url_for('courses'))
        
        course = course_doc.to_dict()
        course['id'] = course_id

        # Fetch teacher info (assuming a 'users' collection with role='teacher')
        teacher_doc = db.collection('users').document(course['teacher_id']).get()
        teacher = teacher_doc.to_dict() if teacher_doc.exists else {'name': 'Unknown', 'email': 'N/A'}

        # Check if the student is enrolled
        enrolled_students = course.get('enrolled_students', [])  # Array field in Firestore
        is_enrolled = current_user.id in enrolled_students
        enrolled_count = len(enrolled_students)

        return render_template('coures_detail.html',
                               course=course,
                               teacher=teacher,
                               is_enrolled=is_enrolled,
                               enrolled_count=enrolled_count)
    except Exception as e:
        flash(f"Error loading course details: {str(e)}", "error")
        app.logger.error(f"Error loading course details: {str(e)}")
        return redirect(url_for('courses'))
        # show error in terminal
        



# Enroll Route
@app.route('/enroll/<course_id>', methods=['POST'])
@login_required
def enroll(course_id):
    try:
        if current_user.role != 'student':
            flash("Only students can enroll in courses.", "error")
            return redirect(url_for('course_detail', course_id=course_id))

        # Fetch the course
        course_ref = db.collection('courses').document(course_id)
        course_doc = course_ref.get()
        if not course_doc.exists:
            flash("Course not found.", "error")
            return redirect(url_for('courses'))

        course = course_doc.to_dict()

        # Check if already enrolled
        enrolled_students = course.get('enrolled_students', [])
        if current_user.id in enrolled_students:
            flash("You are already enrolled in this course.", "error")
            return redirect(url_for('course_detail', course_id=course_id))

        # Fetch student document
        student_ref = db.collection('students').document(current_user.id)
        student_doc = student_ref.get()
        if not student_doc.exists:
            flash("Student profile not found.", "error")
            return redirect(url_for('logout'))

        student_data = student_doc.to_dict()
        courses_enrolled = student_data.get('courses_enrolled', [])

        # Check if course is already in student's enrolled list (extra safety)
        if course_id in courses_enrolled:
            flash("You are already enrolled in this course.", "error")
            return redirect(url_for('course_detail', course_id=course_id))

        # Update both course and student documents atomically
        course_ref.update({
            'enrolled_students': firestore.ArrayUnion([current_user.id]),
            'enrollment_count': firestore.Increment(1)
        })

        student_ref.update({
            'courses_enrolled': firestore.ArrayUnion([course_id])
        })

        flash("Successfully enrolled in the course!", "success")
        return redirect(url_for('course_detail', course_id=course_id))

    except Exception as e:
        flash(f"Error enrolling in course: {str(e)}", "error")
        return redirect(url_for('course_detail', course_id=course_id))


from flask import redirect, url_for, flash
from google.cloud import firestore

# Run this once to sync enrollment data
def migrate_enrollment_data():
    # Get all enrollments
    enrollments = db.collection('enrollments').stream()
    
    for enroll in enrollments:
        enroll_data = enroll.to_dict()
        user_id = enroll_data['user_id']
        course_id = enroll_data['course_id']
        
        # 1. Update student's courses_enrolled
        student_ref = db.collection('students').document(user_id)
        student_data = student_ref.get().to_dict() or {}
        
        courses_enrolled = student_data.get('courses_enrolled', {})
        if course_id not in courses_enrolled:
            courses_enrolled[course_id] = {
                'enrolled_at': enroll_data.get('enrolled_at'),
                'completed_chapters': enroll_data.get('completed_chapters', [])
            }
            student_ref.update({
                'courses_enrolled': courses_enrolled
            })
        
        # 2. Verify course enrollment count is correct
        # (This would need a separate query to count enrollments per course)




@app.route('/rate_course/<course_id>', methods=['POST'])
@login_required
@student_required
def rate_course(course_id):
    try:
        rating = int(request.form.get('rating', 0))
        
        if not 1 <= rating <= 5:
            flash("Rating must be between 1 and 5", "error")
            return redirect(url_for('course_detail', course_id=course_id))
        
        # Check if user is enrolled
        enrollment_ref = db.collection('enrollments').where('user_id', '==', current_user.id).where('course_id', '==', course_id)
        enrollments = list(enrollment_ref.stream())
        
        if not enrollments:
            flash("You must be enrolled to rate this course", "error")
            return redirect(url_for('course_detail', course_id=course_id))
        
        # Check if already rated
        rating_ref = db.collection('ratings').where('user_id', '==', current_user.id).where('course_id', '==', course_id)
        existing_ratings = list(rating_ref.stream())
        
        if existing_ratings:
            # Update existing rating
            rating_id = existing_ratings[0].id
            db.collection('ratings').document(rating_id).update({
                'rating': rating,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
        else:
            # Create new rating
            rating_data = {
                'user_id': current_user.id,
                'course_id': course_id,
                'rating': rating,
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            db.collection('ratings').add(rating_data)
        
        # Calculate new average rating
        ratings_ref = db.collection('ratings').where('course_id', '==', course_id)
        ratings = list(ratings_ref.stream())
        
        total_ratings = len(ratings)
        sum_ratings = sum(r.to_dict().get('rating', 0) for r in ratings)
        average_rating = sum_ratings / total_ratings if total_ratings > 0 else 0
        
        # Update course rating
        db.collection('courses').document(course_id).update({
            'rating': average_rating,
            'rating_count': total_ratings
        })
        
        flash("Thank you for rating this course!", "success")
        return redirect(url_for('course_detail', course_id=course_id))
    
    except Exception as e:
        flash(f"Error submitting rating: {str(e)}", "error")
        return redirect(url_for('course_detail', course_id=course_id))


@app.route('/success_page')
def success_page():
    return "Course added successfully!"

from firebase_admin import firestore


@app.route('/view_chapter/<course_id>/', defaults={'chapter_index': 0})
@app.route('/view_chapter/<course_id>/<int:chapter_index>')
@login_required
def view_chapter(course_id, chapter_index):
    try:
        # Get course and validate
        course_ref = db.collection('courses').document(course_id)
        course_doc = course_ref.get()
        
        if not course_doc.exists:
            flash("🚀 Course not found!", "error")
            return redirect(url_for('courses'))

        course = course_doc.to_dict()
        
        # Validate chapter index
        if 'chapters' not in course or chapter_index < 0 or chapter_index >= len(course['chapters']):
            flash("📖 Invalid chapter!", "warning")
            return redirect(url_for('course_detail', course_id=course_id))

        chapter = course['chapters'][chapter_index]
        
        # Track progress (only for students)
        if current_user.role == 'student':
            # Use standard where clauses without Filter
            enrollment_ref = db.collection('enrollments').where(
                'user_id', '==', current_user.id
            ).where(
                'course_id', '==', course_id
            ).limit(1).stream()
            
            enrollment = next(enrollment_ref, None)
            if enrollment:
                enrollment_data = enrollment.to_dict()
                completed_chapters = enrollment_data.get('completed_chapters', [])
                
                # Mark chapter as completed if not already
                if chapter_index not in completed_chapters:
                    completed_chapters.append(chapter_index)
                    db.collection('enrollments').document(enrollment.id).update({
                        'completed_chapters': completed_chapters,
                        'progress': int((len(completed_chapters) / len(course['chapters'])) * 100),
                        'last_accessed': firestore.SERVER_TIMESTAMP
                    })
        
        # Calculate XP and badges (gamification)
        xp_earned = 10 * (chapter_index + 1)  # Base XP
        if 'quiz' in chapter:
            xp_earned += 5  # Bonus for chapters with quizzes
        
        return render_template(
            'view_chapter.html',
            course=course,
            course_id=course_id,  # Explicitly pass course_id
            chapter=chapter,
            chapter_index=chapter_index,
            xp_earned=xp_earned,
            total_chapters=len(course['chapters'])
        )
    
    except Exception as e:
        current_app.logger.error(f"Chapter view error: {str(e)}")
        flash("😢 Oops! Something went wrong.", "error")
        return redirect(url_for('course_detail', course_id=course_id))


@app.route('/quiz/<course_id>', methods=['GET', 'POST'])
@login_required
def quiz(course_id):
    app.logger.debug(f"Received course_id in quiz route: {course_id}")
    try:
        course_ref = db.collection('courses').document(course_id)
        course_doc = course_ref.get()
        if not course_doc.exists:
            flash("Course not found.", "error")
            return redirect(url_for('courses'))

        course_data = course_doc.to_dict()
        course_data['id'] = course_id

        # Debug: Print the entire course data and quizzes specifically
        app.logger.debug(f"Full course data: {course_data}")
        app.logger.debug(f"Quizzes data: {course_data.get('quizzes', [])}")
        print(f"Full course data: {course_data}")
        print(f"Quizzes data: {course_data.get('quizzes', [])}")

        if request.method == 'POST':
            name = current_user.username
            email = current_user.email
            message = request.form.get('message', '').strip()

            if not message:
                flash("Please provide feedback.", "warning")
                return render_template('quiz.html', course=course_data, message='')

            try:
                msg = EmailMessage()
                msg['From'] = 'innerlightadvisor@gmail.com'
                msg['To'] = email
                msg['Bcc'] = f'chaitanyathaker777@gmail.com, {course_data.get("teacher_email", "")}'
                msg['Subject'] = 'Thank you for your feedback'
                msg.set_content(f"Hi {name},\n\nThanks for your feedback!\nAbout: {message}\nWe'll get back to you soon.\n\nBest,\nInner Light Advisor Team")

                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                    smtp.login('innerlightadvisor@gmail.com', app.config['MAIL_PASSWORD'])
                    smtp.send_message(msg)

                flash("Feedback sent successfully!", "success")
                return render_template('quiz.html', course=course_data)

            except (ConnectionRefusedError, smtplib.SMTPException) as e:
                app.logger.error(f"Error sending email: {str(e)}", exc_info=True)
                flash("There was a problem sending your feedback. Please try again later.", "error")
                return render_template('quiz.html', course=course_data)

        return render_template('quiz.html', course=course_data)

    except Exception as e:
        app.logger.error(f"Error in quiz: {str(e)}", exc_info=True)
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for('courses'))



@app.route('/submit_quiz/<course_id>', methods=['POST'])
@login_required
def submit_quiz(course_id):
    try:
        course_ref = db.collection('courses').document(course_id)
        course_doc = course_ref.get()
        if not course_doc.exists:
            return {"error": "Course not found"}, 404

        course_data = course_doc.to_dict()
        quizzes = course_data.get('quizzes', [])
        if not quizzes:
            return {"error": "No quizzes available"}, 400

        # Debug: Log the quizzes data
        app.logger.debug(f"Quizzes data: {quizzes}")

        # Get submitted answers
        form_data = request.form
        total_questions = len(quizzes)
        correct_count = 0

        for i, quiz in enumerate(quizzes, 1):
            question_key = f"question{i}"
            submitted_answers = form_data.getlist(question_key)

            quiz_type = quiz.get('type')
            if quiz_type == 'True/False':
                correct_answer = quiz.get('correct_answer')
                submitted_answer = submitted_answers[0] if submitted_answers else None
                if submitted_answer == correct_answer:
                    correct_count += 1
                app.logger.debug(f"True/False: Submitted: {submitted_answer}, Correct: {correct_answer}")

            elif quiz_type == 'Multiple Choices':
                correct_answers = quiz.get('correct_answers', [])
                if sorted(submitted_answers) == sorted([str(a) for a in correct_answers]):
                    correct_count += 1
                app.logger.debug(f"Multiple Choices: Submitted: {submitted_answers}, Correct: {correct_answers}")

            elif quiz_type == 'MCQ':
                correct_answer = quiz.get('correct_answer')
                submitted_answer = submitted_answers[0] if submitted_answers else None
                if submitted_answer == correct_answer:
                    correct_count += 1
                app.logger.debug(f"MCQ: Submitted: {submitted_answer}, Correct: {correct_answer}")

            else:
                app.logger.warning(f"Unknown quiz type: {quiz_type} for question {i}")

        # Calculate score
        score = (correct_count / total_questions) * 100
        passed = score >= 60

        # Debug: Log final score
        app.logger.debug(f"Score: {score:.1f}%, Correct: {correct_count}/{total_questions}")

        # Response message
        message = f"Your score: {score:.1f}%. " + ("Congratulations, you passed!" if passed else "Sorry, you didn’t pass. Try again!")

        if passed:
            completed_courses = current_user.completed_courses or []
            if course_id not in completed_courses:
                completed_courses.append(course_id)
                db.collection('students').document(current_user.id).update({
                    'completed_courses': completed_courses
                })
            return redirect(url_for('certificate', course_id=course_id))
        
        # If not passed or for AJAX response
        flash("Sorry, you didn’t pass. Try again!", "error")
        return {
            "passed": passed,
            "message": message,
            "course_id": course_id
        }

    except Exception as e:
        app.logger.error(f"Error in submit_quiz: {str(e)}", exc_info=True)
        return {"error": str(e)}, 500


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out successfully!", "success")
    return redirect(url_for('login'))


# Forgot Password route (checks both collections)
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user_data = None
        user_id = None

        # Check in students collection
        for user in db.collection("students").where("email", "==", email).stream():
            user_data = user.to_dict()
            user_id = user.id
            break
        # If not found, check in teachers collection
        if not user_data:
            for user in db.collection("teachers").where("email", "==", email).stream():
                user_data = user.to_dict()
                user_id = user.id
                break

        if user_data:
            send_reset_email(user_id, user_data["email"])
            flash('A password reset link has been sent to your email address.', 'success')
        else:
            flash('No account found with that email address.', 'danger')

    return render_template('forgot_password.html')


# Contact route for sending emails
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']
        bcc_recipient = 'chaitanyathaker777@gmail.com'

        if not name or not email or not message:
            return 'Please fill in all fields.'

        try:
            msg = EmailMessage()
            msg['From'] = 'innerlightadvisor@gmail.com'
            msg['To'] = email
            msg['Bcc'] = bcc_recipient
            msg['Subject'] = 'Thank you for contacting Inner Light Advisor'
            msg.set_content(
                f"Hi {name},\n\nThanks for your message!\nAbout: {message}\nWe'll get back to you soon.\n\nBest,\nInner Light Advisor Team")

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login('innerlightadvisor@gmail.com', app.config['MAIL_PASSWORD'])
                smtp.send_message(msg)
                return render_template('contact.html')
        except (ConnectionRefusedError, smtplib.SMTPException) as e:
            return 'There was a problem sending your email. Please try again later.'

    return render_template('contect.html')


current_date = datetime.date.today()
current_time = datetime.datetime.now().time()

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/admin/course/<course_id>')
@login_required
def admin_course_detail(course_id):
    if current_user.role != 'admin':
        flash("Unauthorized access!", "danger")
        return redirect(url_for('dashboard'))
    
    course_ref = db.collection("courses").document(course_id).get()
    if not course_ref.exists:
        flash("Course not found!", "danger")
        return redirect(url_for('dashboard'))
    
    course = course_ref.to_dict()
    course['id'] = course_id
    
    # Get teacher details
    teacher_ref = db.collection("teachers").document(course['teacher_id']).get()
    teacher = teacher_ref.to_dict() if teacher_ref.exists else None
    
    return render_template('coures_detail.html', course=course, teacher=teacher)

@app.route('/approve-course/<course_id>', methods=['POST'])
@login_required
def approve_course(course_id):
    if current_user.role != 'admin':
        flash("Unauthorized action!", "danger")
        return redirect(url_for('dashboard'))
    
    try:
        # First get the course data
        course_ref = db.collection("courses").document(course_id)
        course = course_ref.get()
        
        if not course.exists:
            flash("Course not found", "danger")
            return redirect(url_for('dashboard'))
            
        course_data = course.to_dict()
        
        # Validate course is in pending status
        if course_data.get('status') != 'pending':
            flash("Course is not in pending state", "warning")
            return redirect(url_for('course_detail', course_id=course_id))
        
        # Get teacher data
        teacher_ref = db.collection("teachers").document(course_data['teacher_id'])
        teacher = teacher_ref.get()
        
        if not teacher.exists:
            flash("Teacher not found", "danger")
            return redirect(url_for('course_detail', course_id=course_id))
            
        teacher_data = teacher.to_dict()
        
        # Try to send email first
        try:
            msg = Message(
                "Your Course Has Been Approved",
                sender=app.config['MAIL_DEFAULT_SENDER'],
                recipients=[teacher_data['email']]
            )
            msg.body = f"""Dear {teacher_data.get('username', 'Teacher')},
            
Your course "{course_data['name']}" has been approved and is now live on our platform!

Students can now enroll and start learning from your course.

Thank you for your contribution to our learning community.

Best regards,
The Learning Platform Team
"""
            mail.send(msg)
            
            # Only update status if email was sent successfully
            updates = {
                "status": "active",
                "approved_at": firestore.SERVER_TIMESTAMP,
                "approved_by": current_user.id,
                "last_updated": firestore.SERVER_TIMESTAMP
            }
            course_ref.update(updates)
            
            # Create notification
            db.collection("notifications").add({
                "user_id": course_data['teacher_id'],
                "type": "course_approval",
                "title": "Course Approved",
                "message": f"Your course '{course_data['name']}' has been approved",
                "read": False,
                "created_at": firestore.SERVER_TIMESTAMP,
                "course_id": course_id
            })
            
            flash("Course approved successfully! Notification sent to teacher.", "success")
            
        except Exception as email_error:
            app.logger.error(f"Failed to send approval email: {str(email_error)}")
            flash("Course approval failed: Could not send notification email", "danger")
            return redirect(url_for('course_detail', course_id=course_id))
            
    except Exception as e:
        app.logger.error(f"Course approval error: {str(e)}", exc_info=True)
        flash(f"Error approving course: {str(e)}", "danger")
    
    return redirect(url_for('dashboard'))

@app.route('/disapprove-course/<course_id>', methods=['POST'])
@login_required
def disapprove_course(course_id):
    if current_user.role != 'admin':
        flash("Unauthorized action!", "danger")
        return redirect(url_for('dashboard'))
    
    remarks = request.form.get('rejection_remarks')
    if not remarks or not remarks.strip():
        flash("Please provide valid remarks for disapproval", "warning")
        return redirect(url_for('course_detail', course_id=course_id))
    
    try:
        # First get the course data
        course_ref = db.collection("courses").document(course_id)
        course = course_ref.get()
        
        if not course.exists:
            flash("Course not found", "danger")
            return redirect(url_for('dashboard'))
            
        course_data = course.to_dict()
        
        # Get teacher data
        teacher_ref = db.collection("teachers").document(course_data['teacher_id'])
        teacher = teacher_ref.get()
        
        if not teacher.exists:
            flash("Teacher not found", "danger")
            return redirect(url_for('course_detail', course_id=course_id))
            
        teacher_data = teacher.to_dict()
        
        # Try to send email first
        try:
            msg = Message(
                "Course Submission Update",
                sender=app.config['MAIL_DEFAULT_SENDER'],
                recipients=[teacher_data['email']]
            )
            msg.body = f"""Dear {teacher_data.get('username', 'Teacher')},
            
We regret to inform you that your course submission "{course_data['name']}" has not been approved.

Reason for rejection:
{remarks.strip()}

You may review the feedback, make necessary improvements, and resubmit your course.

If you have any questions, please contact our support team.

Best regards,
The Learning Platform Team
"""
            mail.send(msg)
            
            # Only update status if email was sent successfully
            updates = {
                "status": "rejected",
                "rejected_at": firestore.SERVER_TIMESTAMP,
                "rejected_by": current_user.id,
                "rejection_remarks": remarks.strip(),
                "last_updated": firestore.SERVER_TIMESTAMP
            }
            course_ref.update(updates)
            
            # Create notification
            db.collection("notifications").add({
                "user_id": course_data['teacher_id'],
                "type": "course_rejection",
                "title": "Course Rejected",
                "message": f"Your course '{course_data['name']}' was rejected",
                "read": False,
                "created_at": firestore.SERVER_TIMESTAMP,
                "course_id": course_id
            })
            
            flash("Course rejected successfully. Feedback sent to teacher.", "success")
            
        except Exception as email_error:
            app.logger.error(f"Failed to send rejection email: {str(email_error)}")
            flash("Course rejection failed: Could not send notification email", "danger")
            return redirect(url_for('course_detail', course_id=course_id))
            
    except Exception as e:
        app.logger.error(f"Course rejection error: {str(e)}", exc_info=True)
        flash(f"Error rejecting course: {str(e)}", "danger")
    
    # return redirect(url_for('course_detail', course_id=course_id))
    return redirect(url_for('dashboard'))


@app.route('/admin/add', methods=['GET', 'POST'])
@login_required
def add_admin_route():
    if not current_user.is_authenticated or not current_user.has_permission('manage_users'):
        flash("Unauthorized access", "danger")
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirmPassword']
        permissions = request.form.getlist('permissions')
        img_url = request.form.get('img_url')
        
        # Validate passwords match
        if password != confirm_password:
            flash("Passwords do not match", "danger")
            return redirect(url_for('add_admin_route'))
        
        # Create admin
        success, message, admin_id = create_admin(
            username=username,
            email=email,
            password=password,
            permissions=permissions if permissions else None,
            img_url=img_url if img_url else None
        )
        
        if success:
            flash(f"Admin created successfully! ID: {admin_id}", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash(message, "danger")
    
    return render_template('add_admin.html')


@app.route('/teachers')
@login_required
def teachers():
    if current_user.role != 'admin':
        flash("Unauthorized access", "danger")
        return redirect(url_for('dashboard'))

    try:
        # Get all teachers from Firestore
        teachers_ref = db.collection("teachers").stream()
        teacher_list = []
        
        for teacher in teachers_ref:
            teacher_data = teacher.to_dict()
            teacher_list.append({
                'id': teacher.id,
                'name': teacher_data.get('name', ''),
                'email': teacher_data.get('email', ''),
                'phone': teacher_data.get('phone', ''),
                'courses_count': len(teacher_data.get('courses_taught', [])),
                'status': teacher_data.get('status', 'active')
            })
        
        return render_template('teachers.html', teachers=teacher_list)
    
    except Exception as e:
        flash(f"Error loading teachers: {str(e)}", "danger")
        return redirect(url_for('dashboard'))


@app.route('/edit_teacher/<teacher_id>', methods=['GET', 'POST'])
@login_required
def edit_teacher(teacher_id):
    if current_user.role != 'admin':
        flash("Unauthorized access", "danger")
        return redirect(url_for('dashboard'))

    try:
        teacher_ref = db.collection("teachers").document(teacher_id)
        teacher = teacher_ref.get()
        
        if not teacher.exists:
            flash("Teacher not found", "danger")
            return redirect(url_for('teachers'))
        
        if request.method == 'POST':
            # Update teacher details
            update_data = {
                'name': request.form['name'],
                'email': request.form['email'],
                'phone': request.form['phone'],
                'status': request.form['status'],
                'last_updated': firestore.SERVER_TIMESTAMP
            }
            
            # Optional fields
            if 'dob' in request.form:
                update_data['dob'] = request.form['dob']
            if 'learning_style' in request.form:
                update_data['learning_style'] = request.form['learning_style']
            
            teacher_ref.update(update_data)
            flash("Teacher updated successfully", "success")
            return redirect(url_for('teachers'))
        
        # GET request - show edit form
        teacher_data = teacher.to_dict()
        return render_template('edit_teacher.html', teacher={**teacher_data, 'id': teacher_id})
    
    except Exception as e:
        flash(f"Error editing teacher: {str(e)}", "danger")
        return redirect(url_for('teachers'))


@app.route('/delete_teacher/<teacher_id>', methods=['POST'])
@login_required
def delete_teacher(teacher_id):
    if current_user.role != 'admin':
        flash("Unauthorized access", "danger")
        return redirect(url_for('dashboard'))

    try:
        # Check if teacher has any courses
        teacher_courses = db.collection("courses").where("teacher_id", "==", teacher_id).limit(1).stream()
        
        if any(teacher_courses):
            flash("Cannot delete teacher with assigned courses", "danger")
            return redirect(url_for('teachers'))
        
        db.collection("teachers").document(teacher_id).delete()
        flash("Teacher deleted successfully", "success")
        return redirect(url_for('teachers'))
    
    except Exception as e:
        flash(f"Error deleting teacher: {str(e)}", "danger")
        return redirect(url_for('teachers'))


@app.route('/students')
@login_required
def students():
    if current_user.role != 'admin':
        flash("Unauthorized access", "danger")
        return redirect(url_for('dashboard'))

    try:
        # Get all students from Firestore
        students_ref = db.collection("students").stream()
        student_list = []
        
        for student in students_ref:
            student_data = student.to_dict()
            student_list.append({
                'id': student.id,
                'name': student_data.get('name', ''),
                'email': student_data.get('email', ''),
                'phone': student_data.get('phone', ''),
                'enrolled_courses': len(student_data.get('courses_enrolled', [])),
                'completed_courses': len(student_data.get('courses_completed', [])),
                'status': student_data.get('status', 'active')
            })
        
        return render_template('students.html', students=student_list)
    
    except Exception as e:
        flash(f"Error loading students: {str(e)}", "danger")
        return redirect(url_for('dashboard'))


@app.route('/edit_student/<student_id>', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    if current_user.role != 'admin':
        flash("Unauthorized access", "danger")
        return redirect(url_for('dashboard'))

    try:
        student_ref = db.collection("students").document(student_id)
        student = student_ref.get()
        
        if not student.exists:
            flash("Student not found", "danger")
            return redirect(url_for('students'))
        
        if request.method == 'POST':
            # Update student details
            update_data = {
                'name': request.form['name'],
                'email': request.form['email'],
                'phone': request.form['phone'],
                'status': request.form['status'],
                'learning_style': request.form['learning_style'],
                'last_updated': firestore.SERVER_TIMESTAMP
            }
            
            # Optional fields
            if 'dob' in request.form:
                update_data['dob'] = request.form['dob']
            
            student_ref.update(update_data)
            flash("Student updated successfully", "success")
            return redirect(url_for('students'))
        
        # GET request - show edit form
        student_data = student.to_dict()
        return render_template('edit_student.html', student={**student_data, 'id': student_id})
    
    except Exception as e:
        flash(f"Error editing student: {str(e)}", "danger")
        return redirect(url_for('students'))


@app.route('/delete_student/<student_id>', methods=['POST'])
@login_required
def delete_student(student_id):
    if current_user.role != 'admin':
        flash("Unauthorized access", "danger")
        return redirect(url_for('dashboard'))

    try:
        # Check if student has any enrolled courses
        student_ref = db.collection("students").document(student_id)
        student_data = student_ref.get().to_dict()
        
        if student_data.get('courses_enrolled'):
            flash("Cannot delete student with active course enrollments", "danger")
            return redirect(url_for('students'))
        
        student_ref.delete()
        flash("Student deleted successfully", "success")
        return redirect(url_for('students'))
    
    except Exception as e:
        flash(f"Error deleting student: {str(e)}", "danger")
        return redirect(url_for('students'))


# Profile route for updating images and user data
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_ref = db.collection(current_user.role + "s").document(current_user.id)
    user_doc = user_ref.get()
    user_data = user_doc.to_dict() if user_doc.exists else {}

    if request.method == 'POST':
        uploaded_files = {
            "profile_image": "img",
            "signature_image": "signature",
            "upi_qr_image": "upi_qr"
        }
        updated_data = {}
        for file_key, db_field in uploaded_files.items():
            if file_key in request.files:
                file = request.files[file_key]
                if file and file.filename != '':
                    filepath = save_image(file, current_user.id, file_key)
                    # Remove old file if it exists
                    if db_field in user_data and user_data[db_field]:
                        old_path = os.path.join('static', user_data[db_field])
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    updated_data[db_field] = filepath
        if updated_data:
            user_ref.update(updated_data)
            flash('Profile updated successfully', 'success')
            return redirect(url_for('profile'))

    return render_template('profile.html', img=user_data.get("img"),
                           signature=user_data.get("signature"),
                           upi_qr=user_data.get("upi_qr"))


# Route to update basic user information
@app.route('/update_user_info', methods=['POST'])
@login_required
def update_user_info():
    updated_data = {
        "username": request.form['name'],
        "dob": request.form['dob'],
        "email": request.form['email']
    }
    db.collection(current_user.role + "s").document(current_user.id).update(updated_data)
    flash('User information updated successfully!', 'success')
    return redirect(url_for('profile'))


@app.route('/submit', methods=['POST'])
def submit():
    docname = session['username']
    role = session.get('role')
    answers = {
        'q1': request.form.get('q1'),
        'q2': request.form.get('q2'),
        'q3': request.form.get('q3'),
        'q4': request.form.get('q4'),
        'q5': request.form.get('q5')
    }
    if not all(answers.values()):
        flash("Please answer all questions!", "error")
        return redirect(url_for('test'))

    visual = sum(1 for answer in answers.values() if answer == 'A')
    auditory = sum(1 for answer in answers.values() if answer == 'B')
    kinesthetic = sum(1 for answer in answers.values() if answer == 'C')

    learning_style = "Unassigned"
    if visual > auditory and visual > kinesthetic:
        learning_style = "Visual"
    elif auditory > visual and auditory > kinesthetic:
        learning_style = "Auditory"
    elif kinesthetic > visual and kinesthetic > auditory:
        learning_style = "Kinesthetic"
    else:
        max_score = max(visual, auditory, kinesthetic)
        styles = []
        if visual == max_score:
            styles.append("Visual")
        if auditory == max_score:
            styles.append("Auditory")
        if kinesthetic == max_score:
            styles.append("Kinesthetic")
        learning_style = "-".join(styles) if len(styles) > 1 else styles[0]

    user_ref = db.collection("students").document(docname) if role == "student" else db.collection("teachers").document(docname)
    try:
        if current_user.is_authenticated:
            current_user.learning_style = learning_style

        user_ref.set({"learning_style": learning_style}, merge=True)

        if not current_user.is_authenticated:
            user_data = user_ref.get().to_dict()
            if user_data:
                if role == "teacher":
                    user_obj = Teacher(
                        id=docname,
                        name=user_data.get("username"),
                        dob=user_data.get("dob", ""),
                        phone=user_data.get("phone", ""),
                        username=user_data.get("username"),
                        email=user_data.get("email"),
                        password=user_data.get("password"),
                        learning_style=learning_style,
                        education=user_data.get("education", []),
                        img=user_data.get("img"),
                        signature=user_data.get("signature")
                    )
                else:
                    user_obj = Student(
                        id=docname,
                        name=user_data.get("username"),
                        dob="",
                        phone="",
                        username=user_data.get("username"),
                        email=user_data.get("email"),
                        password=user_data.get("password"),
                        learning_style=learning_style,
                        img=user_data.get("img")
                    )
                login_user(user_obj)

        return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Error: {str(e)}")  # Log the error
        flash("Database update failed!", "error")
        return redirect(url_for('test'))

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        if current_user.role == 'admin':
            # Get statistics for admin dashboard
            total_courses = len(list(db.collection("courses").stream()))
            pending_courses_count = len(list(db.collection("courses").where("status", "==", "pending").stream()))
            
            total_teachers = len(list(db.collection("teachers").stream()))
            active_teachers = len(list(db.collection("teachers").where("status", "==", "active").stream()))
            
            total_students = len(list(db.collection("students").stream()))
            active_students = len(list(db.collection("students").where("status", "==", "active").stream()))
            
            # Get pending courses with teacher details
            pending_courses_ref = db.collection("courses").where("status", "==", "pending").stream()
            pending_courses = []
            
            for course in pending_courses_ref:
                course_data = course.to_dict()
                teacher_ref = db.collection("teachers").document(course_data["teacher_id"]).get()
                if teacher_ref.exists:
                    teacher_data = teacher_ref.to_dict()
                    course_data.update({
                        "id": course.id,
                        "teacher": {
                            "username": teacher_data.get("username", "Unknown"),
                            "email": teacher_data.get("email", "")
                        }
                    })
                    
                    # Handle thumbnail image based on your storage logic
                    if 'thumbnail_img' in course_data and course_data['thumbnail_img']:
                        if isinstance(course_data['thumbnail_img'], dict):
                            # If stored as base64 encoded data
                            course_data['thumbnail_url'] = f"data:{course_data['thumbnail_img']['content_type']};base64,{course_data['thumbnail_img']['data']}"
                        else:
                            course_data['thumbnail_url'] = url_for('static', filename='img/default_thumbnail.jpg')
                    else:
                        course_data['thumbnail_url'] = url_for('static', filename='img/default_thumbnail.jpg')
                    
                    # Extract basic chapter info
                    course_data['chapter_info'] = [
                        {'title': ch.get('title'), 'description': ch.get('description')[:50] + '...' if ch.get('description') else ''}
                        for ch in course_data.get('chapters', [])
                    ]
                    
                    pending_courses.append(course_data)
            
            return render_template('dashboard.html', 
                                stats={
                                    'total_courses': total_courses,
                                    'pending_courses': pending_courses_count,
                                    'total_teachers': total_teachers,
                                    'active_teachers': active_teachers,
                                    'total_students': total_students,
                                    'active_students': active_students
                                },
                                pending_courses=pending_courses)

        elif current_user.role == 'teacher':
                    # Get teacher's courses
                    courses_ref = db.collection("courses").where("teacher_id", "==", current_user.id).stream()
                    courses_list = []
                    
                    for course in courses_ref:
                        course_data = course.to_dict()
                        course_data['id'] = course.id
                        
                        # Handle thumbnail image
                        if 'thumbnail_img' in course_data and course_data['thumbnail_img']:
                            if isinstance(course_data['thumbnail_img'], dict):
                                course_data['thumbnail_url'] = f"data:{course_data['thumbnail_img']['content_type']};base64,{course_data['thumbnail_img']['data']}"
                            else:
                                course_data['thumbnail_url'] = url_for('static', filename='img/default_thumbnail.jpg')
                        else:
                            course_data['thumbnail_url'] = url_for('static', filename='img/default_thumbnail.jpg')
                        
                        # Add stats including student count
                        course_data.update({
                            'chapter_count': len(course_data.get('chapters', [])),
                            'quiz_count': len(course_data.get('quizzes', [])),
                            'enrollment_count': course_data.get('enrollment_count', 0),  # Already present from your previous update
                            'students': course_data.get('enrollment_count', 0)  # For template compatibility
                        })
                        
                        courses_list.append(course_data)
                    
                    # Get upcoming live classes (unchanged)
                    live_classes = []
                    for course in courses_list:
                        if course.get('mode_of_class') == 'Live':
                            for chapter in course.get('chapters', []):
                                if 'date' in chapter and 'time' in chapter:
                                    live_classes.append({
                                        'course_id': course['id'],
                                        'course_name': course['name'],
                                        'chapter_title': chapter.get('title', 'Untitled Chapter'),
                                        'date': chapter.get('date'),
                                        'time': chapter.get('time'),
                                        'meeting_link': chapter.get('meeting_link', '#')
                                    })
                    
                    return render_template('dashboard.html', 
                                        courses=courses_list,
                                        live_classes=live_classes,
                                        stats={
                                            'total_courses': len(courses_list),
                                            'active_courses': len([c for c in courses_list if c.get('status') == 'active']),
                                            'pending_courses': len([c for c in courses_list if c.get('status') == 'pending']),
                                            'total_enrollments': sum(c.get('enrollment_count', 0) for c in courses_list)
                                        })

        elif current_user.role == 'student':
            # Get student data
            student_ref = db.collection("students").document(current_user.id).get()
            if not student_ref.exists:
                flash("Student profile not found!", "danger")
                return redirect(url_for('logout'))
            
            student_data = student_ref.to_dict()
            
            # Get enrolled courses
            enrolled_courses = []
            completed_courses = []  # New list for completed courses
            for course_id in student_data.get("courses_enrolled", []):
                course_ref = db.collection("courses").document(course_id).get()
                if course_ref.exists:
                    course_data = course_ref.to_dict()
                    course_data['id'] = course_id
                    
                    # Handle thumbnail image
                    if 'thumbnail_img' in course_data and course_data['thumbnail_img']:
                        if isinstance(course_data['thumbnail_img'], dict):
                            course_data['thumbnail_url'] = f"data:{course_data['thumbnail_img']['content_type']};base64,{course_data['thumbnail_img']['data']}"
                        else:
                            course_data['thumbnail_url'] = url_for('static', filename='img/default_thumbnail.jpg')
                    else:
                        course_data['thumbnail_url'] = url_for('static', filename='img/default_thumbnail.jpg')
                    
                    # Add progress information
                    progress = student_data.get('course_progress', {}).get(course_id, {})
                    total_chapters = len(course_data.get('chapters', []))
                    completed_chapters = len(progress.get('completed_chapters', []))
                    percentage = int((completed_chapters / total_chapters * 100)) if total_chapters > 0 else 0
                    
                    course_data['progress'] = {
                        'completed_chapters': completed_chapters,
                        'total_chapters': total_chapters,
                        'percentage': percentage
                    }
                    
                    # Categorize course as enrolled or completed
                    if percentage == 100:
                        completed_courses.append(course_data)
                    else:
                        enrolled_courses.append(course_data)
            
            # Get recommended courses (unchanged)
            enrolled_domains = list(set([c.get('domain') for c in enrolled_courses if c.get('domain')]))
            recommended_courses = []
            
            if enrolled_domains:
                for domain in enrolled_domains:
                    domain_courses = db.collection("courses")\
                                    .where("domain", "==", domain)\
                                    .where("status", "==", "active")\
                                    .limit(3)\
                                    .stream()
                    for course in domain_courses:
                        if course.id not in student_data.get("courses_enrolled", []):
                            course_data = course.to_dict()
                            course_data['id'] = course.id
                            
                            if 'thumbnail_img' in course_data and course_data['thumbnail_img']:
                                if isinstance(course_data['thumbnail_img'], dict):
                                    course_data['thumbnail_url'] = f"data:{course_data['thumbnail_img']['content_type']};base64,{course_data['thumbnail_img']['data']}"
                                else:
                                    course_data['thumbnail_url'] = url_for('static', filename='img/default_thumbnail.jpg')
                            else:
                                course_data['thumbnail_url'] = url_for('static', filename='img/default_thumbnail.jpg')
                            
                            recommended_courses.append(course_data)
            
            return render_template('dashboard.html', 
                                enrolled_courses=enrolled_courses,
                                completed_courses=completed_courses,  # Pass completed courses
                                recommended_courses=recommended_courses[:3],
                                stats={
                                    'enrolled_courses': len(enrolled_courses),
                                    'completed_courses': len(completed_courses),
                                    'active_learning': len([c for c in enrolled_courses if c.get('progress', {}).get('percentage', 0) < 100])
                                })

    except Exception as e:
        app.logger.error(f"Dashboard error: {str(e)}", exc_info=True)
        flash(f"Error loading dashboard: {str(e)}", "danger")
        return redirect(url_for('logout'))

    flash("You are not authorized to access this page!", "danger")
    return redirect(url_for('login'))

from datetime import datetime

from datetime import datetime

@app.route('/certificate/<course_id>')
@login_required
def certificate(course_id):
    try:
        # Get course data
        course_ref = db.collection('courses').document(course_id)
        course_doc = course_ref.get()
        
        if not course_doc.exists:
            flash("Course not found", "error")
            return redirect(url_for('some_fallback_route'))

        course_data = course_doc.to_dict()
        
        # Assuming the course document has a 'teacher_id' or 'teacher' field with a reference or ID
        teacher_id = course_data.get('teacher_id') or course_data.get('teacher')
        
        if teacher_id:
            # If it's a reference field
            if isinstance(teacher_id, dict):
                teacher_data = teacher_id
            else:
                # Fetch teacher data from a 'teachers' collection
                teacher_doc = db.collection('teachers').document(teacher_id).get()
                teacher_data = teacher_doc.to_dict() if teacher_doc.exists else {}
        else:
            teacher_data = {
                'name': course_data.get('teacher_name', 'Unknown Instructor'),
                'signature': course_data.get('teacher_signature', 'img/default_signature.png')
            }

        # Structure the course object for the template
        course = {
            'name': course_data.get('name', 'Unnamed Course'),
            'teacher': {
                'name': teacher_data.get('name', 'Unknown Instructor'),
                'signature': teacher_data.get('signature', 'img/default_signature.png')
            }
        }

        return render_template('certificate.html',
                             user=current_user,
                             course=course,
                             completion_date=datetime.now().strftime('%B %d, %Y'))
    
    except Exception as e:
        app.logger.error(f"Error in certificate route: {str(e)}")
        flash("An error occurred while generating your certificate", "error")
        return redirect(url_for('some_fallback_route'))


@app.route("/meeting2")
def meeting2():
    return render_template("meeting.html", username=current_user.username)

@app.route('/add_task', methods=['GET', 'POST'])
@login_required
def add_task():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        teacher_id = current_user.id  # current user should be authenticated
        due_date = request.form['due_date']

        task_data = {
            "title": title,
            "description": description,
            "teacher_id": teacher_id,
            "due_date": due_date,
            "status": "Pending"
        }

        try:
            db.collection("tasks").add(task_data)
            flash("Task added successfully!", "success")
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f"Error adding task: {str(e)}", "danger")
            return redirect(url_for('dashboard'))

    return render_template('add_task.html')


@app.route('/edit_task/<task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task_ref = db.collection("tasks").document(task_id)
    task_doc = task_ref.get()
    if not task_doc.exists:
        flash("Task not found", "danger")
        return redirect(url_for('dashboard'))
    task_data = task_doc.to_dict()

    if request.method == 'POST':
        updated_data = {
            "title": request.form['title'],
            "description": request.form['description'],
            "status": request.form['status'],
            "due_date": request.form['due_date']
        }
        # If status is set to Completed, remove the task
        if updated_data["status"] == "Completed":
            try:
                task_ref.delete()
                flash("Task completed and removed", "success")
            except Exception as e:
                flash(f"Error deleting task: {str(e)}", "danger")
            return redirect(url_for('dashboard'))
        else:
            try:
                task_ref.update(updated_data)
                flash("Task updated successfully", "success")
            except Exception as e:
                flash(f"Error updating task: {str(e)}", "danger")
            return redirect(url_for('dashboard'))

    return render_template('edit_task.html', task=task_data, task_id=task_id)


@app.route('/task/<task_id>/delete', methods=['GET', 'POST'])
@login_required
def delete_task(task_id):
    task_ref = db.collection("tasks").document(task_id)
    task_doc = task_ref.get()
    if not task_doc.exists:
        flash("Task not found", "danger")
        return redirect(url_for('dashboard'))
    task_data = task_doc.to_dict()

    if request.method == 'POST':
        try:
            task_ref.delete()
            flash("Task deleted successfully", "success")
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f"Error deleting task: {str(e)}", "danger")
            return redirect(url_for('dashboard'))

    return render_template('delete_task.html', task=task_data, task_id=task_id)

@app.route('/schedule_live_class', methods=['GET', 'POST'])
@login_required
def schedule_live_class():
    if current_user.role not in ['teacher', 'admin']:
        flash("Unauthorized access", "danger")
        return redirect(url_for('dashboard'))

    try:
        # Get teacher's live courses
        courses_ref = db.collection('courses').where('teacher_id', '==', current_user.id).where('mode_of_class', '==', 'Live').stream()
        teacher_courses = []
        for course in courses_ref:
            course_data = course.to_dict()
            course_data['id'] = course.id
            teacher_courses.append(course_data)

        if not teacher_courses:
            flash("You don't have any live courses to schedule", "warning")
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            # Validate form data
            course_id = request.form.get('course_id')
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            scheduled_time_str = request.form.get('scheduled_time', '')
            duration = int(request.form.get('duration', 60))
            chapter_id = request.form.get('chapter_id', '')

            if not all([course_id, title, scheduled_time_str]):
                flash("Please fill all required fields", "danger")
                return redirect(url_for('schedule_live_class'))

            try:
                scheduled_time = datetime.strptime(scheduled_time_str, '%Y-%m-%dT%H:%M')
                if scheduled_time < datetime.now():
                    flash("Scheduled time must be in the future", "danger")
                    return redirect(url_for('schedule_live_class'))
            except ValueError:
                flash("Invalid date/time format", "danger")
                return redirect(url_for('schedule_live_class'))

            # Get the selected course
            selected_course = next((c for c in teacher_courses if c['id'] == course_id), None)
            if not selected_course:
                flash("Invalid course selection", "danger")
                return redirect(url_for('schedule_live_class'))

            # Use teacher's default meeting link from profile or course
            meeting_link = current_user.meeting_link or selected_course.get('default_meeting_link', '')
            if not meeting_link:
                flash("Please set up your default meeting link in your profile first", "danger")
                return redirect(url_for('profile'))

            # Create live class document
            live_class_data = {
                'course_id': course_id,
                'title': title,
                'description': description,
                'meeting_link': meeting_link,
                'scheduled_time': scheduled_time,
                'duration_minutes': duration,
                'teacher_id': current_user.id,
                'teacher_name': current_user.name,
                'status': 'scheduled',
                'created_at': firestore.SERVER_TIMESTAMP,
                'chapter_id': chapter_id if chapter_id else None
            }

            # Add to Firestore
            db.collection('live_classes').add(live_class_data)

            # Notify enrolled students
            enrolled_students = db.collection('students').where('courses_enrolled', 'array_contains', course_id).stream()
            for student in enrolled_students:
                db.collection('notifications').add({
                    'user_id': student.id,
                    'title': 'New Live Class Scheduled',
                    'message': f'New live class scheduled for {selected_course["name"]} on {scheduled_time.strftime("%B %d, %Y at %I:%M %p")}',
                    'type': 'live_class',
                    'related_id': course_id,
                    'read': False,
                    'created_at': firestore.SERVER_TIMESTAMP
                })

            flash("Live class scheduled successfully!", "success")
            return redirect(url_for('dashboard'))

        # GET request - show form
        # Prepare chapter options for all courses
        course_chapters = {}
        for course in teacher_courses:
            chapters = course.get('chapters', [])
            course_chapters[course['id']] = [{'id': f'chapter_{i}', 'title': ch['title']} 
                                           for i, ch in enumerate(chapters)]

        return render_template('schedule_live_class.html',
                            courses=teacher_courses,
                            course_chapters=course_chapters,
                            min_date=datetime.now().strftime('%Y-%m-%d'),
                            default_time=(datetime.now() + timedelta(hours=1)).strftime('%H:%M'))

    except Exception as e:
        app.logger.error(f"Error scheduling live class: {str(e)}", exc_info=True)
        flash(f"Error scheduling live class: {str(e)}", "danger")
        return redirect(url_for('dashboard'))


@app.route('/test')
def test():
    return render_template('test.html')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/FAQs')
def FAQs():
    return render_template('faqs.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/base')
def base():
    return render_template('base.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
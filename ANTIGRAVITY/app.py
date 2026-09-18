from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from config import Config
from database import db, User, Book, IssuedBook
from seed_data import seed_database
import os

app = Flask(__name__)
app.config.from_object(Config)
app.config['SQLALCHEMY_DATABASE_URI'] = Config.get_database_uri()

# Initialize Database
db.init_app(app)

with app.app_context():
    try:
        db.create_all()
        seed_database()
    except Exception as e:
        print(f"Warning/Error initializing database: {e}")
        # If MySQL failed, fallback to SQLite automatically
        print("Falling back to local SQLite database...")
        app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLITE_URI
        db.create_all()
        seed_database()


# ---------------------------------------------------------
# Helper Decorators & Functions
# ---------------------------------------------------------
def get_current_user():
    user_id = session.get('user_id')
    if user_id:
        return User.query.filter_by(user_id=user_id).first()
    return None

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Authentication required. Please log in.'}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user = get_current_user()
        if not current_user or current_user.role != 'admin':
            return jsonify({'success': False, 'message': 'Admin privileges required.'}), 403
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------
# Web Page Routes
# ---------------------------------------------------------
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('index.html')

@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html')


# ---------------------------------------------------------
# Authentication API Routes
# ---------------------------------------------------------
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    user_identifier = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role_type = data.get('role', 'student').lower() # 'admin' or 'student'

    if not user_identifier or not password:
        return jsonify({'success': False, 'message': 'Username/ID and password are required.'}), 400

    # Search user by user_id or email
    user = User.query.filter(
        (User.user_id == user_identifier) | (User.email == user_identifier)
    ).first()

    if not user or not user.check_password(password):
        return jsonify({'success': False, 'message': 'Invalid User ID/Email or Password.'}), 401

    if role_type == 'admin' and user.role != 'admin':
        return jsonify({'success': False, 'message': 'Account does not have Admin rights.'}), 403

    # Set Session
    session['user_id'] = user.user_id
    session['role'] = user.role
    session['name'] = user.name

    return jsonify({
        'success': True,
        'message': f'Welcome back, {user.name}!',
        'user': user.to_dict()
    })

@app.route('/api/logout', methods=['POST', 'GET'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully.'})

@app.route('/api/current_user', methods=['GET'])
def current_user():
    user = get_current_user()
    if not user:
        return jsonify({'logged_in': False}), 200
    return jsonify({
        'logged_in': True,
        'user': user.to_dict()
    })


# ---------------------------------------------------------
# Network Info API Route (For Mobile Access)
# ---------------------------------------------------------
@app.route('/api/network-info', methods=['GET'])
def network_info():
    import socket
    ip_address = '127.0.0.1'
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    mobile_url = f"http://{ip_address}:5000"
    qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={mobile_url}"

    return jsonify({
        'success': True,
        'ip_address': ip_address,
        'port': 5000,
        'mobile_url': mobile_url,
        'qr_code_url': qr_code_url
    })


# ---------------------------------------------------------
# Dashboard Statistics API Route
# ---------------------------------------------------------
@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
def dashboard_stats():
    total_books = db.session.query(db.func.sum(Book.total_copies)).scalar() or 0
    available_books = db.session.query(db.func.sum(Book.available_copies)).scalar() or 0
    total_book_titles = Book.query.count()
    
    # Active issued books (where status is 'issued' or overdue)
    active_issued = IssuedBook.query.filter(IssuedBook.status != 'returned').count()
    total_students = User.query.filter_by(role='student').count()

    # Overdue count
    today = date.today()
    overdue_count = IssuedBook.query.filter(
        IssuedBook.status == 'issued',
        IssuedBook.due_date < today
    ).count()

    # Pending requests count
    pending_count = IssuedBook.query.filter_by(status='pending').count()

    # Recent activities (last 5 issues/returns/requests)
    recent_issues = IssuedBook.query.order_by(IssuedBook.created_at.desc()).limit(5).all()

    return jsonify({
        'success': True,
        'stats': {
            'total_books': total_books,
            'available_books': available_books,
            'issued_books': active_issued,
            'total_students': total_students,
            'total_titles': total_book_titles,
            'overdue_books': overdue_count,
            'pending_requests': pending_count
        },
        'recent_activities': [item.to_dict() for item in recent_issues]
    })


# ---------------------------------------------------------
# Book Management API Routes
# ---------------------------------------------------------
@app.route('/api/books', methods=['GET'])
@login_required
def get_books():
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    available_only = request.args.get('available', '').lower() == 'true'

    query = Book.query

    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            (Book.title.ilike(search_pattern)) |
            (Book.author.ilike(search_pattern)) |
            (Book.category.ilike(search_pattern)) |
            (Book.isbn.ilike(search_pattern)) |
            (Book.rack_number.ilike(search_pattern))
        )

    if category_filter and category_filter != 'All':
        query = query.filter(Book.category.ilike(category_filter))

    if available_only:
        query = query.filter(Book.available_copies > 0)

    books = query.order_by(Book.title.asc()).all()
    categories = [cat[0] for cat in db.session.query(Book.category).distinct().all()]

    return jsonify({
        'success': True,
        'books': [book.to_dict() for book in books],
        'categories': sorted(categories)
    })

@app.route('/api/books/<int:book_id>', methods=['GET'])
@login_required
def get_book_by_id(book_id):
    book = Book.query.get_or_404(book_id)
    return jsonify({'success': True, 'book': book.to_dict()})

@app.route('/api/books', methods=['POST'])
@admin_required
def add_book():
    data = request.get_json() or {}

    title = data.get('title', '').strip()
    author = data.get('author', '').strip()
    isbn = data.get('isbn', '').strip()
    category = data.get('category', '').strip()
    publisher = data.get('publisher', '').strip()
    total_copies = int(data.get('total_copies', 1))
    rack_number = data.get('rack_number', '').strip()
    description = data.get('description', '').strip()

    if not title or not author or not isbn or not category:
        return jsonify({'success': False, 'message': 'Title, Author, ISBN, and Category are required.'}), 400

    existing_book = Book.query.filter_by(isbn=isbn).first()
    if existing_book:
        return jsonify({'success': False, 'message': f'Book with ISBN {isbn} already exists.'}), 400

    new_book = Book(
        title=title,
        author=author,
        isbn=isbn,
        category=category,
        publisher=publisher,
        total_copies=total_copies,
        available_copies=total_copies,
        rack_number=rack_number,
        description=description
    )

    db.session.add(new_book)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Book "{title}" added successfully!',
        'book': new_book.to_dict()
    }), 201

@app.route('/api/books/<int:book_id>', methods=['PUT'])
@admin_required
def update_book(book_id):
    book = Book.query.get_or_404(book_id)
    data = request.get_json() or {}

    old_total = book.total_copies
    old_available = book.available_copies

    new_total = int(data.get('total_copies', book.total_copies))
    diff = new_total - old_total

    # Ensure available copies won't go negative if copies are reduced
    if old_available + diff < 0:
        return jsonify({
            'success': False,
            'message': f'Cannot decrease total copies below currently issued copies.'
        }), 400

    book.title = data.get('title', book.title).strip()
    book.author = data.get('author', book.author).strip()
    book.category = data.get('category', book.category).strip()
    book.publisher = data.get('publisher', book.publisher).strip()
    book.total_copies = new_total
    book.available_copies = old_available + diff
    book.rack_number = data.get('rack_number', book.rack_number).strip()
    book.description = data.get('description', book.description).strip()

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Book details updated successfully!',
        'book': book.to_dict()
    })

@app.route('/api/books/<int:book_id>', methods=['DELETE'])
@admin_required
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)

    # Check if there are active unreturned issues
    active_issues = IssuedBook.query.filter_by(book_id=book.id, status='issued').first()
    if active_issues:
        return jsonify({
            'success': False,
            'message': 'Cannot delete book because copies are currently issued to students.'
        }), 400

    db.session.delete(book)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Book "{book.title}" deleted successfully.'
    })


# ---------------------------------------------------------
# Student Management API Routes
# ---------------------------------------------------------
@app.route('/api/students', methods=['GET'])
@login_required
def get_students():
    search_query = request.args.get('search', '').strip()
    query = User.query.filter_by(role='student')

    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            (User.user_id.ilike(search_pattern)) |
            (User.name.ilike(search_pattern)) |
            (User.email.ilike(search_pattern)) |
            (User.department.ilike(search_pattern))
        )

    students = query.order_by(User.user_id.asc()).all()
    return jsonify({
        'success': True,
        'students': [stu.to_dict() for stu in students]
    })

@app.route('/api/students', methods=['POST'])
@admin_required
def add_student():
    data = request.get_json() or {}

    user_id = data.get('user_id', '').strip() # Roll Number
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    department = data.get('department', '').strip()
    year = data.get('year', '').strip()
    password = data.get('password', 'student123').strip()

    if not user_id or not name or not email:
        return jsonify({'success': False, 'message': 'Student ID (Roll No), Name, and Email are required.'}), 400

    if User.query.filter_by(user_id=user_id).first():
        return jsonify({'success': False, 'message': f'Student ID "{user_id}" already exists.'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': f'Email "{email}" is already registered.'}), 400

    new_student = User(
        user_id=user_id,
        name=name,
        email=email,
        phone=phone,
        department=department,
        year=year,
        role='student'
    )
    new_student.set_password(password)

    db.session.add(new_student)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Student "{name}" ({user_id}) registered successfully!',
        'student': new_student.to_dict()
    }), 201

@app.route('/api/students/<int:id>', methods=['PUT'])
@admin_required
def update_student(id):
    student = User.query.get_or_404(id)
    if student.role != 'student':
        return jsonify({'success': False, 'message': 'Invalid user account.'}), 400

    data = request.get_json() or {}
    student.name = data.get('name', student.name).strip()
    student.email = data.get('email', student.email).strip()
    student.phone = data.get('phone', student.phone).strip()
    student.department = data.get('department', student.department).strip()
    student.year = data.get('year', student.year).strip()

    if data.get('password'):
        student.set_password(data.get('password').strip())

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Student details updated successfully!',
        'student': student.to_dict()
    })

@app.route('/api/students/<int:id>', methods=['DELETE'])
@admin_required
def delete_student(id):
    student = User.query.get_or_404(id)
    if student.role != 'student':
        return jsonify({'success': False, 'message': 'Cannot delete non-student accounts.'}), 400

    # Check for active issued books
    active_issues = IssuedBook.query.filter_by(student_id=student.user_id, status='issued').first()
    if active_issues:
        return jsonify({
            'success': False,
            'message': 'Cannot delete student while they have unreturned books.'
        }), 400

    db.session.delete(student)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Student account {student.user_id} deleted successfully.'
    })


# ---------------------------------------------------------
# Issue & Return Books API Routes
# ---------------------------------------------------------
@app.route('/api/issued-books', methods=['GET'])
@login_required
def get_issued_books():
    current_user = get_current_user()
    status_filter = request.args.get('status', '').strip()
    search_query = request.args.get('search', '').strip()

    query = IssuedBook.query

    # Students only see their own issued books
    if current_user.role == 'student':
        query = query.filter_by(student_id=current_user.user_id)

    if status_filter and status_filter != 'All':
        if status_filter == 'overdue':
            query = query.filter(IssuedBook.status == 'issued', IssuedBook.due_date < date.today())
        else:
            query = query.filter(IssuedBook.status == status_filter)

    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.join(Book).filter(
            (Book.title.ilike(search_pattern)) |
            (Book.isbn.ilike(search_pattern)) |
            (IssuedBook.student_id.ilike(search_pattern))
        )

    issued_list = query.order_by(IssuedBook.issue_date.desc()).all()
    return jsonify({
        'success': True,
        'issued_books': [item.to_dict() for item in issued_list]
    })

@app.route('/api/issue', methods=['POST'])
@admin_required
def issue_book():
    data = request.get_json() or {}

    book_id = data.get('book_id')
    student_id = data.get('student_id', '').strip()
    days_to_issue = int(data.get('days', 14))
    notes = data.get('notes', '').strip()

    if not book_id or not student_id:
        return jsonify({'success': False, 'message': 'Book and Student Roll Number are required.'}), 400

    book = Book.query.get(book_id)
    if not book:
        return jsonify({'success': False, 'message': 'Book not found.'}), 44

    if book.available_copies <= 0:
        return jsonify({'success': False, 'message': f'Book "{book.title}" is currently out of stock.'}), 400

    student = User.query.filter_by(user_id=student_id, role='student').first()
    if not student:
        return jsonify({'success': False, 'message': f'Student with ID "{student_id}" not found.'}), 404

    # Check if student already has this book issued & unreturned
    already_issued = IssuedBook.query.filter_by(
        book_id=book.id,
        student_id=student.user_id,
        status='issued'
    ).first()

    if already_issued:
        return jsonify({
            'success': False,
            'message': f'Student {student.name} already has a copy of "{book.title}" issued.'
        }), 400

    # Calculate issue date and due date
    issue_dt = date.today()
    due_dt = issue_dt + timedelta(days=days_to_issue)

    new_issue = IssuedBook(
        book_id=book.id,
        student_id=student.user_id,
        issue_date=issue_dt,
        due_date=due_dt,
        status='issued',
        notes=notes
    )

    # Decrement available copies
    book.available_copies -= 1

    db.session.add(new_issue)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Book "{book.title}" issued to {student.name} successfully! Due date: {due_dt.strftime("%Y-%m-%d")}',
        'issued_book': new_issue.to_dict()
    }), 201

@app.route('/api/return/<int:issue_id>', methods=['POST'])
@admin_required
def return_book(issue_id):
    issue_record = IssuedBook.query.get_or_404(issue_id)

    if issue_record.status == 'returned':
        return jsonify({'success': False, 'message': 'This book has already been returned.'}), 400

    issue_record.status = 'returned'
    issue_record.return_date = date.today()

    # Increment available copies
    book = Book.query.get(issue_record.book_id)
    if book:
        book.available_copies += 1

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Book "{book.title if book else "Book"}" successfully returned!'
    })

@app.route('/api/extend/<int:issue_id>', methods=['POST'])
@login_required
def extend_due_date(issue_id):
    issue_record = IssuedBook.query.get_or_404(issue_id)
    current_user = get_current_user()

    if current_user.role == 'student' and issue_record.student_id != current_user.user_id:
        return jsonify({'success': False, 'message': 'Unauthorized action.'}), 403

    if issue_record.status == 'returned':
        return jsonify({'success': False, 'message': 'Cannot extend return date for an already returned book.'}), 400

    # Extend due date by 7 days
    issue_record.due_date = issue_record.due_date + timedelta(days=7)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Due date extended by 7 days to {issue_record.due_date.strftime("%Y-%m-%d")}.'
    })


@app.route('/api/request-book', methods=['POST'])
@login_required
def request_book():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'success': False, 'message': 'Authentication required.'}), 401

    data = request.get_json() or {}
    book_id = data.get('book_id')
    notes = data.get('notes', 'Requested by student').strip()

    if not book_id:
        return jsonify({'success': False, 'message': 'Book ID is required.'}), 400

    book = Book.query.get(book_id)
    if not book:
        return jsonify({'success': False, 'message': 'Book not found.'}), 404

    if book.available_copies <= 0:
        return jsonify({'success': False, 'message': f'"{book.title}" is currently out of stock.'}), 400

    # Check if student already has a pending or active issue for this book
    existing = IssuedBook.query.filter(
        IssuedBook.book_id == book.id,
        IssuedBook.student_id == current_user.user_id,
        IssuedBook.status.in_(['pending', 'issued'])
    ).first()

    if existing:
        msg = 'You already have an active request for this book.' if existing.status == 'pending' else 'This book is already issued to you.'
        return jsonify({'success': False, 'message': msg}), 400

    issue_dt = date.today()
    due_dt = issue_dt + timedelta(days=14)

    new_request = IssuedBook(
        book_id=book.id,
        student_id=current_user.user_id,
        issue_date=issue_dt,
        due_date=due_dt,
        status='pending',
        notes=notes
    )

    db.session.add(new_request)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Request for "{book.title}" sent to Admin for approval!',
        'issued_book': new_request.to_dict()
    }), 201


@app.route('/api/requests/<int:issue_id>/approve', methods=['POST'])
@admin_required
def approve_book_request(issue_id):
    issue_record = IssuedBook.query.get_or_404(issue_id)

    if issue_record.status != 'pending':
        return jsonify({'success': False, 'message': f'Cannot approve request with status "{issue_record.status}".'}), 400

    book = Book.query.get(issue_record.book_id)
    if not book or book.available_copies <= 0:
        return jsonify({'success': False, 'message': 'Cannot approve request: Book out of stock.'}), 400

    # Approve request & update book availability
    issue_record.status = 'issued'
    issue_record.issue_date = date.today()
    issue_record.due_date = date.today() + timedelta(days=14)
    book.available_copies -= 1

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Book request approved! "{book.title}" has been issued to student {issue_record.student_id}.'
    })


@app.route('/api/requests/<int:issue_id>/reject', methods=['POST'])
@admin_required
def reject_book_request(issue_id):
    issue_record = IssuedBook.query.get_or_404(issue_id)

    if issue_record.status != 'pending':
        return jsonify({'success': False, 'message': f'Cannot reject request with status "{issue_record.status}".'}), 400

    issue_record.status = 'rejected'
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Book request for student {issue_record.student_id} rejected.'
    })


# ---------------------------------------------------------
# Application Runner
# ---------------------------------------------------------
if __name__ == '__main__':
    print("Starting College Digital Library Management System...")
    print("Server running at http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)

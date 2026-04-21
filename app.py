import json
import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, session, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-prod'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ---------------------------------------------------------------------------
# Load static data once at startup
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(__file__)

with open(os.path.join(BASE_DIR, 'data', 'exercises.json')) as f:
    EXERCISES = json.load(f)

with open(os.path.join(BASE_DIR, 'data', 'quiz.json')) as f:
    QUIZ = json.load(f)

TOTAL_LESSONS = len(EXERCISES)
TOTAL_QUESTIONS = len(QUIZ)


def _first_existing_media(*relative_paths):
    """Return the first relative static path whose file exists, else None."""
    for rel in relative_paths:
        abs_path = os.path.join(BASE_DIR, 'static', rel)
        if os.path.exists(abs_path):
            return rel
    return None


_EXERCISE_GIFS = {
    1: 'images/gif/Lat-Pulldown.gif',
    2: 'images/gif/Face-Pull.gif',
    3: 'images/gif/Standing-Dumbbell-Overhead-Press.gif',
    4: 'images/gif/Z-Bar-Preacher-Curl.gif',
    5: 'images/gif/Pushdown.gif',
}

def exercise_media(exercise_id):
    gif = _EXERCISE_GIFS.get(exercise_id)
    if gif:
        return _first_existing_media(gif)
    return _first_existing_media(
        f'images/exercises/exercise-{exercise_id}.gif',
        f'images/exercises/exercise-{exercise_id}.png',
    )


def exercise_diagram(exercise_id):
    return _first_existing_media(f'images/exercises/exercise-{exercise_id}.png')


# lx/ly = label position (%), tx/ty = arrow tip on the muscle (%)
# lx < 50 → label on left side; lx > 50 → label on right side
_MUSCLE_LABELS = {
    1: [  # Lat Pulldown
        {'name': 'Lats',       'lx': 8,  'ly': 80, 'tx': 47, 'ty': 50},
        {'name': 'Rear Delts', 'lx': 10,  'ly': 44, 'tx': 47, 'ty': 38},
        {'name': 'Biceps',     'lx': 84, 'ly': 18, 'tx': 65, 'ty': 36},
    ],
    2: [  # Face Pulls
        {'name': 'Rear Delts',   'lx': 6,  'ly': 68, 'tx': 63, 'ty': 24},
        {'name': 'Traps',        'lx': 48, 'ly': 92, 'tx': 73, 'ty': 28},
        {'name': 'Rotator Cuff', 'lx': 78, 'ly': 12, 'tx': 68, 'ty': 29},
    ],
    3: [  # Overhead Press
        {'name': 'Front Delts', 'lx': 6,  'ly': 82, 'tx': 46, 'ty': 37},
        {'name': 'Side Delts',  'lx': 6,  'ly': 50, 'tx': 42, 'ty': 36},
        {'name': 'Triceps',     'lx': 84, 'ly': 44, 'tx': 57, 'ty': 44},
        {'name': 'Upper Chest', 'lx': 82, 'ly': 76, 'tx': 48, 'ty': 38},
    ],
    4: [  # Preacher Curl
        {'name': 'Brachialis',     'lx': 82, 'ly': 74, 'tx': 49, 'ty': 33},
        {'name': 'Biceps', 'lx': 6,  'ly': 88, 'tx': 40, 'ty': 35},
    ],
    5: [  # Tricep Pushdown
        {'name': 'Triceps', 'lx': 6, 'ly': 80, 'tx': 25, 'ty': 39},
    ],
}


def question_media(question_num):
    return _first_existing_media(
        f'images/questions/question-{question_num}.gif',
        f'images/questions/question-{question_num}.png',
    )

# ---------------------------------------------------------------------------
# Database models
# ---------------------------------------------------------------------------

class UserSession(db.Model):
    """Created once per app start (one user at a time)."""
    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)

    lesson_visits = db.relationship('LessonVisit', backref='user_session', lazy=True)
    quiz_answers  = db.relationship('QuizAnswer',  backref='user_session', lazy=True)


class LessonVisit(db.Model):
    """Records each time a lesson page is loaded."""
    id          = db.Column(db.Integer, primary_key=True)
    session_id  = db.Column(db.Integer, db.ForeignKey('user_session.id'), nullable=False)
    lesson_num  = db.Column(db.Integer, nullable=False)
    visited_at  = db.Column(db.DateTime, default=datetime.utcnow)


class QuizAnswer(db.Model):
    """Records the user's choice for each quiz question."""
    id            = db.Column(db.Integer, primary_key=True)
    session_id    = db.Column(db.Integer, db.ForeignKey('user_session.id'), nullable=False)
    question_num  = db.Column(db.Integer, nullable=False)
    answer_chosen = db.Column(db.String(10), nullable=False)
    is_correct    = db.Column(db.Boolean, nullable=False)
    answered_at   = db.Column(db.DateTime, default=datetime.utcnow)
    final_score   = db.Column(db.Integer, nullable=True)  # only set on last question


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_or_create_db_session():
    """Return the current DB session id from the Flask session cookie."""
    return session.get('db_session_id')


def _record_lesson_visit(lesson_num):
    db_sid = get_or_create_db_session()
    if db_sid:
        visit = LessonVisit(session_id=db_sid, lesson_num=lesson_num)
        db.session.add(visit)
        db.session.commit()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def home():
    return render_template('home.html')


@app.route('/start', methods=['POST'])
def start():
    """Create a new DB session and reset cookie-level state."""
    user_sess = UserSession()
    db.session.add(user_sess)
    db.session.commit()

    session.clear()
    session['db_session_id'] = user_sess.id
    session['answers'] = {}   # {str(question_num): chosen_letter}
    session['score']   = 0

    return redirect(url_for('exercises'))


@app.route('/exercises')
def exercises():
    items = []
    for ex in EXERCISES:
        items.append({**ex, 'media': exercise_media(ex['id'])})
    return render_template(
        'exercises.html',
        exercises=items,
    )


@app.route('/learn/<int:lesson_num>')
def learn(lesson_num):
    if lesson_num < 1 or lesson_num > TOTAL_LESSONS:
        return redirect(url_for('home'))

    exercise = EXERCISES[lesson_num - 1]
    _record_lesson_visit(lesson_num)

    return render_template(
        'learn.html',
        exercise=exercise,
        lesson_num=lesson_num,
        total_lessons=TOTAL_LESSONS,
        media=exercise_media(exercise['id']),
        diagram=exercise_diagram(exercise['id']),
        muscle_labels=_MUSCLE_LABELS.get(exercise['id'], []),
    )


@app.route('/quiz')
def quiz_intro():
    return render_template('quiz_intro.html')


@app.route('/quiz/<int:question_num>')
def quiz(question_num):
    if question_num < 1 or question_num > TOTAL_QUESTIONS:
        return redirect(url_for('results'))

    question = QUIZ[question_num - 1]

    # Check if already answered (allow review without re-recording)
    already_answered = str(question_num) in session.get('answers', {})
    chosen = session['answers'].get(str(question_num)) if already_answered else None

    return render_template(
        'quiz.html',
        question=question,
        question_num=question_num,
        total_questions=TOTAL_QUESTIONS,
        already_answered=already_answered,
        chosen=chosen,
        media=question_media(question_num),
    )


@app.route('/submit_answer', methods=['POST'])
def submit_answer():
    """
    AJAX endpoint called by jQuery when the user clicks an answer.
    Expects JSON: { question_num: int, answer: str }
    Returns JSON: { is_correct: bool, correct: str, feedback: str, next_url: str }
    """
    data         = request.get_json(force=True)
    question_num = int(data.get('question_num', 0))
    chosen       = str(data.get('answer', '')).upper()

    if question_num < 1 or question_num > TOTAL_QUESTIONS:
        return jsonify(error='Invalid question number'), 400

    question    = QUIZ[question_num - 1]
    correct     = question['correct']
    is_correct  = chosen == correct
    feedback    = question['explanations'].get(chosen, '')

    # Persist to cookie-session (only record first attempt)
    answers = session.get('answers', {})
    if str(question_num) not in answers:
        answers[str(question_num)] = chosen
        session['answers'] = answers
        if is_correct:
            session['score'] = session.get('score', 0) + 1

        # Persist to DB
        db_sid = get_or_create_db_session()
        if db_sid:
            final_score = session['score'] if question_num == TOTAL_QUESTIONS else None
            record = QuizAnswer(
                session_id    = db_sid,
                question_num  = question_num,
                answer_chosen = chosen,
                is_correct    = is_correct,
                final_score   = final_score,
            )
            db.session.add(record)
            db.session.commit()

    # Determine where "Next Question" should go
    if question_num < TOTAL_QUESTIONS:
        next_url = url_for('quiz', question_num=question_num + 1)
    else:
        next_url = url_for('results')

    return jsonify(
        is_correct    = is_correct,
        correct       = correct,
        feedback      = feedback,
        next_url      = next_url,
    )


@app.route('/results')
def results():
    score   = session.get('score', 0)
    answers = session.get('answers', {})

    # Build per-question summary
    summary = []
    for q in QUIZ:
        q_num  = str(q['id'])
        chosen = answers.get(q_num)
        summary.append({
            'question'    : q['question'],
            'chosen'      : chosen,
            'chosen_text' : q['options'].get(chosen, 'Not answered') if chosen else 'Not answered',
            'correct'     : q['correct'],
            'correct_text': q['options'][q['correct']],
            'is_correct'  : chosen == q['correct'],
            'feedback'    : q['explanations'].get(chosen, '') if chosen else '',
        })

    return render_template(
        'results.html',
        score          = score,
        total_questions= TOTAL_QUESTIONS,
        summary        = summary,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

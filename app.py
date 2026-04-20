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

    return redirect(url_for('learn', lesson_num=1))


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

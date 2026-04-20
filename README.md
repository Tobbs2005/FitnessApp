# Mastering the Pull: Upper Body Basics

A beginner's interactive guide to 5 key upper body exercises, built as a Flask web app for a Columbia University UI/UX course project.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

## Project Structure

```
├── app.py               # Flask app, routes, DB models
├── data/
│   ├── exercises.json   # 5 exercises with muscles, steps, common mistakes
│   └── quiz.json        # 5 questions with answer choices and explanations
└── templates/
    ├── base.html        # Shared nav, Bootstrap 5 + jQuery
    ├── home.html        # Landing page
    ├── learn.html       # Individual exercise detail (/learn/<n>)
    ├── quiz_intro.html  # Quiz intro page
    ├── quiz.html        # Quiz question with AJAX answer submission (/quiz/<n>)
    └── results.html     # Final score + answer breakdown
```

## Team

- **Akrisht Kaul** — backend, data, routes
- **Toby** — UI design and styling

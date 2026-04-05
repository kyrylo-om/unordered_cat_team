# Django + React Barebones App

This project is a minimal working foundation with:
- Django backend API
- React frontend (Vite, JavaScript)

## Structure

- backend: Django project
- frontend: React app

## Run backend

```bash
cd backend
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py runserver
```

Backend runs on http://127.0.0.1:8000
API endpoint: http://127.0.0.1:8000/api/hello/

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on http://127.0.0.1:5173

The frontend calls /api/hello/ and Vite proxies it to Django.

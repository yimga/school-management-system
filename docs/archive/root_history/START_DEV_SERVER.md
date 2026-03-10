# Start Development Server - Quick Commands

## 🚀 Quick Start (Copy & Paste)

### Option 1: Basic Start (Recommended)
```bash
cd "c:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system"
python manage.py runserver
```

**Server will start at:** http://127.0.0.1:8000

---

### Option 2: Custom Port
```bash
cd "c:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system"
python manage.py runserver 8000
```

**Or use a different port:**
```bash
python manage.py runserver 8080
```

---

### Option 3: Accessible from Network (Other devices)
```bash
cd "c:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system"
python manage.py runserver 0.0.0.0:8000
```

---

## 📋 Pre-Start Checklist

Before starting, ensure:

1. **You're in the project directory:**
   ```bash
   cd "c:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system"
   ```

2. **Virtual environment is activated** (if using one):
   ```bash
   # If you have a venv
   venv\Scripts\activate
   
   # Or if using conda
   conda activate your-env-name
   ```

3. **Dependencies are installed:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Database migrations are applied:**
   ```bash
   python manage.py migrate
   ```

---

## 🎯 One-Line Command (All-in-One)

If everything is set up, just run:
```bash
cd "c:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system" && python manage.py runserver
```

---

## 🌐 Access URLs

Once server starts, access:

- **Admin Dashboard:** http://127.0.0.1:8000/admin/
- **Backend Dashboard:** http://127.0.0.1:8000/backend/
- **Portal:** http://127.0.0.1:8000/portal/
- **API:** http://127.0.0.1:8000/api/

---

## 🛑 Stop Server

Press `Ctrl + C` in the terminal where server is running.

---

## 🔧 Troubleshooting

### Port Already in Use
```bash
# Use a different port
python manage.py runserver 8001
```

### Module Not Found Error
```bash
# Install dependencies
pip install -r requirements.txt
```

### Database Error
```bash
# Run migrations
python manage.py migrate
```

### Static Files Not Loading
```bash
# Collect static files (if needed)
python manage.py collectstatic --noinput
```

---

## 📝 Full Setup Sequence (First Time)

```bash
# 1. Navigate to project
cd "c:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system"

# 2. Activate virtual environment (if using)
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run migrations
python manage.py migrate

# 5. Create superuser (if needed)
python manage.py ensure_superuser
# Or: python manage.py createsuperuser

# 6. Start server
python manage.py runserver
```

---

## ✅ Verify Server is Running

You should see output like:
```
Watching for file changes with StatReloader
Performing system checks...

System check identified no issues (0 silenced).
January 31, 2026 - 12:00:00
Django version X.X.X, using settings 'config.settings'
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

---

**Ready to test!** 🎉

import os, sqlite3, secrets, io, csv, time, json, re
from pathlib import Path
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort, send_file
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from html.parser import HTMLParser
from markupsafe import Markup

BASE = Path(__file__).resolve().parent
DB = BASE / 'kazemi.db'
UPLOAD_DIR = BASE / 'static' / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
FONT_ALLOWED = {'woff2','woff','ttf','otf'}
app = Flask(__name__)
def load_secret_key():
    configured = os.environ.get('SECRET_KEY')
    if configured:
        return configured
    key_file = BASE / '.kazemi_secret_key'
    try:
        if key_file.exists():
            return key_file.read_text(encoding='utf-8').strip()
        value = secrets.token_urlsafe(48)
        key_file.write_text(value, encoding='utf-8')
        try: key_file.chmod(0o600)
        except OSError: pass
        return value
    except OSError:
        return secrets.token_urlsafe(48)

app.secret_key = load_secret_key()
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
LOGIN_ATTEMPTS = {}

class RichTextSanitizer(HTMLParser):
    ALLOWED_TAGS = {'font','p','br','h2','h3','h4','strong','b','em','i','u','s','ul','ol','li','blockquote','a','img','figure','figcaption','hr','table','thead','tbody','tr','th','td','div','span'}
    ALLOWED_ATTRS = {'a': {'href','target','rel'}, 'font': {'color','size'}, 'img': {'src','alt','title','width','height'}, 'td': {'colspan','rowspan'}, 'th': {'colspan','rowspan'}, 'p': {'style'}, 'h2': {'style'}, 'h3': {'style'}, 'h4': {'style'}, 'div': {'style'}, 'span': {'style'}, 'img': {'style'}, 'figure': {'style'}}
    VOID = {'br','hr','img'}
    def __init__(self):
        super().__init__(convert_charrefs=True); self.out=[]
    def handle_starttag(self, tag, attrs):
        if tag not in self.ALLOWED_TAGS: return
        clean=[]
        for k,v in attrs:
            if k in self.ALLOWED_ATTRS.get(tag,set()) and v is not None and not k.lower().startswith('on'):
                if k in {'href','src'} and re.match(r'\s*(javascript:|data:)',v,re.I): continue
                if k == 'style':
                    safe=[]
                    for decl in v.split(';'):
                        if ':' not in decl: continue
                        prop,val=decl.split(':',1); prop=prop.strip().lower(); val=val.strip()
                        if prop in {'text-align','width','max-width','height'} and not re.search(r'(url|expression|javascript)',val,re.I): safe.append(f'{prop}:{val}')
                    if not safe: continue
                    v=';'.join(safe)
                clean.append(f'{k}="{str(v).replace(chr(34),"&quot;")}"')
        if tag=='a': clean += ['rel="noopener noreferrer"']
        self.out.append('<'+tag+(' '+' '.join(clean) if clean else '')+'>')
    def handle_endtag(self, tag):
        if tag in self.ALLOWED_TAGS and tag not in self.VOID: self.out.append('</'+tag+'>')
    def handle_data(self, data): self.out.append(data.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'))
    def html(self): return ''.join(self.out)
def clean_rich_html(value):
    parser=RichTextSanitizer(); parser.feed(value or ''); return parser.html()

DEFAULTS = {
 'company':'پیمانکاری کاظمی', 'slogan':'سنگ‌کاری • نما • اجرای ساختمان',
 'heroText':'پیمانکاری کاظمی؛ همراه مطمئن شما در اجرای سنگ‌کاری، نمای ساختمان و پروژه‌های ساختمانی، از ایده تا تحویل نهایی.', 'hero_heading':'سنگ را با هنر و سازه را با اعتماد بسازید.', 'about_heading':'ساختن فقط اجرا نیست؛ تعهد به نتیجه است.', 'services_heading':'تخصص‌هایی برای ساخت بهتر', 'projects_heading':'نتیجه کار، معرف ماست.', 'contact_heading':'پروژه‌تان را با ما شروع کنید.',
 'aboutText':'در پیمانکاری کاظمی، هر پروژه با شناخت نیاز کارفرما، انتخاب مصالح مناسب و برنامه‌ریزی دقیق آغاز می‌شود. هدف ما اجرای تمیز، اصولی و ماندگار است.',
 'quote':'اعتماد با حرف ساخته نمی‌شود؛ با کیفیت کار، ماندگار می‌شود.',
 'experience':'۱۰+', 'projectsCount':'۷۰+', 'phone':'', 'whatsapp':'', 'telegram':'', 'address':'', 'about_bg_image':'/static/uploads/about-stone-background-user.jpg', 'statement_bg_image':'', 'footer_credit_text':'MADE BY DEKU', 'footer_credit_url':'',
 'hero_badge':'تخصص، دقت، ماندگاری', 'hero_projects_button':'مشاهده نمونه‌کارها', 'hero_contact_button':'درخواست مشاوره', 'experience_label':'سال تجربه', 'projects_label':'پروژه اجراشده', 'quality_label':'تعهد به کیفیت', 'hero_art_small':'پیمانکاری کاظمی', 'hero_art_title':'کیفیت در جزئیات است', 'about_label':'درباره پیمانکاری کاظمی', 'about_link':'برای شروع همکاری با ما تماس بگیرید', 'services_intro':'خدمات اجرایی با توجه به کیفیت مصالح، دقت نصب و نیاز واقعی هر پروژه.', 'projects_intro':'نمونه‌کارهای واقعی و جزئیات پروژه‌های اجراشده را مشاهده کنید.', 'blog_label':'دانش و تجربه', 'blog_heading':'مجله کاظمی', 'blog_intro':'راهنماها، تجربه‌های اجرایی و نکات کاربردی درباره سنگ‌کاری و ساختمان.', 'contact_label':'تماس و مشاوره', 'contact_intro':'برای دریافت مشاوره، برآورد اولیه یا هماهنگی بازدید از پروژه با ما در تماس باشید.', 'contact_form_title':'درخواست مشاوره', 'contact_form_submit':'ارسال درخواست', 'contact_form_help':'با زدن دکمه، پیام در واتساپ شما آماده ارسال می‌شود.', 'footer_slogan':'سنگ‌کاری • نما • اجرای ساختمان', 'footer_copyright':'تمام حقوق محفوظ است.',
 'nav_home':'خانه', 'nav_blog':'مجله کاظمی', 'nav_services':'خدمات', 'nav_projects':'نمونه‌کارها', 'nav_about':'درباره ما', 'nav_contact':'تماس با ما', 'services_section_label':'۰۲ / خدمات ما', 'projects_section_label':'۰۳ / پروژه‌ها', 'project_search_label':'جست‌وجوی نمونه‌کار', 'project_search_placeholder':'عنوان یا دسته‌بندی پروژه...', 'project_empty':'نمونه‌کارها پس از ثبت در پنل مدیریت اینجا نمایش داده می‌شوند.', 'blog_empty':'مقاله‌های جدید به‌زودی منتشر می‌شوند.', 'blog_all_button':'مشاهده همه مقاله‌ها', 'custom_section_label':'بخش اختصاصی', 'statement_signature':'پیمانکاری کاظمی', 'phone_label':'شماره تماس', 'whatsapp_label':'واتساپ', 'whatsapp_action':'ارسال پیام در واتساپ', 'address_label':'موقعیت / آدرس', 'address_placeholder':'آدرس محل فعالیت را وارد کنید', 'form_name_label':'نام و نام خانوادگی', 'form_name_placeholder':'نام شما', 'form_phone_label':'شماره تماس', 'form_phone_placeholder':'شماره‌ای که با آن تماس بگیریم', 'form_service_label':'موضوع پروژه', 'form_message_label':'توضیحات پروژه', 'form_message_placeholder':'نوع پروژه، محل و توضیحات کوتاه...', 'form_other':'سایر', 'floating_label':'راه‌های ارتباطی', 'admin_link_label':'ورود مدیر', 'footer_top_label':'بازگشت به بالا', 'hero_scroll_label':'برای مشاهده ادامه صفحه', 'project_image_placeholder':'تصویر پروژه', 'blog_read_more':'ادامه مطلب', 'quality_number':'۱۰۰٪', 'header_call_label':'تماس و مشاوره', 'project_search_aria':'جست‌وجوی نمونه‌کار', 'project_reading_label':'مشاهده جزئیات پروژه',
 'seo_title':'پیمانکاری کاظمی | سنگ‌کاری و اجرای ساختمان',
 'seo_description':'اجرای تخصصی سنگ‌کاری، نمای ساختمان، بازسازی و پیمانکاری ساختمان در ایران.', 'accent_color':'#c7a46b', 'home_projects_limit':'12', 'seo_city':'', 'visual_layout':'{}'
}

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        con.execute('''CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, category TEXT NOT NULL, description TEXT DEFAULT '', image TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, is_favorite INTEGER NOT NULL DEFAULT 0)''')
        cols = [r['name'] for r in con.execute('PRAGMA table_info(projects)')]
        if 'is_favorite' not in cols:
            con.execute('ALTER TABLE projects ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0')
        con.execute('''CREATE TABLE IF NOT EXISTS service_categories (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL UNIQUE, slug TEXT NOT NULL UNIQUE, description TEXT DEFAULT '')''')
        con.execute('''CREATE TABLE IF NOT EXISTS home_sections (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT DEFAULT '', is_visible INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL DEFAULT 0)''')
        con.execute('''CREATE TABLE IF NOT EXISTS custom_pages (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, slug TEXT NOT NULL UNIQUE, content TEXT DEFAULT '', meta_description TEXT DEFAULT '', is_published INTEGER NOT NULL DEFAULT 1)''')
        defaults = [
            ('نمای سنگ ساختمان','nemaye-sang-sakhteman','اجرای تخصصی نمای سنگ ساختمان با دقت در انتخاب مصالح و جزئیات نصب.'),
            ('سنگ لاشه','sang-lashe','طراحی و اجرای سنگ لاشه برای فضاهای ساختمانی و محوطه.'),
            ('اجرای سنگ لاشه','ejraye-sang-lashe','اجرای اصولی سنگ لاشه با توجه به طرح و شرایط پروژه.'),
            ('سنگ‌کاری آبنما','sang-kari-abnama','اجرای سنگ‌کاری آبنما و جزئیات سنگی محوطه.')
        ]
        for title, slug, desc in defaults:
            con.execute('INSERT OR IGNORE INTO service_categories(title,slug,description) VALUES(?,?,?)',(title,slug,desc))
        # Migrate the earlier misspelled service label without losing linked projects.
        old_service = con.execute("SELECT id FROM service_categories WHERE title='سنگ کاری ابنما'").fetchone()
        correct_service = con.execute("SELECT id FROM service_categories WHERE title='سنگ‌کاری آبنما'").fetchone()
        if old_service:
            if correct_service:
                con.execute("UPDATE projects SET category='سنگ‌کاری آبنما' WHERE category='سنگ کاری ابنما'")
                con.execute("DELETE FROM service_categories WHERE id=?", (old_service['id'],))
            else:
                con.execute("UPDATE service_categories SET title='سنگ‌کاری آبنما',slug='sang-kari-abnama' WHERE id=?", (old_service['id'],))
                con.execute("UPDATE projects SET category='سنگ‌کاری آبنما' WHERE category='سنگ کاری ابنما'")
        con.execute('''CREATE TABLE IF NOT EXISTS blog_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            excerpt TEXT DEFAULT '',
            content TEXT NOT NULL,
            image TEXT DEFAULT '',
            meta_description TEXT DEFAULT '',
            is_published INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        con.execute('''CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT, service TEXT, message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        con.execute('''CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL)''')
        for k,v in DEFAULTS.items():
            con.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(k,v))
        if not con.execute('SELECT id FROM admins LIMIT 1').fetchone():
            username = os.environ.get('ADMIN_USERNAME', 'admin')
            password = os.environ.get('ADMIN_PASSWORD', 'Kazemi-Change-This-2026!')
            con.execute('INSERT INTO admins(username,password_hash) VALUES(?,?)',(username,generate_password_hash(password)))

init_db()

@app.context_processor
def inject_csrf():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    return {'csrf_token': session['csrf_token']}

def valid_csrf():
    return secrets.compare_digest(str(session.get('csrf_token', '')), str(request.form.get('csrf_token', '')))

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('admin_login', next=request.path))
        if request.method == 'POST' and not valid_csrf():
            abort(400, description='درخواست نامعتبر است؛ صفحه را تازه‌سازی کنید.')
        return fn(*args, **kwargs)
    return wrapped

def get_settings():
    with db() as con:
        values = dict(DEFAULTS)
        values.update({r['key']:r['value'] for r in con.execute('SELECT key,value FROM settings')})
        return values

@app.get('/')
def home():
    
    settings = get_settings()
    try: layout = json.loads(settings.get('visual_layout', '{}'))
    except (TypeError, ValueError): layout = {}
    with db() as con:
        categories = con.execute('SELECT * FROM service_categories ORDER BY id').fetchall()
        projects = con.execute('SELECT * FROM projects ORDER BY is_favorite DESC,id DESC LIMIT 60').fetchall()
        pages = con.execute('SELECT title,slug FROM custom_pages WHERE is_published=1 ORDER BY id DESC').fetchall()
        home_sections = con.execute('SELECT * FROM home_sections WHERE is_visible=1 ORDER BY sort_order,id').fetchall()
        blog_posts = con.execute('SELECT id,title,slug,excerpt,image,created_at FROM blog_posts WHERE is_published=1 ORDER BY created_at DESC,id DESC LIMIT 3').fetchall()
    return render_template('index.html', settings=settings, layout=layout, categories=categories, projects=projects, pages=pages, home_sections=home_sections, blog_posts=blog_posts)

@app.get('/service/<slug>')
def service_detail(slug):
    with db() as con:
        category = con.execute('SELECT * FROM service_categories WHERE slug=?',(slug,)).fetchone()
        if not category: abort(404)
        projects = con.execute('SELECT * FROM projects WHERE category=? ORDER BY is_favorite DESC,id DESC',(category['title'],)).fetchall()
    return render_template('service_detail.html', category=category, projects=projects, settings=get_settings())

@app.get('/page/<slug>')
def custom_page(slug):
    with db() as con:
        page = con.execute('SELECT * FROM custom_pages WHERE slug=? AND is_published=1',(slug,)).fetchone()
    if not page: abort(404)
    return render_template('custom_page.html', page=page, settings=get_settings())

@app.get('/project/<int:pid>')
def project_detail(pid):
    with db() as con:
        project = con.execute('SELECT * FROM projects WHERE id=?', (pid,)).fetchone()
    if not project: abort(404)
    return render_template('project_detail.html', project=project, settings=get_settings())

@app.get('/blog')
def blog_index():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 9
    with db() as con:
        total = con.execute('SELECT COUNT(*) FROM blog_posts WHERE is_published=1').fetchone()[0]
        posts = con.execute('SELECT * FROM blog_posts WHERE is_published=1 ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?', (per_page, (page-1)*per_page)).fetchall()
    return render_template('blog_index.html', posts=posts, page=page, pages=max(1,(total+per_page-1)//per_page), settings=get_settings())

@app.get('/blog/<slug>')
def blog_detail(slug):
    with db() as con:
        post = con.execute('SELECT * FROM blog_posts WHERE slug=? AND is_published=1', (slug,)).fetchone()
    if not post: abort(404)
    return render_template('blog_detail.html', post={**dict(post), 'content': Markup(clean_rich_html(post['content']))}, settings=get_settings())

@app.get('/robots.txt')
def robots():
    return app.response_class('User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: ' + request.url_root.rstrip('/') + '/sitemap.xml\n', mimetype='text/plain')

@app.get('/sitemap.xml')
def sitemap():
    from xml.sax.saxutils import escape
    with db() as con:
        ids = [r['id'] for r in con.execute('SELECT id FROM projects ORDER BY id DESC')]
    root = request.url_root.rstrip('/')
    with db() as con:
        slugs=[r['slug'] for r in con.execute('SELECT slug FROM service_categories')]
        page_slugs=[r['slug'] for r in con.execute('SELECT slug FROM custom_pages WHERE is_published=1')]
        blog_slugs=[r['slug'] for r in con.execute('SELECT slug FROM blog_posts WHERE is_published=1')]
    urls = [f'<url><loc>{escape(root)}/</loc></url>', f'<url><loc>{escape(root)}/blog</loc></url>'] + [f'<url><loc>{escape(root)}/project/{pid}</loc></url>' for pid in ids] + [f'<url><loc>{escape(root)}/service/{escape(slug)}</loc></url>' for slug in slugs] + [f'<url><loc>{escape(root)}/page/{escape(slug)}</loc></url>' for slug in page_slugs] + [f'<url><loc>{escape(root)}/blog/{escape(slug)}</loc></url>' for slug in blog_slugs]
    return app.response_class('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(urls) + '</urlset>', mimetype='application/xml')

@app.get('/api/public')
def public_data():
    with db() as con:
        projects = [dict(r) for r in con.execute('SELECT id,title,category,description,image,is_favorite FROM projects ORDER BY is_favorite DESC, id DESC')]
    with db() as con:
        categories = [dict(r) for r in con.execute('SELECT title,slug,description FROM service_categories ORDER BY id')]
    return jsonify({'settings':get_settings(),'projects':projects,'categories':categories})

@app.post('/api/contact')
def contact():
    data = request.get_json(silent=True) or request.form
    name = str(data.get('name','')).strip()[:120]
    phone = str(data.get('phone','')).strip()[:40]
    service = str(data.get('service','')).strip()[:120]
    message = str(data.get('message','')).strip()[:3000]
    if not name or not phone:
        return jsonify({'ok':False,'error':'نام و شماره تماس الزامی است.'}), 400
    with db() as con:
        con.execute('INSERT INTO messages(name,phone,service,message) VALUES(?,?,?,?)',(name,phone,service,message))
    return jsonify({'ok':True,'message':'درخواست شما ثبت شد. با شما تماس می‌گیریم.'})

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        if not valid_csrf(): abort(400, description='درخواست نامعتبر است؛ صفحه را تازه‌سازی کنید.')
        ip = request.remote_addr or 'unknown'
        attempts, started = LOGIN_ATTEMPTS.get(ip, (0, time.time()))
        if time.time() - started > 600: attempts, started = 0, time.time()
        if attempts >= 8:
            flash('تلاش‌های ورود زیاد است؛ ۱۰ دقیقه دیگر امتحان کنید.','error')
            return render_template('admin_login.html'), 429
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        with db() as con:
            user = con.execute('SELECT * FROM admins WHERE username=?',(username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            LOGIN_ATTEMPTS.pop(ip, None)
            session.clear(); session['admin_id'] = user['id']; session['admin_name'] = user['username']; session['csrf_token'] = secrets.token_urlsafe(32)
            return redirect(url_for('admin_dashboard'))
        LOGIN_ATTEMPTS[ip] = (attempts + 1, started)
        flash('نام کاربری یا رمز عبور اشتباه است.','error')
    return render_template('admin_login.html')

@app.post('/admin/logout')
@admin_required
def admin_logout():
    session.clear(); return redirect(url_for('admin_login'))

@app.get('/admin')
@admin_required
def admin_dashboard():
    with db() as con:
        projects = con.execute('SELECT * FROM projects ORDER BY id DESC').fetchall()
        messages = con.execute('SELECT * FROM messages ORDER BY id DESC LIMIT 100').fetchall()
        total_projects = con.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
        total_messages = con.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
        latest_message = con.execute('SELECT MAX(created_at) FROM messages').fetchone()[0]
        categories = con.execute('SELECT * FROM service_categories ORDER BY id').fetchall()
        pages = con.execute('SELECT * FROM custom_pages ORDER BY id DESC').fetchall()
        home_sections = con.execute('SELECT * FROM home_sections ORDER BY sort_order,id').fetchall()
        blog_posts = con.execute('SELECT * FROM blog_posts ORDER BY created_at DESC,id DESC').fetchall()
    return render_template('admin_dashboard.html', settings=get_settings(), projects=projects, messages=messages, total_projects=total_projects, total_messages=total_messages, latest_message=latest_message, categories=categories, pages=pages, home_sections=home_sections, blog_posts=blog_posts)

@app.get('/admin/builder')
@admin_required
def visual_builder():
    settings = get_settings()
    try: layout = json.loads(settings.get('visual_layout', '{}'))
    except (TypeError, ValueError): layout = {}
    return render_template('admin_builder.html', settings=settings, layout=layout)

@app.post('/admin/builder')
@admin_required
def save_visual_builder():
    allowed_sections = {'home','about','services','projects','statement','contact'}
    order = request.form.getlist('section_order')
    order = [x for x in order if x in allowed_sections]
    order = list(dict.fromkeys(order))
    order += [x for x in ['home','about','services','projects','statement','contact'] if x not in order]
    hidden = [x for x in request.form.getlist('hidden_sections') if x in allowed_sections]
    transition = request.form.get('transition', 'fade-up')
    if transition not in {'none','fade','fade-up','slide-left','zoom','flip','blur'}: transition = 'fade-up'
    try: duration = max(100, min(2000, int(request.form.get('duration','650'))))
    except ValueError: duration = 650
    accent = request.form.get('accent', '#c7a46b').strip()
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', accent): accent = '#c7a46b'
    try: radius = max(0, min(40, int(request.form.get('radius','14'))))
    except ValueError: radius = 14
    font = request.form.get('font', 'Tahoma').strip()
    if font not in {'Tahoma','Arial','Vazirmatn','sans-serif'}: font = 'Tahoma'
    hover = request.form.get('hover_effect','zoom')
    if hover not in {'none','zoom','lift','tilt'}: hover='zoom'
    gallery = request.form.get('gallery_layout','grid')
    if gallery not in {'grid','masonry','slider'}: gallery='grid'
    title_style = request.form.get('title_style','classic')
    if title_style not in {'classic','underline','center'}: title_style='classic'
    config = {'order':order, 'hidden':hidden, 'transition':transition, 'duration':duration, 'accent':accent, 'radius':radius, 'font':font, 'hover_effect':hover, 'gallery_layout':gallery, 'title_style':title_style}
    with db() as con:
        con.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', ('visual_layout', json.dumps(config, ensure_ascii=False)))
    flash('چیدمان و ظاهر سایت ذخیره شد.','success')
    return redirect(url_for('visual_builder'))

@app.get('/admin/posts')
@admin_required
def admin_posts():
    with db() as con:
        posts=con.execute('SELECT * FROM blog_posts ORDER BY created_at DESC,id DESC').fetchall()
    return render_template('admin_posts.html', posts=posts)

@app.get('/admin/posts/new')
@admin_required
def admin_post_new():
    return render_template('admin_post_editor.html', post=None)

@app.get('/admin/posts/<int:post_id>/edit')
@admin_required
def admin_post_edit(post_id):
    with db() as con:
        post=con.execute('SELECT * FROM blog_posts WHERE id=?',(post_id,)).fetchone()
    if not post: abort(404)
    return render_template('admin_post_editor.html', post=post)

def make_slug(value):
    value = re.sub(r'[^\w\u0600-\u06FF-]+', '-', value.strip().lower()).strip('-')
    return value[:70] or secrets.token_hex(4)

@app.post('/admin/categories/add')
@admin_required
def add_category():
    title=request.form.get('title','').strip()[:120]
    description=request.form.get('description','').strip()[:1000]
    if not title:
        flash('عنوان خدمت الزامی است.','error')
        return redirect(url_for('admin_dashboard')+'#categories')
    slug=make_slug(request.form.get('slug') or title)
    try:
        with db() as con: con.execute('INSERT INTO service_categories(title,slug,description) VALUES(?,?,?)',(title,slug,description))
        flash('عنوان خدمت و صفحه اختصاصی آن ساخته شد.','success')
    except sqlite3.IntegrityError:
        flash('عنوان یا نشانی این خدمت قبلاً ثبت شده است.','error')
    return redirect(url_for('admin_dashboard')+'#categories')

@app.post('/admin/categories/<int:cid>/delete')
@admin_required
def delete_category(cid):
    with db() as con:
        row=con.execute('SELECT title FROM service_categories WHERE id=?',(cid,)).fetchone()
        if row:
            con.execute('DELETE FROM service_categories WHERE id=?',(cid,))
    flash('خدمت حذف شد؛ نمونه‌کارهای قبلی حذف نمی‌شوند.','success')
    return redirect(url_for('admin_dashboard')+'#categories')

@app.post('/admin/sections/add')
@admin_required
def add_home_section():
    title=request.form.get('title','').strip()[:160]
    content=request.form.get('content','').strip()[:5000]
    if not title or not content:
        flash('عنوان و متن بخش الزامی است.','error')
    else:
        with db() as con:
            next_order=con.execute('SELECT COALESCE(MAX(sort_order),0)+1 FROM home_sections').fetchone()[0]
            con.execute('INSERT INTO home_sections(title,content,sort_order) VALUES(?,?,?)',(title,content,next_order))
        flash('بخش جدید به صفحه اصلی اضافه شد.','success')
    return redirect(url_for('admin_dashboard')+'#sections')

@app.post('/admin/sections/<int:sid>/delete')
@admin_required
def delete_home_section(sid):
    with db() as con: con.execute('DELETE FROM home_sections WHERE id=?',(sid,))
    flash('بخش صفحه اصلی حذف شد.','success')
    return redirect(url_for('admin_dashboard')+'#sections')

@app.post('/admin/pages/add')
@admin_required
def add_page():
    title=request.form.get('title','').strip()[:160]
    content=request.form.get('content','').strip()[:12000]
    slug=make_slug(request.form.get('slug') or title)
    if not title or not content:
        flash('عنوان و محتوای صفحه الزامی است.','error')
        return redirect(url_for('admin_dashboard')+'#pages')
    try:
        with db() as con: con.execute('INSERT INTO custom_pages(title,slug,content,meta_description) VALUES(?,?,?,?)',(title,slug,content,request.form.get('meta_description','').strip()[:300]))
        flash('صفحه جدید ساخته شد.','success')
    except sqlite3.IntegrityError:
        flash('این نشانی صفحه قبلاً استفاده شده است.','error')
    return redirect(url_for('admin_dashboard')+'#pages')

@app.post('/admin/pages/<int:pid>/delete')
@admin_required
def delete_page(pid):
    with db() as con: con.execute('DELETE FROM custom_pages WHERE id=?',(pid,))
    flash('صفحه حذف شد.','success')
    return redirect(url_for('admin_dashboard')+'#pages')

@app.post('/admin/blog/add')
@admin_required
def add_blog_post():
    title = request.form.get('title','').strip()[:180]
    content = clean_rich_html(request.form.get('content','').strip()[:30000])
    excerpt = request.form.get('excerpt','').strip()[:500]
    slug = make_slug(request.form.get('slug') or title)
    meta = request.form.get('meta_description','').strip()[:300]
    published = 1 if request.form.get('is_published') == 'on' else 0
    if not title or not content:
        flash('عنوان و متن مقاله الزامی است.','error')
        return redirect(url_for('admin_posts'))
    try:
        image = save_upload(request.files.get('image'))
    except ValueError as e:
        flash(str(e),'error')
        return redirect(url_for('admin_posts'))
    try:
        with db() as con:
            con.execute('INSERT INTO blog_posts(title,slug,excerpt,content,image,meta_description,is_published) VALUES(?,?,?,?,?,?,?)',
                        (title,slug,excerpt,content,image,meta,published))
        flash('مقاله ذخیره شد.','success')
    except sqlite3.IntegrityError:
        flash('این نشانی مقاله قبلاً استفاده شده است.','error')
    return redirect(url_for('admin_posts'))

@app.post('/admin/blog/<int:post_id>/edit')
@admin_required
def edit_blog_post(post_id):
    title = request.form.get('title','').strip()[:180]
    content = clean_rich_html(request.form.get('content','').strip()[:30000])
    excerpt = request.form.get('excerpt','').strip()[:500]
    meta = request.form.get('meta_description','').strip()[:300]
    published = 1 if request.form.get('is_published') == 'on' else 0
    if not title or not content:
        flash('عنوان و متن مقاله الزامی است.','error')
        return redirect(url_for('admin_posts'))
    try:
        image = save_upload(request.files.get('image'))
    except ValueError as e:
        flash(str(e),'error')
        return redirect(url_for('admin_posts'))
    with db() as con:
        old = con.execute('SELECT image FROM blog_posts WHERE id=?',(post_id,)).fetchone()
        if not old: abort(404)
        if image:
            con.execute('UPDATE blog_posts SET title=?,excerpt=?,content=?,image=?,meta_description=?,is_published=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                        (title,excerpt,content,image,meta,published,post_id))
        else:
            con.execute('UPDATE blog_posts SET title=?,excerpt=?,content=?,meta_description=?,is_published=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                        (title,excerpt,content,meta,published,post_id))
    flash('مقاله ویرایش شد.','success')
    return redirect(url_for('admin_posts'))

@app.post('/admin/blog/<int:post_id>/delete')
@admin_required
def delete_blog_post(post_id):
    with db() as con:
        row = con.execute('SELECT image FROM blog_posts WHERE id=?',(post_id,)).fetchone()
        if row:
            con.execute('DELETE FROM blog_posts WHERE id=?',(post_id,))
            if row['image'] and row['image'].startswith('/static/uploads/'):
                try: (BASE / row['image'].lstrip('/')).unlink(missing_ok=True)
                except OSError: pass
    flash('مقاله حذف شد.','success')
    return redirect(url_for('admin_posts'))

@app.post('/admin/settings')
@admin_required
def save_settings():
    values={key:request.form.get(key,'').strip()[:2000] for key in DEFAULTS if key in request.form}
    try:
        bg=save_upload(request.files.get('about_bg_image'))
        if bg: values['about_bg_image']=bg
        statement_bg=save_upload(request.files.get('statement_bg_image'))
        if statement_bg: values['statement_bg_image']=statement_bg
        font_file=request.files.get('custom_font')
        if font_file and font_file.filename:
            ext=font_file.filename.rsplit('.',1)[-1].lower() if '.' in font_file.filename else ''
            if ext not in FONT_ALLOWED: raise ValueError('فرمت فونت باید WOFF2، WOFF، TTF یا OTF باشد.')
            font_data=font_file.read(5*1024*1024+1)
            if len(font_data)>5*1024*1024: raise ValueError('حجم فونت نباید بیشتر از ۵ مگابایت باشد.')
            font_name=secrets.token_hex(12)+'.'+ext
            (UPLOAD_DIR/font_name).write_bytes(font_data)
            values['custom_font_url']='/static/uploads/'+font_name
            values['custom_font_format']={'ttf':'truetype','otf':'opentype','woff':'woff','woff2':'woff2'}[ext]
    except ValueError as e:
        flash(str(e),'error'); return redirect(url_for('admin_dashboard')+'#settings')
    with db() as con:
        for key,value in values.items():
            con.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
    flash('تنظیمات سایت ذخیره شد.','success')
    return redirect(url_for('admin_dashboard')+'#settings')

@app.post('/admin/blog/image-upload')
@admin_required
def blog_image_upload():
    try: image=save_upload(request.files.get('image'))
    except ValueError as e: return jsonify({'ok':False,'error':str(e)}),400
    if not image: return jsonify({'ok':False,'error':'تصویری انتخاب نشده است.'}),400
    return jsonify({'ok':True,'url':image})

def save_upload(file):
    if not file or not file.filename: return ''
    filename = secure_filename(file.filename)
    if '.' not in filename or filename.rsplit('.',1)[1].lower() not in ALLOWED:
        raise ValueError('فرمت تصویر باید JPG، PNG، WEBP یا GIF باشد.')
    ext = filename.rsplit('.',1)[1].lower()
    name = secrets.token_hex(12)+'.'+ext
    file.save(UPLOAD_DIR/name)
    return '/static/uploads/'+name

@app.post('/admin/projects/add')
@admin_required
def add_project():
    title=request.form.get('title','').strip(); category=request.form.get('category','').strip(); description=request.form.get('description','').strip()
    if not title or not category:
        flash('عنوان و دسته‌بندی پروژه الزامی است.','error'); return redirect(url_for('admin_dashboard')+'#projects')
    try: image=save_upload(request.files.get('image'))
    except ValueError as e:
        flash(str(e),'error'); return redirect(url_for('admin_dashboard')+'#projects')
    with db() as con: con.execute('INSERT INTO projects(title,category,description,image) VALUES(?,?,?,?)',(title,category,description,image))
    flash('نمونه‌کار اضافه شد.','success'); return redirect(url_for('admin_dashboard')+'#projects')

@app.post('/admin/projects/<int:pid>/edit')
@admin_required
def edit_project(pid):
    title=request.form.get('title','').strip(); category=request.form.get('category','').strip(); description=request.form.get('description','').strip()
    try: image=save_upload(request.files.get('image'))
    except ValueError as e:
        flash(str(e),'error'); return redirect(url_for('admin_dashboard')+'#projects')
    with db() as con:
        old=con.execute('SELECT image FROM projects WHERE id=?',(pid,)).fetchone()
        if not old: abort(404)
        if image:
            con.execute('UPDATE projects SET title=?,category=?,description=?,image=? WHERE id=?',(title,category,description,image,pid))
        else:
            con.execute('UPDATE projects SET title=?,category=?,description=? WHERE id=?',(title,category,description,pid))
    flash('نمونه‌کار ویرایش شد.','success'); return redirect(url_for('admin_dashboard')+'#projects')

@app.post('/admin/projects/<int:pid>/delete')
@admin_required
def delete_project(pid):
    with db() as con:
        row=con.execute('SELECT image FROM projects WHERE id=?',(pid,)).fetchone()
        if row:
            con.execute('DELETE FROM projects WHERE id=?',(pid,))
            if row['image'].startswith('/static/uploads/'):
                try: (BASE / row['image'].lstrip('/')).unlink(missing_ok=True)
                except OSError: pass
    flash('نمونه‌کار حذف شد.','success'); return redirect(url_for('admin_dashboard')+'#projects')

@app.post('/admin/projects/<int:pid>/favorite')
@admin_required
def toggle_favorite(pid):
    with db() as con:
        row = con.execute('SELECT is_favorite FROM projects WHERE id=?', (pid,)).fetchone()
        if not row: abort(404)
        con.execute('UPDATE projects SET is_favorite=? WHERE id=?', (0 if row['is_favorite'] else 1, pid))
    flash('وضعیت محبوبیت نمونه‌کار تغییر کرد.', 'success')
    return redirect(url_for('admin_dashboard') + '#projects')

@app.post('/admin/messages/<int:mid>/delete')
@admin_required
def delete_message(mid):
    with db() as con: con.execute('DELETE FROM messages WHERE id=?',(mid,))
    flash('پیام حذف شد.','success'); return redirect(url_for('admin_dashboard')+'#messages')

@app.post('/admin/password')
@admin_required
def change_password():
    current=request.form.get('current',''); new=request.form.get('new','')
    with db() as con:
        user=con.execute('SELECT * FROM admins WHERE id=?',(session['admin_id'],)).fetchone()
        if not user or not check_password_hash(user['password_hash'],current):
            flash('رمز فعلی صحیح نیست.','error')
        elif len(new)<12:
            flash('رمز جدید باید حداقل ۱۲ نویسه باشد.','error')
        else:
            con.execute('UPDATE admins SET password_hash=? WHERE id=?',(generate_password_hash(new),session['admin_id']))
            flash('رمز عبور تغییر کرد.','success')
    return redirect(url_for('admin_dashboard')+'#password')

@app.get('/admin/export/messages.csv')
@admin_required
def export_messages():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['نام', 'تلفن', 'موضوع', 'پیام', 'تاریخ'])
    with db() as con:
        for row in con.execute('SELECT name,phone,service,message,created_at FROM messages ORDER BY id DESC'):
            writer.writerow(list(row))
    data = ('\ufeff' + output.getvalue()).encode('utf-8')
    return send_file(io.BytesIO(data), mimetype='text/csv; charset=utf-8', as_attachment=True, download_name='kazemi-messages.csv')

@app.get('/admin/backup')
@admin_required
def backup_database():
    if not DB.exists(): abort(404)
    return send_file(DB, mimetype='application/x-sqlite3', as_attachment=True, download_name='kazemi-backup.sqlite3')

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)

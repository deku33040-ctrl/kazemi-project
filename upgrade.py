from pathlib import Path
import re, shutil
base=Path('/mnt/data/kazemi_work')
app=base/'app.py'; s=app.read_text()
# add html parser imports
s=s.replace('import os, sqlite3, secrets, io, csv, time, json, re', 'import os, sqlite3, secrets, io, csv, time, json, re\nfrom html import escape\nfrom html.parser import HTMLParser')
# defaults
s=s.replace("'experience':'۱۰+', 'projectsCount':'۷۰+', 'phone':'', 'address':'',", "'experience':'۱۰+', 'projectsCount':'۷۰+', 'phone':'', 'whatsapp_number':'', 'telegram_url':'', 'address':'',\n 'hero_eyebrow':'تخصص، دقت، ماندگاری', 'hero_title':'سنگ را با هنر\u003cbr\u003eو سازه را با اعتماد بسازید.',\n 'hero_button_projects':'مشاهده نمونه‌کارها', 'hero_button_contact':'درخواست مشاوره',\n 'about_label':'۰۱ / درباره پیمانکاری کاظمی', 'about_title':'ساختن فقط اجرا نیست؛ تعهد به نتیجه است.',\n 'about_link':'برای شروع همکاری با ما تماس بگیرید', 'services_label':'۰۲ / خدمات ما',\n 'services_title':'تخصص‌هایی برای ساخت بهتر', 'services_intro':'خدمات اجرایی با توجه به کیفیت مصالح، دقت نصب و نیاز واقعی هر پروژه.',\n 'projects_label':'۰۳ / پروژه‌ها', 'projects_title':'نتیجه کار، معرف ماست',\n 'projects_intro':'نمونه‌کارهای واقعی و جزئیات پروژه‌های اجراشده را مشاهده کنید.',\n 'about_image':'',")
# csrf header
s=s.replace("return secrets.compare_digest(str(session.get('csrf_token', '')), str(request.form.get('csrf_token', '')))\n", "token = request.form.get('csrf_token', '') or request.headers.get('X-CSRF-Token', '')\n    return secrets.compare_digest(str(session.get('csrf_token', '')), str(token))\n")
# sanitizer class before app
needle="BASE = Path(__file__).resolve().parent"
s=s.replace(needle, '''class ArticleSanitizer(HTMLParser):
    allowed = {'p','br','strong','b','em','i','u','s','h2','h3','h4','ul','ol','li','blockquote','a','img','hr','pre','code','table','thead','tbody','tr','th','td','figure','figcaption'}
    void = {'br','img','hr'}
    blocked = {'script','style','iframe','object','embed','form','input','button'}
    def __init__(self):
        super().__init__(convert_charrefs=True); self.out=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in self.blocked: self.skip += 1; return
        if self.skip or tag not in self.allowed: return
        attrs=dict(attrs); safe=[]
        if tag=='a':
            href=attrs.get('href','')
            if href.startswith(('https://','http://','mailto:','/')): safe.append(('href',href))
            safe.extend([('target','_blank'),('rel','noopener noreferrer')])
        if tag=='img':
            src=attrs.get('src','')
            if not src.startswith('/static/uploads/'): return
            safe += [('src',src),('alt',attrs.get('alt','')[:250]),('loading','lazy')]
            for key in ('width','height'): 
                if attrs.get(key,'').isdigit(): safe.append((key,attrs[key]))
        if tag in ('th','td') and attrs.get('colspan','').isdigit(): safe.append(('colspan',attrs['colspan']))
        self.out.append('<'+tag+''.join(f' {k}="{escape(v, quote=True)}"' for k,v in safe)+'>')
    def handle_endtag(self, tag):
        if tag in self.blocked:
            if self.skip: self.skip-=1
            return
        if not self.skip and tag in self.allowed and tag not in self.void: self.out.append(f'</{tag}>')
    def handle_data(self, data):
        if not self.skip: self.out.append(escape(data))
    def result(self): return ''.join(self.out)

def clean_article_html(value):
    parser=ArticleSanitizer(); parser.feed(value or ''); return parser.result()

'''+needle)
# sanitize content when save
s=s.replace("content = request.form.get('content','').strip()[:30000]", "content = clean_article_html(request.form.get('content','').strip()[:30000])")
# about image route before settings
needle="@app.post('/admin/settings')"
s=s.replace(needle, '''@app.post('/admin/about-image')
@admin_required
def upload_about_image():
    try: image=save_upload(request.files.get('image'))
    except ValueError as e:
        flash(str(e),'error'); return redirect(url_for('admin_dashboard')+'#settings')
    if image:
        with db() as con:
            con.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('about_image',image))
        flash('تصویر پس‌زمینه درباره ما تغییر کرد.','success')
    return redirect(url_for('admin_dashboard')+'#settings')

@app.post('/admin/blog/upload-image')
@admin_required
def upload_blog_inline_image():
    try: image=save_upload(request.files.get('image'))
    except ValueError as e: return jsonify({'ok':False,'error':str(e)}),400
    if not image: return jsonify({'ok':False,'error':'تصویری انتخاب نشده است.'}),400
    return jsonify({'ok':True,'url':image})

'''+needle)
# blog display safe
app.write_text(s)

# update home template
p=base/'templates/index.html'; t=p.read_text()
t=t.replace('<section class="intro section" id="about">','<section class="intro section about-background" id="about" style="--about-image:url(\'{{ settings.about_image }}\')">')
t=t.replace('<div class="eyebrow"><span></span> تخصص، دقت، ماندگاری</div>', '<div class="eyebrow"><span></span> {{ settings.hero_eyebrow }}</div>')
t=t.replace('<h1>سنگ را با هنر<br>و سازه را با <em>اعتماد</em> بسازید.</h1>', '<h1>{{ settings.hero_title|safe }}</h1>')
t=t.replace('مشاهده نمونه‌کارها <b>↙</b>', '{{ settings.hero_button_projects }}')
t=t.replace('درخواست مشاوره</a>', '{{ settings.hero_button_contact }}</a>',1)
t=t.replace('۰۱ / درباره پیمانکاری کاظمی</div>', '{{ settings.about_label }}</div>')
t=t.replace('ساختن فقط اجرا نیست؛<br><em>تعهد به نتیجه است.</em></h2>', '{{ settings.about_title }}</h2>')
t=t.replace('برای شروع همکاری با ما تماس بگیرید <span>↙</span>', '{{ settings.about_link }}')
t=t.replace('۰۲ / خدمات ما</div>', '{{ settings.services_label }}</div>')
t=t.replace('تخصص‌هایی برای <em>ساخت بهتر</em></h2>', '{{ settings.services_title }}</h2>')
t=t.replace('خدمات اجرایی با توجه به کیفیت مصالح، دقت نصب و نیاز واقعی هر پروژه.</p>', '{{ settings.services_intro }}</p>',1)
t=t.replace('{% for c in categories %}<article class="service reveal"><span class="number">{{ \'%02d\'|format(loop.index) }}</span><span class="service-symbol">▧</span><div><h3>{{c.title}}</h3><p>{{c.description}}</p></div><a href="{{url_for(\'service_detail\',slug=c.slug)}}" aria-label="مشاهده {{c.title}}">↙</a></article>{% endfor %}', '{% for c in categories %}<a class="service reveal service-link" href="{{url_for(\'service_detail\',slug=c.slug)}}" aria-label="مشاهده {{c.title}}"><span class="number">{{ \'%02d\'|format(loop.index) }}</span><span class="service-symbol">▧</span><div><h3>{{c.title}}</h3><p>{{c.description}}</p></div></a>{% endfor %}')
t=t.replace('۰۳ / پروژه‌ها</div>', '{{ settings.projects_label }}</div>')
t=t.replace('نتیجه کار، <em>معرف ماست</em></h2>', '{{ settings.projects_title }}</h2>')
t=t.replace('نمونه‌کارهای واقعی و جزئیات پروژه‌های اجراشده را مشاهده کنید.</p>', '{{ settings.projects_intro }}</p>',1)
t=t.replace('href="tel:+93700000000"', 'href="tel:{{ settings.phone }}"')
t=t.replace('href="https://wa.me/93700000000"', 'href="https://wa.me/{{ settings.whatsapp_number }}"')
t=t.replace('<b>ارسال پیام در واتساپ ↙</b>', '<b>ارسال پیام در واتساپ</b>')
t=t.replace('<div class="contact-lines">', '<div class="contact-lines">')
t=t.replace('<footer><a class="logo"', '<div class="floating-contact" aria-label="راه‌های ارتباطی"><a class="float-call" href="tel:{{settings.phone}}" aria-label="تماس"><span>☎</span></a>{% if settings.whatsapp_number %}<a class="float-wa" href="https://wa.me/{{settings.whatsapp_number}}" target="_blank" rel="noopener" aria-label="واتساپ"><span>◉</span></a>{% endif %}{% if settings.telegram_url %}<a class="float-tg" href="{{settings.telegram_url}}" target="_blank" rel="noopener" aria-label="تلگرام"><span>➤</span></a>{% endif %}</div>\n<footer><a class="logo"')
# append CSS
style='''\n<style>
.service-link{display:flex;align-items:center;gap:22px;color:inherit;text-decoration:none;cursor:pointer;transition:transform .3s,box-shadow .3s}
.service-link:hover{transform:translateY(-7px);box-shadow:0 18px 38px #101a2a22}
.service-link .service-symbol{flex:0 0 auto}.service-link>div{flex:1}.service-link:after{content:none!important}
.about-background{position:relative;isolation:isolate;overflow:hidden;border-radius:28px}
.about-background:before{content:"";position:absolute;inset:0;z-index:-2;background-image:var(--about-image);background-size:cover;background-position:center;filter:blur(5px);transform:scale(1.06);opacity:.27}
.about-background:after{content:"";position:absolute;inset:0;z-index:-1;background:linear-gradient(115deg,rgba(248,249,251,.94),rgba(238,242,247,.82));pointer-events:none}
.floating-contact{position:fixed;right:18px;bottom:22px;z-index:9999;display:flex;flex-direction:column;gap:10px}
.floating-contact a{width:52px;height:52px;border-radius:50%;display:grid;place-items:center;color:white;text-decoration:none;font-size:23px;box-shadow:0 8px 24px #07152b40;transition:transform .25s}
.floating-contact a:hover{transform:translateY(-4px) scale(1.05)}.float-call{background:#132b4b}.float-wa{background:#159b61}.float-tg{background:#168bc4}
@media(max-width:700px){.floating-contact{right:12px;bottom:14px}.floating-contact a{width:46px;height:46px}}
</style>\n'''
t=t.replace('</head>',style+'</head>')
p.write_text(t)

# Blog detail render sanitized HTML
p=base/'templates/blog_detail.html'; t=p.read_text().replace('{{post.content}}</div>', '{{post.content|safe}}</div>'); p.write_text(t)

# admin dashboard theme and forms
p=base/'templates/admin_dashboard.html'; t=p.read_text()
t=t.replace(':root{--bg:#101510;--panel:#1b211b;--line:#343b31;--gold:#c8a65b;--txt:#f4f1e8;--muted:#b9b9aa}', ':root{--bg:#f3f6fb;--panel:#ffffff;--line:#dce3ed;--gold:#17365d;--txt:#17263c;--muted:#64748b}')
t=t.replace('background:#101510ee;', 'background:#ffffffed;')
t=t.replace('background:#111711;color:white;border:1px solid #485044', 'background:#fff;color:#17263c;border:1px solid #cbd5e1')
t=t.replace('.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px;margin:18px 0}', '.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px;margin:18px 0;box-shadow:0 8px 28px #1831530b}')
t=t.replace('button,.btn{background:var(--gold);color:#151711;', 'button,.btn{background:var(--gold);color:#ffffff;')
# replace blog content textareas with editor wrapper, preserving name hidden field
# New article exact textarea
old='<label>متن مقاله</label><textarea name="content" rows="10" required placeholder="متن کامل مقاله را بنویسید..."></textarea>'
new='<label>متن مقاله</label><div class="rich-editor" data-editor><div class="editor-toolbar"><button type="button" data-cmd="bold">B</button><button type="button" data-cmd="italic"><i>I</i></button><button type="button" data-cmd="underline">U</button><button type="button" data-block="h2">تیتر ۲</button><button type="button" data-block="h3">تیتر ۳</button><button type="button" data-block="p">پاراگراف</button><button type="button" data-cmd="insertUnorderedList">فهرست</button><button type="button" data-cmd="insertOrderedList">شماره‌گذاری</button><button type="button" data-cmd="justifyRight">راست‌چین</button><button type="button" data-cmd="justifyCenter">وسط</button><button type="button" data-link>لینک</button><button type="button" data-image>درج تصویر</button><input type="file" accept="image/*" data-image-file hidden></div><div class="editor-area" contenteditable="true" data-placeholder="متن مقاله را اینجا بنویسید..."></div><textarea name="content" hidden required></textarea></div>'
t=t.replace(old,new)
old2='<label>متن مقاله</label><textarea name="content" rows="8" required>{{post.content}}</textarea>'
new2='<label>متن مقاله</label><div class="rich-editor" data-editor><div class="editor-toolbar"><button type="button" data-cmd="bold">B</button><button type="button" data-cmd="italic"><i>I</i></button><button type="button" data-cmd="underline">U</button><button type="button" data-block="h2">تیتر ۲</button><button type="button" data-block="h3">تیتر ۳</button><button type="button" data-block="p">پاراگراف</button><button type="button" data-cmd="insertUnorderedList">فهرست</button><button type="button" data-cmd="insertOrderedList">شماره‌گذاری</button><button type="button" data-cmd="justifyRight">راست‌چین</button><button type="button" data-cmd="justifyCenter">وسط</button><button type="button" data-link>لینک</button><button type="button" data-image>درج تصویر</button><input type="file" accept="image/*" data-image-file hidden></div><div class="editor-area" contenteditable="true">{{post.content|safe}}</div><textarea name="content" hidden required></textarea></div>'
t=t.replace(old2,new2)
# settings inputs
old3="{% for key,label in [('company','نام شرکت'),('slogan','شعار'),('phone','شماره تماس با کد کشور'),('address','شهر و آدرس فعالیت'),('experience','سابقه کاری نمایشی'),('projectsCount','تعداد پروژه نمایشی'),('seo_title','عنوان سئو'),('seo_description','توضیحات سئو')] %}"
new3="{% for key,label in [('company','نام شرکت'),('slogan','شعار'),('phone','شماره تماس با کد کشور'),('whatsapp_number','شماره واتساپ با کد کشور، فقط عدد'),('telegram_url','لینک تلگرام یا شناسه کامل'),('address','شهر و آدرس فعالیت'),('experience','سابقه کاری نمایشی'),('projectsCount','تعداد پروژه نمایشی'),('seo_title','عنوان سئو'),('seo_description','توضیحات سئو')] %}"
t=t.replace(old3,new3)
# Insert all homepage text fields in settings after about text
marker='<label>جمله پایانی</label><textarea name="quote">{{settings.quote}}</textarea>'
extra=marker+'''<h3>ویرایش متن‌های صفحه اصلی</h3><div class="grid">{% for key,label in [('hero_eyebrow','متن کوچک بالای تیتر اصلی'),('hero_title','تیتر اصلی (برای خط جدید از &lt;br&gt; استفاده کن)'),('hero_button_projects','متن دکمه نمونه‌کارها'),('hero_button_contact','متن دکمه مشاوره'),('about_label','برچسب درباره ما'),('about_title','تیتر درباره ما'),('about_link','متن لینک درباره ما'),('services_label','برچسب خدمات'),('services_title','تیتر خدمات'),('services_intro','توضیح خدمات'),('projects_label','برچسب نمونه‌کارها'),('projects_title','تیتر نمونه‌کارها'),('projects_intro','توضیح نمونه‌کارها')] %}<div><label>{{label}}</label><input name="{{key}}" value="{{settings.get(key,'')}}"></div>{% endfor %}</div>'''
t=t.replace(marker,extra)
# add about image upload block before close settings panel section (near button)
needle='<button>ذخیره اطلاعات سایت</button></form></section>'
rep='<button>ذخیره اطلاعات سایت</button></form><hr><h3>تصویر پس‌زمینه بخش درباره ما</h3>{% if settings.about_image %}<p><img class="thumb" src="{{settings.about_image}}" alt="تصویر فعلی درباره ما"></p>{% endif %}<form method="post" action="/admin/about-image" enctype="multipart/form-data"><input type="hidden" name="csrf_token" value="{{csrf_token}}"><label>انتخاب تصویر جدید</label><input type="file" name="image" accept="image/jpeg,image/png,image/webp" required><button>تغییر تصویر درباره ما</button></form></section>'
t=t.replace(needle,rep)
# Add editor CSS and JS before final script
editor_css='''<style>
body{background:#f3f6fb!important;color:#17263c!important}.top{box-shadow:0 3px 18px #1c35520d}.nav a{background:#fff;color:#17365d;border-color:#dce3ed}.panel h2{color:#17365d}.small,.muted{color:#64748b}.rich-editor{border:1px solid #cbd5e1;border-radius:12px;background:#fff;overflow:hidden;margin:8px 0 18px}.editor-toolbar{display:flex;gap:6px;flex-wrap:wrap;padding:10px;background:#edf2f8;border-bottom:1px solid #dce3ed}.editor-toolbar button{padding:7px 11px;background:#17365d;color:white;border-radius:6px}.editor-area{min-height:260px;padding:18px;outline:none;color:#17263c;line-height:2;font-size:15px}.editor-area:empty:before{content:attr(data-placeholder);color:#94a3b8}.editor-area img{max-width:100%;height:auto;border-radius:10px;display:block;margin:18px auto}.editor-area h2,.editor-area h3{color:#17365d}.editor-area blockquote{border-right:4px solid #17365d;padding:10px 16px;background:#f1f5f9}.editor-area table{border-collapse:collapse;width:100%}.editor-area td,.editor-area th{border:1px solid #cbd5e1;padding:8px}
</style>
<script>
document.querySelectorAll('[data-editor]').forEach(editor=>{const area=editor.querySelector('.editor-area'), hidden=editor.querySelector('textarea[name="content"]'), form=editor.closest('form');const sync=()=>hidden.value=area.innerHTML;editor.querySelectorAll('[data-cmd]').forEach(b=>b.addEventListener('click',()=>{area.focus();document.execCommand(b.dataset.cmd,false,null);sync()}));editor.querySelectorAll('[data-block]').forEach(b=>b.addEventListener('click',()=>{area.focus();document.execCommand('formatBlock',false,b.dataset.block);sync()}));editor.querySelector('[data-link]').addEventListener('click',()=>{area.focus();const url=prompt('آدرس لینک را وارد کنید');if(url)document.execCommand('createLink',false,url);sync()});const picker=editor.querySelector('[data-image-file]');editor.querySelector('[data-image]').addEventListener('click',()=>picker.click());picker.addEventListener('change',async()=>{if(!picker.files[0])return;const fd=new FormData();fd.append('image',picker.files[0]);try{const res=await fetch('/admin/blog/upload-image',{method:'POST',headers:{'X-CSRF-Token':document.querySelector('input[name="csrf_token"]').value},body:fd});const data=await res.json();if(!res.ok)throw new Error(data.error||'خطا در آپلود');area.focus();document.execCommand('insertHTML',false,'<p><img src="'+data.url+'" alt="تصویر مقاله"></p>');sync()}catch(e){alert(e.message)}picker.value=''});form.addEventListener('submit',sync);sync()});
</script>
'''
t=t.replace('</body>',editor_css+'</body>')
p.write_text(t)

# Upload user's supplied background image into the project static folder
uploads=base/'static'/'uploads'; uploads.mkdir(parents=True,exist_ok=True)
shutil.copy2('/mnt/data/IMG_fda8c143-8d1f-4566-990d-70a9b38fae4b.jpg',uploads/'about-stone-background.jpg')
# Set default about image in settings database seed
app=base/'app.py'; s=app.read_text().replace("'about_image':'',", "'about_image':'/static/uploads/about-stone-background.jpg',")
app.write_text(s)

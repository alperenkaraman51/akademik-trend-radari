# Google Stitch ile Tasarlama ve Yayına Alma Rehberi

Kurulan sistem iki katmandan oluşur ve **Google Stitch (`stitch.withgoogle.com`)** ile %100 uyumlu olacak şekilde **Tailwind CSS + HTML** mimarisiyle hazırlanmıştır:

1. **[index.html](file:///C:/Users/Alperen/.gemini/antigravity/scratch/akademik_trend/index.html)**: Kurulum gerektirmeden doğrudan çift tıklayarak tarayıcıda çalışan, anahtar kelimeleri girdiğinizde **makale başlıklarını, yıllarını, tam özetlerini (abstract), atıf sayılarını, Google Akademik bağlantılarını** ve **yıl bazlı makale trend grafiklerini** gösteren hazır web uygulaması.
2. **[app.py](file:///C:/Users/Alperen/.gemini/antigravity/scratch/akademik_trend/app.py)**: Doğrudan **Google Akademik (`scholar.google.com`)** sayfalarını tarayıp tam özet verileriyle birleştiren Python (Flask) arka uç servisi.

---

## 1. Google Stitch'te Özel Tasarım Üretmek İçin Hazır Prompt

[stitch.withgoogle.com](https://stitch.withgoogle.com) adresine gidip aşağıdaki metni yapıştırarak alternatif arayüz tasarımları üretebilirsiniz:

```text
Design a modern dark-mode Academic Literature & Publication Trend Analytics Dashboard called "ScholarPulse".
Include:
1. Top search bar section with:
   - Primary keywords input (OR logic)
   - Secondary keywords input (AND logic)
   - Publisher filter dropdown (All, Elsevier, Taylor & Francis, Springer Nature, Wiley, IEEE, MDPI)
   - Start year and End year inputs, plus a primary "Analyze" button.
2. 4 KPI summary cards: Total Articles, Peak Publication Year, Period Growth %, and Top Publisher.
3. Two side-by-side chart containers:
   - "Yearly Publication Volume Trend" (bar chart)
   - "Publisher Comparison Trend (Elsevier, Taylor & Francis, Springer, IEEE, Wiley)" (multi-line chart)
4. "Academic Articles Feed" section with search/sort controls and cards showing:
   - Publication Year badge, Publisher badge, and Citation count badge
   - Article Title, Authors & Journal subtitle
   - Expandable full Abstract box with highlighted keywords
   - "Open in Google Scholar" and "PDF" action buttons, plus a "Download CSV" button.
```

---

## 2. Google Stitch Kodunu Sisteme Bağlama

Google Stitch tasarımınızı beğendiğinizde sağ üstteki **"Export Code" -> "HTML / Tailwind"** çıktısını kopyalayın.
- Tasarımdaki arama kutularına ve grafik/liste alanlarına `index.html` içindeki şu `id`'leri vermeniz yeterlidir (veya Stitch kodunu buraya yapıştırırsanız sizin için saniyeler içinde bağlayabilirim):
  - Anahtar kelime kutuları: `id="keywords1"`, `id="keywords2"`
  - Yıl kutuları ve yayıncı: `id="startYear"`, `id="endYear"`, `id="publisherSelect"`
  - Grafik kanvasları: `id="yearlyTotalChart"`, `id="publisherTrendChart"`
  - Makale listesi alanı: `id="articlesContainer"`

---

## 3. Sistemi Yayına Alma (Deployment) Seçenekleri

### Seçenek A: Sadece Ön Yüz (Ücretsiz & 30 Saniyede Yayında — Netlify / Vercel / GitHub Pages)
`index.html` dosyası tarayıcı üzerinden doğrudan canlı akademik API'lerle konuşabildiği için sunucu kurmadan:
1. [app.netlify.com/drop](https://app.netlify.com/drop) sayfasına gidin.
2. `C:\Users\Alperen\.gemini\antigravity\scratch\akademik_trend` klasörünü sürükleyip bırakın.
3. Siteniz anında herkese açık bir URL ile yayına girer.

### Seçenek B: Python Google Akademik Sunucusu ile Yayına Alma (Render / Railway)
1. Klasörü bir GitHub deposuna yükleyin.
2. **Render.com** veya **Railway.app** üzerinde yeni bir Web Service oluşturun.
3. Başlatma komutu olarak `python app.py` (veya `gunicorn app:app`) tanımlayın.
4. Yoğun trafik altında Google Akademik CAPTCHA engeline takılmamak için ortam değişkenlerine (`Environment Variables`) isteğe bağlı `SERPAPI_KEY` ekleyebilirsiniz.

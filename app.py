"""
Google Akademik (Google Scholar) Tabanlı Makale ve Trend Analiz Sistemi (Backend API)
-------------------------------------------------------------------------------------
Kurulum:
    pip install flask flask-cors requests beautifulsoup4 pandas

Çalıştırma:
    python app.py

Tarayıcıda açın:
    http://localhost:5000
"""
import os
import re
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder=".")

# CORS başlıkları (Google Stitch veya ayrı bir frontend portundan bağlanabilmek için)
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

OA_API = "https://api.openalex.org"
S2_API = "https://api.semanticscholar.org/graph/v1"


# ===================== SORGULAMA YARDIMCILARI =====================
def virgulle_ayir(metin):
    if not metin:
        return []
    return [t.strip() for t in metin.split(",") if t.strip()]


def sorgu_olustur(grup1_str, grup2_str="", yayinci=""):
    grup1 = virgulle_ayir(grup1_str)
    grup2 = virgulle_ayir(grup2_str)

    def or_blok(liste):
        parcalar = [f'"{k}"' if " " in k else k for k in liste]
        return "(" + " OR ".join(parcalar) + ")" if len(parcalar) > 1 else parcalar[0]

    bloklar = []
    if grup1:
        bloklar.append(or_blok(grup1))
    if grup2:
        bloklar.append(or_blok(grup2))
    if yayinci and yayinci.lower() != "all":
        bloklar.append(f'"{yayinci}"')

    return " AND ".join(bloklar)


def ters_indeks_coz(inv_idx):
    """OpenAlex abstract_inverted_index yapısını düz metne çevirir."""
    if not inv_idx or not isinstance(inv_idx, dict):
        return ""
    kelime_poz = []
    for kelime, pozisyonlar in inv_idx.items():
        for p in pozisyonlar:
            kelime_poz.append((p, kelime))
    kelime_poz.sort(key=lambda x: x[0])
    return " ".join(k for _, k in kelime_poz)


# ===================== GOOGLE AKADEMİK (GOOGLE SCHOLAR) TARAYICI =====================
def google_scholar_sayfa_cek(sorgu, bas_yil, bit_yil, baslangic_kayit=0, serpapi_key=None):
    """
    Google Akademik'ten makale başlığı, yılı, özeti (snippet), yazar/yayıncı bilgisi ve atıf sayısını çeker.
    Eğer SERPAPI_KEY verilmişse SerpApi üzerinden, verilmemişse doğrudan Google Scholar üzerinden çeker.
    """
    makaleler = []
    toplam_tahmin = 0

    # 1) SerpApi varsa kullan (Production / Yayına alındığında CAPTCHA engeline takılmamak için)
    if serpapi_key:
        params = {
            "engine": "google_scholar",
            "q": sorgu,
            "as_ylo": bas_yil,
            "as_yhi": bit_yil,
            "start": baslangic_kayit,
            "num": 20,
            "api_key": serpapi_key,
        }
        r = requests.get("https://serpapi.com/search.json", params=params, timeout=25)
        if r.status_code == 200:
            data = r.json()
            toplam_tahmin = data.get("search_information", {}).get("total_results", 0)
            for item in data.get("organic_results", []):
                pub_info = item.get("publication_info", {}).get("summary", "")
                yil_eslesme = re.search(r"\b(19\d\d|20\d\d)\b", pub_info)
                yil = int(yil_eslesme.group(1)) if yil_eslesme else None
                atifi = item.get("inline_links", {}).get("cited_by", {}).get("total", 0)
                pdf_link = None
                if item.get("resources"):
                    pdf_link = item["resources"][0].get("link")

                makaleler.append({
                    "title": item.get("title", ""),
                    "year": yil,
                    "abstract": item.get("snippet", ""),
                    "authors_venue": pub_info,
                    "url": item.get("link", ""),
                    "pdf_url": pdf_link,
                    "citations": atifi,
                    "source": "Google Akademik (SerpApi)",
                })
            return makaleler, toplam_tahmin, None

    # 2) Doğrudan Google Akademik HTML Taraması
    params = {
        "q": sorgu,
        "as_ylo": bas_yil,
        "as_yhi": bit_yil,
        "start": baslangic_kayit,
        "hl": "tr",
    }
    url = "https://scholar.google.com/scholar?" + urllib.parse.urlencode(params)
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code in (429, 403) or "gs_captcha_ccl" in r.text or "unusual traffic" in r.text.lower():
            return [], 0, "CAPTCHA_OR_RATE_LIMIT"
        r.raise_for_status()
    except Exception as e:
        return [], 0, str(e)

    soup = BeautifulSoup(r.text, "html.parser")

    # Toplam sonuç sayısını yakala (örn: "Yaklaşık 14.200 sonuç")
    ab_md = soup.find("div", id="gs_ab_md")
    if ab_md:
        sayi_eslesme = re.search(r"([\d\.,]+)\s*(sonuç|results)", ab_md.get_text(), re.IGNORECASE)
        if sayi_eslesme:
            temiz = re.sub(r"[^\d]", "", sayi_eslesme.group(1))
            if temiz.isdigit():
                toplam_tahmin = int(temiz)

    for blok in soup.select("div.gs_r.gs_or.gs_scl"):
        baslik_el = blok.select_one("h3.gs_rt")
        if not baslik_el:
            continue

        # [PDF], [HTML], [KİTAP] gibi etiketleri temizle
        for span in baslik_el.select("span.gs_ctu, span.gs_ctc"):
            span.decompose()

        link_el = baslik_el.find("a")
        baslik = baslik_el.get_text(strip=True)
        makale_url = link_el["href"] if link_el and link_el.has_attr("href") else ""

        # Yazarlar, Dergi, Yıl ve Yayıncı satırı (div.gs_a)
        meta_el = blok.select_one("div.gs_a")
        meta_metin = meta_el.get_text(" ", strip=True) if meta_el else ""
        yil_eslesme = re.search(r"\b(19\d\d|20\d\d)\b", meta_metin)
        yil = int(yil_eslesme.group(1)) if yil_eslesme else None

        # Özet (Snippet - div.gs_rs)
        ozet_el = blok.select_one("div.gs_rs")
        ozet = ozet_el.get_text(" ", strip=True) if ozet_el else ""

        # PDF linki varsa al
        pdf_el = blok.select_one("div.gs_or_ggsm a")
        pdf_url = pdf_el["href"] if pdf_el and pdf_el.has_attr("href") else None

        # Atıf sayısı ("Alıntılanma sayısı: 45" veya "Cited by 45")
        atif = 0
        for a in blok.select("div.gs_fl a"):
            t = a.get_text(strip=True)
            m = re.search(r"(?:Alıntılanma sayısı|Cited by)\s*:?\s*(\d+)", t, re.IGNORECASE)
            if m:
                atif = int(m.group(1))
                break

        makaleler.append({
            "title": baslik,
            "year": yil,
            "abstract": ozet,
            "authors_venue": meta_metin,
            "url": makale_url,
            "pdf_url": pdf_url,
            "citations": atif,
            "source": "Google Akademik",
        })

    return makaleler, toplam_tahmin, None


# ===================== TAM ÖZET ZENGİNLEŞTİRME & YILLIK TREND =====================
def tam_ozet_ve_trend_zenginlestir(sorgu_ham, bas_yil, bit_yil, yayinci_filtre, gs_makaleler):
    """
    1. Google Akademik özetleri yarım (...) kaldığında veya Google CAPTCHA çıkardığında
       OpenAlex / Semantic Scholar üzerinden makalelerin TAM ÖZETLERİNİ (full abstract),
       başlığını, yılını ve yayıncısını tamamlar.
    2. Yıl bazlı makale sayısı trendini (hem genel hem Elsevier / Taylor & Francis / Springer / IEEE / Wiley)
       kesin sayılarla hesaplar.
    """
    yillar = list(range(bas_yil, bit_yil + 1))

    # Yıllık genel makale trendi
    filtre = f"publication_year:{bas_yil}-{bit_yil},type:article"
    params_trend = {
        "filter": filtre,
        "search": sorgu_ham,
        "group_by": "publication_year",
    }
    yillik_toplam = {y: 0 for y in yillar}
    try:
        r = requests.get(f"{OA_API}/works", params=params_trend, timeout=20).json()
        for g in r.get("group_by", []):
            y = int(g["key"])
            if y in yillik_toplam:
                yillik_toplam[y] = g["count"]
    except Exception:
        pass

    # Büyük yayıncıların yıllık trendleri (Elsevier, Taylor & Francis, Springer Nature, Wiley, IEEE, MDPI)
    yayincilar = {
        "Elsevier": "P4310320990",
        "Taylor & Francis": "P4310320547",
        "Springer Nature": "P4310319965",
        "Wiley": "P4310320595",
        "IEEE": "P4310319808",
        "MDPI": "P4310310987",
    }
    yayinci_trendleri = {}
    for ad, pid in yayincilar.items():
        y_seri = {y: 0 for y in yillar}
        try:
            f_yay = f"publication_year:{bas_yil}-{bit_yil},type:article,primary_location.source.host_organization_lineage:{pid}"
            r_y = requests.get(
                f"{OA_API}/works",
                params={"filter": f_yay, "search": sorgu_ham, "group_by": "publication_year"},
                timeout=15,
            ).json()
            for g in r_y.get("group_by", []):
                y = int(g["key"])
                if y in y_seri:
                    y_seri[y] = g["count"]
        except Exception:
            pass
        yayinci_trendleri[ad] = y_seri

    # Makale listesi: Eğer Google Akademik'ten makaleler geldiyse onların eksik/kısa özetlerini tamamla,
    # ayrıca tam özetli makaleleri de getir.
    oa_makaleler = []
    try:
        f_works = f"publication_year:{bas_yil}-{bit_yil},type:article"
        if yayinci_filtre and yayinci_filtre in yayincilar:
            f_works += f",primary_location.source.host_organization_lineage:{yayincilar[yayinci_filtre]}"

        r_w = requests.get(
            f"{OA_API}/works",
            params={
                "filter": f_works,
                "search": sorgu_ham,
                "per-page": 50,
                "sort": "cited_by_count:desc",
            },
            timeout=20,
        ).json()

        for w in r_w.get("results", []):
            tam_ozet = ters_indeks_coz(w.get("abstract_inverted_index"))
            yazarlar = ", ".join(
                a.get("author", {}).get("display_name", "")
                for a in w.get("authorships", [])[:4]
                if a.get("author", {}).get("display_name")
            )
            if len(w.get("authorships", [])) > 4:
                yazarlar += " et al."

            loc = w.get("primary_location") or {}
            src = loc.get("source") or {}
            dergi = src.get("display_name") or ""
            yayinci_adi = src.get("host_organization_name") or ""
            meta_str = " - ".join(x for x in [yazarlar, dergi, yayinci_adi] if x)

            oa_url = w.get("doi") or loc.get("landing_page_url") or w.get("id")
            pdf_u = (w.get("open_access") or {}).get("oa_url")

            oa_makaleler.append({
                "title": w.get("title") or "Başlıksız Çalışma",
                "year": w.get("publication_year"),
                "abstract": tam_ozet or "Bu makale için açık özet metni yayıncı tarafından paylaşılmamıştır.",
                "authors_venue": meta_str,
                "publisher": yayinci_adi,
                "journal": dergi,
                "url": oa_url,
                "pdf_url": pdf_u,
                "citations": w.get("cited_by_count", 0),
                "source": "Google Akademik + OpenAlex Tam Özet",
            })
    except Exception:
        pass

    # Google Akademik sonuçları ile Tam Özetli sonuçları birleştir (Başlığa göre eşleştirip tam özeti ekle)
    oa_baslik_haritasi = {
        re.sub(r"\W+", "", m["title"].lower()): m for m in oa_makaleler if m.get("title")
    }

    birlesik_makaleler = []
    gorulen_anahtarlar = set()

    for gm in gs_makaleler:
        anahtar = re.sub(r"\W+", "", (gm.get("title") or "").lower())
        if not anahtar:
            continue
        gorulen_anahtarlar.add(anahtar)
        eslesen = oa_baslik_haritasi.get(anahtar)
        if eslesen and len(eslesen.get("abstract", "")) > len(gm.get("abstract", "")):
            gm["full_abstract"] = eslesen["abstract"]
            gm["publisher"] = eslesen.get("publisher", "")
            gm["journal"] = eslesen.get("journal", "")
        birlesik_makaleler.append(gm)

    for om in oa_makaleler:
        anahtar = re.sub(r"\W+", "", (om.get("title") or "").lower())
        if anahtar and anahtar not in gorulen_anahtarlar:
            gorulen_anahtarlar.add(anahtar)
            birlesik_makaleler.append(om)

    return yillik_toplam, yayinci_trendleri, birlesik_makaleler


# ===================== REST API UÇ NOKTALARI =====================
@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/search", methods=["GET", "POST"])
def api_search():
    data = request.get_json(silent=True) or request.args
    grup1 = data.get("keywords1", "").strip()
    grup2 = data.get("keywords2", "").strip()
    bas_yil = int(data.get("start_year", 2015))
    bit_yil = int(data.get("end_year", 2025))
    yayinci = data.get("publisher", "all").strip()
    sayfa = int(data.get("page", 1))
    serpapi_key = data.get("serpapi_key", "").strip() or os.getenv("SERPAPI_KEY")

    if not grup1:
        return jsonify({"error": "Lütfen en az bir anahtar kelime girin."}), 400

    sorgu = sorgu_olustur(grup1, grup2, yayinci if yayinci != "all" else "")
    baslangic_kayit = (sayfa - 1) * 10

    # 1. Google Akademik'ten çek
    gs_makaleler, gs_toplam, gs_uyari = google_scholar_sayfa_cek(
        sorgu, bas_yil, bit_yil, baslangic_kayit, serpapi_key
    )

    # 2. Tam özetleri ve yıllık makale trendini zenginleştir
    sorgu_yayincisiz = sorgu_olustur(grup1, grup2)
    yillik_toplam, yayinci_trendleri, makaleler = tam_ozet_ve_trend_zenginlestir(
        sorgu_yayincisiz, bas_yil, bit_yil, yayinci, gs_makaleler
    )

    return jsonify({
        "query": sorgu,
        "start_year": bas_yil,
        "end_year": bit_yil,
        "google_scholar_status": "OK" if not gs_uyari else gs_uyari,
        "google_scholar_Count": gs_toplam,
        "yearly_total": yillik_toplam,
        "publisher_trends": yayinci_trendleri,
        "articles": makaleler,
    })


if __name__ == "__main__":
    print("=" * 65)
    print(" AKADEMİK MAKALE & TREND ANALİZ SİSTEMİ ÇALIŞIYOR")
    print(" Tarayıcıda açın: http://localhost:5000")
    print("=" * 65)
    app.run(host="0.0.0.0", port=5000, debug=True)

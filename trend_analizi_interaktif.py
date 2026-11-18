"""
Akademik yayın trend analizi (etkileşimli, tek dosya)
Kaynaklar: OpenAlex (Elsevier + Taylor & Francis), ScienceDirect API, Web of Science Starter API

Kurulum:  pip install requests pandas matplotlib
Çalıştır: python trend_analizi_interaktif.py   (kurum VPN'i açıkken)

Script size sırayla şunları sorar: anahtar kelimeler, yıl aralığı, e-posta, API anahtarları.
API anahtarı girmeden Enter'a basarsanız o kaynak atlanır (OpenAlex anahtarsız çalışır).
"""
import os
import sys
import time
import getpass
import requests
import pandas as pd
import matplotlib.pyplot as plt

OA = "https://api.openalex.org"


# ===================== KULLANICIDAN BİLGİ AL =====================
def virgulle_ayir(metin):
    return [t.strip() for t in metin.split(",") if t.strip()]


def kullanici_girdisi():
    print("=" * 60)
    print(" AKADEMİK YAYIN TREND ANALİZİ")
    print("=" * 60)
    print("\nAnahtar kelimeleri virgülle ayırarak yazın.")
    print("Aynı grup içindekiler VEYA (OR) mantığıyla aranır.")
    print("İki grup girerseniz gruplar arası VE (AND) mantığı uygulanır.\n")

    grup1 = []
    while not grup1:
        grup1 = virgulle_ayir(input(
            "1) Ana anahtar kelimeler (örn: machine learning, deep learning): "))
    grup2 = virgulle_ayir(input(
        "2) Birlikte geçmesi gereken kelimeler (isteğe bağlı, örn: healthcare, clinical): "))

    bas = input("\nBaşlangıç yılı [2015]: ").strip() or "2015"
    bit = input("Bitiş yılı [2025]: ").strip() or "2025"
    eposta = input("E-posta (OpenAlex için, isteğe bağlı): ").strip()

    print("\nAPI anahtarları (yoksa Enter ile geçin; yazarken ekranda görünmez):")
    elsevier = os.getenv("ELSEVIER_API_KEY") or getpass.getpass("  Elsevier API anahtarı: ").strip()
    wos = os.getenv("WOS_API_KEY") or getpass.getpass("  WoS Starter API anahtarı: ").strip()

    def or_blok(liste, tirnak=True):
        parcalar = [f'"{k}"' if tirnak else k for k in liste]
        return "(" + " OR ".join(parcalar) + ")"

    bloklar = [or_blok(grup1)] + ([or_blok(grup2)] if grup2 else [])
    arama = " AND ".join(bloklar)              # OpenAlex + ScienceDirect
    wos_sorgu = f"TS=({arama})"                 # WoS söz dizimi

    cfg = {
        "ARAMA": arama,
        "WOS_SORGU": wos_sorgu,
        "BASLANGIC": int(bas),
        "BITIS": int(bit),
        "EPOSTA": eposta,
        "ELSEVIER_KEY": elsevier or None,
        "WOS_KEY": wos or None,
        "KONU_ADI": "_".join(grup1[:2]).replace(" ", "_")[:40],
    }
    print(f"\nKurulan sorgu: {arama}")
    print(f"WoS sorgusu : {wos_sorgu}\n")
    return cfg


# ===================== YARDIMCI =====================
def get(url, **kw):
    for deneme in range(3):
        try:
            r = requests.get(url, timeout=30, **kw)
            if r.status_code == 429:
                time.sleep(2 * (deneme + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException:
            if deneme == 2:
                raise
            time.sleep(1.5)


# ===================== OpenAlex =====================
def openalex_yayinci(ad, eposta):
    params = {"search": ad}
    if eposta:
        params["mailto"] = eposta
    r = get(f"{OA}/publishers", params=params).json()
    if not r["results"]:
        raise RuntimeError(f"OpenAlex'te yayıncı bulunamadı: {ad}")
    en_buyuk = max(r["results"], key=lambda x: x.get("works_count", 0))
    pid = en_buyuk["id"].split("/")[-1]
    print(f"  [{ad}] -> {en_buyuk['display_name']} ({pid})")
    return pid


def openalex_yillik(pid, cfg, arama=None):
    filtre = (f"publication_year:{cfg['BASLANGIC']}-{cfg['BITIS']},"
              f"primary_location.source.host_organization_lineage:{pid}")
    params = {"filter": filtre, "group_by": "publication_year"}
    if cfg["EPOSTA"]:
        params["mailto"] = cfg["EPOSTA"]
    if arama:
        params["search"] = arama
    r = get(f"{OA}/works", params=params).json()
    return {int(g["key"]): g["count"] for g in r["group_by"]}


# ===================== OpenAlex Topla =====================
def openalex_topla(cfg):
    veri = {}
    for ad in ["Elsevier", "Taylor & Francis"]:
        print(f"OpenAlex: {ad}")
        pid = openalex_yayinci(ad, cfg["EPOSTA"])
        veri[f"{ad} (konu)"] = pd.Series(openalex_yillik(pid, cfg, cfg["ARAMA"]))
        veri[f"{ad} (toplam yayın)"] = pd.Series(openalex_yillik(pid, cfg))
    return veri


# ===================== ScienceDirect =====================
def sciencedirect_topla(cfg, yillar):
    if not cfg["ELSEVIER_KEY"]:
        print("ScienceDirect atlandı: anahtar girilmedi.")
        return None
    url = "https://api.elsevier.com/content/search/sciencedirect"
    headers = {"X-ELS-APIKey": cfg["ELSEVIER_KEY"], "Accept": "application/json",
               "Content-Type": "application/json"}
    sonuc = {}
    for yil in yillar:
        r = requests.put(url, headers=headers, timeout=30,
                         json={"qs": cfg["ARAMA"], "date": str(yil),
                               "display": {"offset": 0, "show": 1}})
        if r.status_code != 200:
            print(f"  ScienceDirect {yil} hata {r.status_code}: {r.text[:200]}")
            return None
        sonuc[yil] = r.json().get("resultsFound", 0)
        time.sleep(0.5)
    print("ScienceDirect tamam.")
    return pd.Series(sonuc)


# ===================== Web of Science =====================
def wos_topla(cfg, yillar):
    if not cfg["WOS_KEY"]:
        print("WoS atlandı: anahtar girilmedi.")
        return None
    url = "https://api.clarivate.com/apis/wos-starter/v1/documents"
    sonuc = {}
    for yil in yillar:
        r = requests.get(url, headers={"X-ApiKey": cfg["WOS_KEY"]}, timeout=30,
                         params={"q": f"{cfg['WOS_SORGU']} AND PY={yil}",
                                 "limit": 1, "page": 1})
        if r.status_code != 200:
            print(f"  WoS {yil} hata {r.status_code}: {r.text[:200]}")
            return None
        sonuc[yil] = r.json()["metadata"]["total"]
        time.sleep(1)
    print("WoS tamam.")
    return pd.Series(sonuc)


# ===================== ANA AKIŞ =====================
def main():
    cfg = kullanici_girdisi()
    yillar = list(range(cfg["BASLANGIC"], cfg["BITIS"] + 1))
    tablo = {}

    try:
        tablo.update(openalex_topla(cfg))
    except Exception as e:
        print("OpenAlex hata:", e)

    sd = sciencedirect_topla(cfg, yillar)
    if sd is not None:
        tablo["ScienceDirect API"] = sd

    wos = wos_topla(cfg, yillar)
    if wos is not None:
        tablo["Web of Science"] = wos

    if not tablo:
        sys.exit("Hiç veri alınamadı.")

    df = pd.DataFrame(tablo).reindex(yillar)

    # Normalizasyon: konunun yayıncının o yılki toplam yayınındaki payı (binde)
    for ad in ["Elsevier", "Taylor & Francis"]:
        k, t = f"{ad} (konu)", f"{ad} (toplam yayın)"
        if k in df and t in df:
            df[f"{ad} pay (‰)"] = df[k] / df[t] * 1000

    dosya = cfg["KONU_ADI"]
    df.to_csv(f"{dosya}_trend.csv", encoding="utf-8-sig")
    print("\n", df.round(2).to_string())

    mutlak = [c for c in df.columns if "toplam" not in c and "pay" not in c]
    ax = df[mutlak].plot(marker="o", figsize=(10, 5),
                         title=f"{dosya}: yıllık yayın sayısı")
    ax.set_xlabel("Yıl"); ax.set_ylabel("Yayın sayısı"); ax.grid(alpha=.3)
    plt.tight_layout(); plt.savefig(f"{dosya}_mutlak.png", dpi=150)

    pay = [c for c in df.columns if "pay" in c]
    if pay:
        ax = df[pay].plot(marker="o", figsize=(10, 5),
                          title=f"{dosya}: yayıncı içindeki pay (binde)")
        ax.set_xlabel("Yıl"); ax.set_ylabel("‰"); ax.grid(alpha=.3)
        plt.tight_layout(); plt.savefig(f"{dosya}_normalize.png", dpi=150)

    print(f"\nKaydedildi: {dosya}_trend.csv, {dosya}_mutlak.png, {dosya}_normalize.png")
    plt.show()


if __name__ == "__main__":
    main()

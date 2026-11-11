# Uvaia

Linux Mint Cinnamon/X11 için yerel görsel dönüştürme uygulaması.

## Çalıştırma

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python uvaia.py
```

Nemo'dan tek bir görseli pencereye bırak veya **Görsel seç…** düğmesini kullan.
Çarktan **PNG**, **JPG** veya **WebP** seç. Sonuç kaynak dosyanın klasörüne
kaydedilir. Aynı isimde bir dosya varsa numaralı bir ad kullanılır. JPG çıktısında
şeffaf alanlar beyaz olur.

İlk prototipte çark, dosya pencereye bırakıldığında açılır.

Sürükle-bırak akışı Nashi'den ilham alır.

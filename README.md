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

## Sürüklerken çarkı açma

Uvaia açıkken Nemo'da bir görseli sol tuşla sürüklemeye başla. **Shift**'e basınca
işlem çarkı imlecin yakınında açılır. Fareyi basılı tutarken **Shift’i bırak**,
ardından görseli **PNG**, **JPG** veya **WebP** düğmesinin üstüne bırak.
Nemo, Shift basılıyken taşıma işlemi sunar. Uvaia, kaynak dosyayı korumak için
yalnızca kopyalama işlemini kabul eder. Sürüklemeyi iptal edersen çark kapanır.

Bu kısayol X11 oturumunda çalışır. Uvaia'nın penceresine dosya bırakmak ve
dosya seçiciyi kullanmak da mümkündür.

Sürükle-bırak akışı Nashi'den ilham alır.

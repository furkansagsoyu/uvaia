# Uvaia

Linux Mint Cinnamon/X11 için yerel görsel, PDF ve video araçları.

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

**Görseli küçült…** ile yeni boyutu yüzde olarak seç. Örneğin %50, 1200 × 800
piksellik bir görseli 600 × 400 piksele indirir. Uvaia PNG, JPG ve WebP
biçimlerini korur, diğer hareketsiz görselleri PNG olarak kaydeder. Çıktı adına
oran eklenir (`foto-50pct.png` gibi).

**Görseli kırp…** ile önizlemeyi aç ve fareyle bir alan seç. **Kırpılmış
kopyayı kaydet** seçimi kaynak klasöre `foto-kirpilmis.png` gibi bir dosya
olarak yazar.

## Sürüklerken çarkı açma

Uvaia açıkken Nemo'da bir görseli sol tuşla sürüklemeye başla. **Shift**'e basınca
işlem çarkı imlecin yakınında açılır. Fareyi basılı tutarken **Shift’i bırak**,
ardından görseli **PNG**, **JPG** veya **WebP** düğmesinin üstüne bırak.
Nemo, Shift basılıyken taşıma işlemi sunar. Uvaia, kaynak dosyayı korumak için
yalnızca kopyalama işlemini kabul eder. Sürüklemeyi iptal edersen çark kapanır.

Bu kısayol X11 oturumunda çalışır. Uvaia'nın penceresine dosya bırakmak ve
dosya seçiciyi kullanmak da mümkündür.

Sürükle-bırak akışı Nashi'den ilham alır.

## PDF birleştirme

Ana pencerede **PDF birleştir…** düğmesine bas. **PDF ekle…** ile en az iki
dosya seç, gerekirse **Yukarı** ve **Aşağı** ile sırala, ardından **Birleştir**’e
bas. Sonuç, listedeki ilk PDF’nin klasörüne `dosya-birlesik.pdf` adıyla yazılır.
Şifreli PDF’ler bu sürümde desteklenmez.

## PDF’den sayfa çıkarma

PDF’yi ana pencereye bırak ve **PDF’den sayfa çıkar…** düğmesine bas. Dosya
bırakmadan da aynı düğmeyle bir PDF seçebilirsin. `1, 3-5` gibi sayfa numaraları
veya aralıkları yaz. Uvaia sayfaları girdiğin sırayla, kaynak PDF’nin klasöründeki
`dosya-sayfalar.pdf` dosyasına kaydeder.

## Videodan MP3 çıkarma

MP4, MKV, MOV, WebM veya AVI dosyasını ana pencereye bırak ve **MP3 olarak
kaydet**’e bas. **Videodan MP3 çıkar…** düğmesiyle de video seçebilirsin.
İlk ses parçası videonun klasörüne MP3 olarak yazılır. Ses parçası olmayan
videolar için uygulama hata gösterir.

FFmpeg, Linux Mint’te `imageio-ffmpeg` bağımlılığıyla kurulur.

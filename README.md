# Uvaia

Linux Mint Cinnamon/X11 için yerel görsel, PDF, video, ses ve arşiv araçları.

## Çalıştırma

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python uvaia.py
```

Araçlar **Görsel**, **PDF**, **Video**, **Ses** ve **Arşiv** sekmelerinde. Ana pencereye dosya
bıraktığında Uvaia ilgili sekmeyi açar. Birden fazla PDF bırakmak birleştirme
listesini açar.

Nemo'dan bir veya birden fazla görseli pencereye bırak ya da **Dosya seç…**
düğmesini kullan.
Çarktan **PNG**, **JPG** veya **WebP** seç. Sonuç kaynak dosyanın klasörüne
kaydedilir. Aynı isimde bir dosya varsa numaralı bir ad kullanılır. JPG çıktısında
şeffaf alanlar beyaz olur. Toplu seçimde her çıktı kendi kaynak klasörüne
kaydedilir. Bir dosya hata verirse diğerleri işlenir ve sonuç özeti gösterilir.
Toplu dönüştürmede ilerleme görünür. **İptal et**, üzerinde çalışılan dosya
bitince işlemi durdurur. Kaydedilen çıktıları açmaya devam edebilirsin.

İşlem sonunda **Çıktıyı aç** ile tek dosyayı varsayılan uygulamada açabilir,
**Çıktı klasörünü aç** ile dosyanın bulunduğu klasöre gidebilirsin. Çıktılar
farklı klasörlerdeyse açacağın klasörü menüden seç.

**Görseli küçült…** ile yeni boyutu yüzde olarak seç. Örneğin %50, 1200 × 800
piksellik bir görseli 600 × 400 piksele indirir. Uvaia PNG, JPG ve WebP
biçimlerini korur, diğer hareketsiz görselleri PNG olarak kaydeder. Çıktı adına
oran eklenir (`foto-50pct.png` gibi).

**Görseli kırp…** ile önizlemeyi aç ve fareyle bir alan seç. **Kırpılmış
kopyayı kaydet** seçimi kaynak klasöre `foto-kirpilmis.png` gibi bir dosya
olarak yazar.

**Görseli sıkıştır…** ile JPG veya WebP ve 1–95 arası kalite seç. Uvaia
piksel boyutlarını korur. Çıktı kaynak dosyadan küçükse
`foto-sikistirilmis.webp` gibi bir kopya kaydeder.

**Döndür ve yansıt…** ile görseli 90 derece sağa veya sola döndür, yatay veya
dikey yansıt ve sonucu önizle. **Kopyayı kaydet** değişiklikleri
`foto-duzenlenmis.png` gibi yeni bir dosyaya yazar.

**Görsel ayarları…** ile parlaklık, kontrast ve doygunluğu değiştir. Önizleme
anında güncellenir. **Kopyayı kaydet** ayarlanmış görseli
`foto-ayarli.png` gibi ayrı bir dosyaya yazar.

**Görsel bilgileri…** ile piksel boyutunu, kamera bilgisini ve EXIF konum
etiketinin bulunup bulunmadığını gör. **Meta verisiz PNG kaydet** seçeneği
görselin görünür yönünü ve şeffaflığını koruyarak yeni bir PNG oluşturur.
Kaynak EXIF, konum, XMP, metin etiketleri ve ICC profili kopyaya aktarılmaz.
Gömülü renk profili varsa çıktı sRGB’ye dönüştürülür.

## Cinnamon ve Nemo menülerine ekleme

```bash
.venv/bin/python install_desktop.py
```

Cinnamon menüsünde **Uvaia** görünür. Nemo’da desteklenen dosyalara sağ
tıklayıp **Uvaia ile aç** seçebilirsin. Birden fazla görsel seçilirse toplu
dönüştürme, birden fazla PDF seçilirse birleştirme listesi açılır. Proje
klasörünü taşırsan kurulum komutunu tekrar çalıştır. Menü girdilerini kaldırmak
için aynı komuta `--remove` ekle.

## Sürüklerken çarkı açma

Uvaia açıkken Nemo'da seçili görselleri sol tuşla sürüklemeye başla. **Shift**'e basınca
işlem çarkı imlecin yakınında açılır. Fareyi basılı tutarken **Shift’i bırak**,
ardından görselleri **PNG**, **JPG** veya **WebP** düğmesinin üstüne bırak.
Nemo, Shift basılıyken taşıma işlemi sunar. Uvaia, kaynak dosyayı korumak için
yalnızca kopyalama işlemini kabul eder. Sürüklemeyi iptal edersen çark kapanır.

Bu kısayol X11 oturumunda çalışır. Uvaia'nın penceresine dosya bırakmak ve
dosya seçiciyi kullanmak da mümkündür.

Sürükle-bırak akışı Nashi'den ilham alır.

## Görsellerden PDF oluşturma

Bir veya daha fazla görseli ana pencereye bırak ve **Görsellerden PDF…**’yi aç.
**Görsel ekle…** ile doğrudan dosya da seçebilirsin. Sayfa sırasını düzenleyip
**PDF oluştur**’a bas. Her görsel ayrı bir sayfa olur. Şeffaf alanlar beyaz
zeminle kaydedilir. Çıktı, listedeki ilk görselin klasörüne
`gorsel-gorseller.pdf` adıyla yazılır.

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

## PDF’yi bölme

**PDF’yi böl…** ile tüm sayfaları veya `1, 3-5` gibi bir seçimi dosya başına
belirlediğin sayıda grupla. Uvaia bölümleri kaynak klasöre
`belge-bolum-001.pdf`, `belge-bolum-002.pdf` gibi adlarla yazar. İşlemi iptal
ettiğinde kaydedilmiş bölümleri açabilirsin.

## PDF’den metin çıkarma

**PDF’den metin çıkar…** ile tüm belgeyi veya `1, 3-5` gibi bir sayfa
seçimini işle. Uvaia metin içeren sayfaları, sayfa numaralarıyla birlikte
`belge-metin.txt` dosyasına UTF-8 olarak kaydeder. Bu araç PDF’nin seçilebilir
metin katmanını kullanır.

## Taranmış PDF ve görselleri OCR ile okuma

Linux Mint’te Tesseract ve dil paketlerini bir kez kur:

```bash
sudo apt install tesseract-ocr tesseract-ocr-tur tesseract-ocr-eng
```

PDF sekmesinde **Taranmış PDF’yi oku (OCR)…** seçeneğini aç. Tüm belgeyi veya
`1, 3-5` gibi sayfaları seç. Uvaia Türkçe ve İngilizce yazıyı yerel olarak
tanır. **Metin (.txt)** seçeneği `belge-ocr.txt` dosyasını oluşturur.
**Aranabilir PDF (.pdf)** seçeneği, 300 DPI sayfa görüntüleri ve seçilebilir
bir metin katmanı içeren `belge-aranabilir.pdf` dosyasını oluşturur. İşlenen
sayfa sayısı tarama sırasında görünür. **İptal et** yarım çıktıyı kaydetmeden
işlemi durdurur.

Ekran görüntüsü veya fotoğraf için **Görsel** sekmesinde **Görseldeki yazıyı
oku (OCR)…** seçeneğini kullan. Çıktı `foto-ocr.txt` olarak kaydedilir.

## PDF sayfalarını döndürme

**PDF sayfalarını döndür…** ile sayfaları 90° sağa, 90° sola veya 180°
döndür. Tüm belge için sayfa alanını boş bırak ya da `1, 3-5` gibi bir
seçim yaz. Çıktı kaynak klasöre `belge-dondurulmus.pdf` olarak kaydedilir.

## PDF sayfalarını PNG veya JPG olarak kaydetme

PDF sekmesinde **PDF’yi görsele dönüştür…** seçeneğini aç. **Sayfalar** alanını
tüm belge için boş bırak veya `1, 3-5` gibi bir seçim yaz. Uvaia her sayfayı
144 DPI ile kaynak klasöre `belge-sayfa-3.png` gibi ayrı bir dosya olarak yazar.
İptal isteği işlenen sayfa bitince uygulanır. Kaydedilmiş sayfalar korunur.

## Videoyu MP4 veya WebM’ye dönüştürme

Video sekmesinde **Videoyu dönüştür…** ile MP4 veya WebM seç. Uvaia ilk video
akışını ve varsa ilk ses parçasını seçtiğin biçimde kaynak klasöre kaydeder.
Dönüştürme ve kesme sırasında ilerlemeyi görebilirsin. **İptal et** çalışan
FFmpeg işlemini durdurur ve yarım video dosyasını kaydetmez.

## Videoyu sıkıştırma

**Videoyu sıkıştır…** ile çıktı yüksekliğini ve kaliteyi seç. Seçilen yükseklik
üst sınırdır. Uvaia küçük videoları büyütmez ve görüntü oranını korur.
Yalnızca daha küçük bir çıktı elde edilirse `video-sikistirilmis.mp4` kaydedilir.

## Videodan MP3 çıkarma

MP4, MKV, MOV, WebM veya AVI dosyasını ana pencereye bırak ve **MP3 olarak
kaydet**’e bas. **Videodan MP3 çıkar…** düğmesiyle de video seçebilirsin.
İlk ses parçası videonun klasörüne MP3 olarak yazılır. Ses parçası olmayan
videolar için uygulama hata gösterir.

FFmpeg, Linux Mint’te `imageio-ffmpeg` bağımlılığıyla kurulur.

## Video sesini kaldırma

Videoyu ana pencereye bırak veya Video sekmesinde **Video sesini kaldır…**
ile seç. Uvaia görüntüyü yeniden kodlamadan, tüm ses parçalarını çıkarır ve
kaynak klasöre `video-sessiz.mp4` gibi aynı biçimde bir kopya yazar.

## Videodan kare alma

Videoyu ana pencereye bırak ya da **Videodan kare al…** ile seç.
Kare zamanını saniye veya saat biçiminde gir. Örneğin `12,5` ve
`00:12.500` aynı zamanı belirtir. **Önizle** ile seçtiğin kareyi görebilirsin. **PNG olarak
kaydet** tam çözünürlüklü kareyi kaynak klasöre
`video-kare-12.500s.png` adıyla kaydeder.

## Videoyu kesme

Videoyu ana pencereye bırak veya **Videoyu kes…** ile seç. Başlangıç ve bitiş
zamanlarını gir. **Başlangıcı önizle** ve **Bitişi önizle** seçilen zamanlardaki
kareyi gösterir. **Kesiti kaydet** ile Uvaia görüntüyü ve varsa ilk ses
parçasını aynı klasöre MP4 olarak kaydeder. Bitiş zamanı videodan uzunsa çıktı
video sonunda biter.

## QR kodu okuma

QR kodunu içeren görseli ana pencereye bırak ve **QR kodu oku…**’ya bas.
Bu düğmeyle doğrudan bir görsel de seçebilirsin. Bulunan içerik düz metin
olarak gösterilir. Metnin tamamını veya seçili bölümünü **Panoya kopyala**
düğmesiyle kopyalayabilirsin.

PDF’de tarama yapmak için **PDF** sekmesinde **PDF’de QR kodu ara…** seçeneğini
aç. Tüm belge için alanı boş bırak veya `1, 3-5` gibi sayfalar seç. Sonuçlarda
her kodun bulunduğu sayfa numarası gösterilir.

## Video hızını değiştirme

**Video hızını değiştir…** ile 0,50× ve 2,00× arasında bir hız seç.
Uvaia görüntünün hızını ve varsa ilk ses parçasının temposunu birlikte
değiştirir. Çıktı kaynak klasöre `video-hiz-1.50x.mp4` gibi bir adla yazılır.

## Ses dönüştürme

Bir ses dosyasını pencereye bırak ve **Ses → Sesi dönüştür…** ile MP3, WAV
veya FLAC seç. Çıktı kaynak klasöre kaydedilir. İlerlemeyi görebilir ve yarım
çıktı bırakmadan işlemi iptal edebilirsin.

## Sesi kesme

**Ses → Sesi kes…** ile başlangıç ve bitiş zamanını gir, ardından MP3, WAV
veya FLAC seç. `12,5` ve `00:12.500` aynı zamanı belirtir. Kesit yeni bir
dosya olarak kaynak klasöre kaydedilir.

## ZIP arşivleri

**Arşiv → ZIP oluştur…** ile seçilen dosyaları ilk dosyanın klasöründe
`dosya-arsiv.zip` olarak paketle. Bir ZIP bırakıp **ZIP’i aç…** seçerek
içeriği arşivin yanındaki yeni bir klasöre çıkar. Çıktı adları çakışırsa numara
eklenir. İptal edilen ZIP işlemlerinin yarım çıktıları temizlenir.

ZIP açma, en fazla 10.000 öğe ve 8 GiB açılmış içerik kabul eder.
Nemo sağ tık menüsüne ZIP ve ses dosyası desteği eklemek için `install_desktop.py` komutunu
yeniden çalıştırabilirsin.

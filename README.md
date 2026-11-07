# Atölye — fotoğraf seçimi

FastAPI, SQLite ve Vanilla JavaScript ile tek sunucuda çalışan, mobil öncelikli bir fotoğraf seçim uygulaması.

## Dosya yapısı

```text
app/
  config.py           Ortam değişkenleri ve dizinler
  database.py         SQLite şeması ve bağlantılar
  images.py           Sınırlı boyutlu WebP üretimi
  main.py             Yönetici ve müşteri HTTP rotaları
  security.py         Yönetici oturumu, istek ve giriş kontrolü
templates/            Jinja2 sayfaları
static/               CSS ve Vanilla JavaScript
deploy/               systemd ve Nginx örnekleri
tests/                API ve eşzamanlı seçim testleri
data/                 Oluşturulan SQLite veritabanı
uploads/              Oluşturulan WebP önizlemeler
```

`data/` ve `uploads/` ilk çalıştırmada oluşturulur. **Orijinal fotoğraflar saklanmaz:** yükleme sonrasında yalnızca orijinal dosya adı ve en uzun kenarı 1200 piksel olan WebP saklanır. Orijinal fotoğraflarınızı ve Lightroom kataloğunuzu ayrıca koruyun. Aynı isimli dosyalar raporda ayırt edilemez; aynı galeride benzersiz ve tercihen virgül içermeyen dosya adları kullanın.

## 1. Yerel kurulum

Python 3.10+ ve Python sanal ortam desteği gereklidir:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` dosyasını düzenleyin. `ADMIN_PASSWORD` en az 12 karakter, `SECRET_KEY` en az 32 karakter olmalıdır. Her ikisi de benzersiz ve rastgele olmalıdır; örneğin `openssl rand -hex 32` ile ayrı değerler üretin. `.env` dosyasını paylaşmayın.

Yalnızca geçici test için `.env` içinde `ALLOW_INSECURE_PIN=true` ayarlanırsa altı ASCII rakamdan oluşan bir `ADMIN_PASSWORD` da kabul edilir. Altı haneli PIN tahmin edilmesi kolay olduğundan üretimde kullanmayın; özellikle HTTP üzerinde parola ve oturum şifrelenmez. Güçlü parolaya dönün ve bu ayarı `false` yapın.

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

`http://127.0.0.1:8000/admin` adresini açın. Yerel HTTP için `COOKIE_SECURE=false` bırakın; HTTPS üzerinde `true` yapın. Sunucu ortam değişkenleri `.env` değerlerinden önceliklidir.

## 2. Kullanım

1. Yönetici olarak giriş yapın, yeni bir galeri ve seçim üst sınırı oluşturun.
2. Galeriyi seçip JPG/PNG dosyalarını sürükleyin veya çoklu dosya seçiciyle yükleyin. Dosyalar tek tek işlenir; her dosya en fazla 30 MB ve 40 milyon piksel olabilir.
3. Galeriyi yayınlayın; özel bağlantıyı müşteriye iletin. Bağlantıya sahip olan herkes erişebileceğinden bağlantıyı gizli tutun.
4. Müşteri kalp düğmesiyle seçim yapar, isteğe bağlı notları düzenler ve alanın dışına çıkarak kaydeder. Sayaç ve sunucu üst sınırı denetler. En az bir fotoğraf seçildikten sonra onay verilebilir; gönderim seçimleri ve notları kilitler.
5. Yönetici ekranındaki sonuçlar yaklaşık 10 saniyede bir yenilenir. Dosya adlarını kopyalayın veya metin alanından elle alın. Lightroom Classic Library Filter'da **Text → Filename → Contains** alanına virgülle ayrılmış listeyi yapıştırın; sonuçları kendi Lightroom sürümünüzde ve dosya adlarınızla doğrulayın. Notlar yönetici ekranında fotoğraf altında görünür.
6. Galeri yayından kaldırıldığında bağlantı ve önizlemeler müşteriye kapanır. Gönderilmiş galeride fotoğraf ekleme/silme kapalıdır; tekrar açma özelliği yoktur.

## 3. Linux VPS ve systemd

Örnek, uygulamanın `/opt/photo-select` altında bulunduğunu ve Debian/Ubuntu üzerinde Python, `python3-venv`, Nginx ve TLS sertifikalarının kurulu olduğunu varsayar. Proje dosyalarını sunucuya aktardıktan sonra:

```bash
sudo useradd --system --home /opt/photo-select --shell /usr/sbin/nologin photo-select
cd /opt/photo-select
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo cp .env.example .env
sudo mkdir -p data uploads
sudo chown -R photo-select:photo-select data uploads
sudo chown root:photo-select .env
sudo chmod 640 .env
sudo chmod 755 /opt/photo-select
```

`.env` dosyasını düzenleyin: güçlü `ADMIN_PASSWORD` ve `SECRET_KEY` belirleyin; `COOKIE_SECURE=true` yapın; `DATA_DIR=/opt/photo-select/data` ve `UPLOAD_DIR=/opt/photo-select/uploads` kullanın. systemd örneği bu dizinlere yazmaya izin verir; dizinleri değiştirirseniz servis dosyasındaki `ReadWritePaths` değerini de değiştirin.

```bash
sudo cp deploy/photo-select.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now photo-select
sudo systemctl status photo-select
sudo journalctl -u photo-select -f
```

[Nginx örneğini](deploy/nginx.conf) alan adınız ve sertifika yollarınızla düzenleyin, site yapılandırmasına yerleştirin ve `sudo nginx -t && sudo systemctl reload nginx` ile uygulayın. DNS, HTTPS sertifikası ve güvenlik duvarını ayrıca yapılandırın. Uvicorn yalnızca `127.0.0.1` üzerinden dinlemelidir. Proxy'nin yükleme sınırı 31 MB'tır; uygulama dosya içeriğini ayrıca 30 MB ile sınırlar.

## 4. Test

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Testler geçici veritabanı ve önizleme dizinleri kullanır; mevcut galerilere dokunmaz.

## İşletim ve güvenlik notları

- Tek Uvicorn worker kullanın: görsel işleme aynı anda bir dosyayla sınırlandırılır; giriş denemesi sınırı da işlem belleğindedir. Giriş başına istemci IP'sinde 15 dakikada beş başarısız denemeye izin verilir; yeniden başlatmada sıfırlanır. Üretimde Nginx/firewall üzerinde ayrıca hız sınırı uygulayın. Güvenilir olmayan proxy'lerden gelen `X-Forwarded-For` değerlerine güvenmeyin.
- Yönetici oturumu imzalı, HttpOnly ve SameSite=Lax çerezidir; üretimde HTTPS ve `COOKIE_SECURE=true` zorunludur. Oturum sekiz saat sürer; parolayı değiştirmenin yanı sıra `SECRET_KEY` değişimi eski tüm oturumları geçersiz kılar. Çıkış yalnızca mevcut tarayıcının çerezini temizler.
- Token'lar rastgeledir, ancak bağlantı bir paroladır: güvenli kanaldan paylaşın. Bağlantı değiştirme veya müşteri bazlı kimlik doğrulama özelliği yoktur. HTTP yanıtları `no-store` ve `no-referrer` kullanır. Tailwind CDN ve Google Fonts, kullanıcıların tarayıcılarından üçüncü taraf sunucularına bağlanır; çevrimdışı veya üçüncü taraf isteği olmadan çalıştırma bu yapılandırmada desteklenmez.
- Pillow görselleri birer birer işler, yükleme geçici dosyaya taşınabilir ve boyut/piksel sınırları vardır; yine de 1 GB sunucuda işletim sistemi, proxy, disk alanı ve başka servisler için pay bırakın. Çok büyük görseller reddedilir. Dosya başına yükleme sırasında geçici disk alanı gerekir.
- Tutarlı yedek için servisi durdurup `data/`, `uploads/` ve güvenli biçimde saklanan `.env` dosyasını birlikte yedekleyin; ardından servisi başlatın. Disk doluluğunu, servis kayıtlarını ve yedeklerin geri yüklenebilirliğini takip edin.

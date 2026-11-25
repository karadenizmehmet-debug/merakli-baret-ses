# Meraklı Baret – Seslendirme

`istekler/<ad>/script.json` dosyasını gönder. GitHub Actions doğal Türkçe sesi üretir ve aynı klasöre yazar:

- `ses.wav`: tüm anlatım (24 kHz, -16 LUFS)
- `ses/NN.wav`: cümle cümle ses
- `zamanlar.json`: cümle ve kelime zamanları (altyazı için)
- `agiz.json`: 30 fps ağız açıklığı (karakter animasyonu için)

Model: [Chatterbox Multilingual](https://github.com/resemble-ai/chatterbox) (Resemble AI, MIT lisans, ticari kullanım serbest). Her çıktıda duyulmayan PerTh filigranı vardır.

Ses rengi `referans/baret.wav` dosyasından kopyalanır (Piper `tr_TR-fahrettin-medium`, CC0). Kendi sesinle 10 sn temiz bir kayıt koyarsan model o sesi kullanır.

Her cümle 3 kez denenir. Konuşma hızı ve boşluklara göre en iyisi seçilir.

Mehmet Karadeniz, 2026-2027

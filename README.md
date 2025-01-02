# PAU Earthquake Analysis Plugin

Bu QGIS eklentisi, Türkiye'deki deprem verilerini analiz etmek ve görselleştirmek için geliştirilmiştir. İl ve ilçe bazında deprem verilerini filtreleyebilir, diri fay hatlarını görüntüleyebilir ve çeşitli analizler yapabilirsiniz.

## Özellikler

- İl ve ilçe bazında deprem verisi filtreleme
- Yakınlık mesafesine göre analiz (buffer)
- Diri fay hatlarını görüntüleme
- Deprem büyüklüğüne göre filtreleme
- Tarih aralığına göre filtreleme
- Deprem verilerini harita üzerinde görselleştirme

## Kurulum

1. QGIS'i açın
2. Eklentiler > Eklentileri Yönet ve Yükle'yi seçin
3. Ayarlar sekmesinden "Eklenti deposu ekle" butonuna tıklayın
4. Eklenti deposunu ekleyin ve eklentiyi yükleyin

Alternatif olarak:
1. Bu depoyu ZIP olarak indirin
2. QGIS'te Eklentiler > Eklentileri Yönet ve Yükle > ZIP'ten Yükle seçeneğini kullanın
3. İndirdiğiniz ZIP dosyasını seçin

## Kullanım

1. QGIS'i açın ve eklentiyi yükleyin
2. Eklenti simgesine tıklayın
3. İlçe sınırları shapefile'ını seçin
4. Deprem verilerini içeren CSV dosyasını seçin
5. Diri fay hatları shapefile'ını seçin (isteğe bağlı)
6. İl ve ilçe seçin
7. Yakınlık mesafesi, tarih aralığı ve büyüklük filtrelerini ayarlayın
8. Analiz sonuçlarını harita üzerinde görüntüleyin

## Gereksinimler

- QGIS 3.x
- Python 3.x
- pandas
- numpy

## Lisans

Bu proje MIT lisansı altında lisanslanmıştır. Detaylar için [LICENSE](LICENSE) dosyasına bakın.

## Katkıda Bulunma

1. Bu depoyu fork edin
2. Yeni bir branch oluşturun (`git checkout -b feature/yeniOzellik`)
3. Değişikliklerinizi commit edin (`git commit -am 'Yeni özellik eklendi'`)
4. Branch'inizi push edin (`git push origin feature/yeniOzellik`)
5. Pull Request oluşturun

## İletişim

- Geliştirici: [Onur Oduncu]
- E-posta: [mail@onuroduncu.info]
- Proje: [https://github.com/0nur0duncu/pau_earthquake_analysis]

## Teşekkürler

- Pamukkale Üniversitesi
- QGIS Topluluğu
- Katkıda bulunan tüm geliştiriciler 